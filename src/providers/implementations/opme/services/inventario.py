"""Contagem periódica de inventário: bipa o estoque e aponta as pendências.

Uma contagem cobre UM local — o almoxarifado ou uma das farmácias —, porque é
assim que ela acontece de verdade: a pessoa está de pé em um estoque só, com o
leitor na mão. Contar "tudo" de uma vez produziria uma lista de pendências
misturando locais, impossível de agir.

O inventário **não move material**. Ele compara o que foi bipado com o que o
sistema esperava ali e entrega a lista de pendências. Corrigir é decisão de
quem lê o relatório, feita depois pelas operações normais, com motivo
registrado — uma contagem apressada não deve mexer no estoque. Por isso nada
aqui grava em `eventos`: nenhum estado de unidade muda.

Diferença importante em relação a `fluxo.bipar`: lá, um código que responde a
mais de uma unidade obriga o operador a escolher qual é. Aqui não faz sentido
perguntar — na contagem o que importa é *quantas* unidades daquele material
existem fisicamente. Cada leitura consome uma unidade ainda não contada, e a
leitura que sobra quando todas já foram contadas vira excedente.
"""

from __future__ import annotations

from ..config import FARMACIAS, rotulo_farmacia
from ..domain import (
    BAIXADO, DEVOLVIDO_FORNECEDOR, DIVERGENCIA, EM_ESTOQUE_FARMACIA,
    EM_ESTOQUE_RECEBIMENTO, SEPARADO, UTILIZADO, rotulo,
)
from ..utils import normalizar_codigo, texto
from .. import db, log

LOCAL_ALMOXARIFADO = "almoxarifado"

# Situações de uma leitura. As quatro últimas são as pendências do relatório.
CONFERE = "confere"
LOCAL_DIVERGENTE = "local_divergente"
NAO_DEVERIA_EXISTIR = "nao_deveria_existir"
EXCEDENTE = "excedente"
DESCONHECIDO = "desconhecido"

# Material nestes estados não existe mais fisicamente para o estoque: se
# aparecer na contagem, ou a baixa/uso foi registrada errado, ou o material
# físico não deveria estar ali.
ESTADOS_FINAIS = (UTILIZADO, BAIXADO, DEVOLVIDO_FORNECEDOR)

SITUACOES = {
    CONFERE: "Confere",
    LOCAL_DIVERGENTE: "Está em outro lugar no sistema",
    NAO_DEVERIA_EXISTIR: "O sistema já deu baixa neste material",
    EXCEDENTE: "Apareceu mais unidade do que o sistema tem",
    DESCONHECIDO: "Não está cadastrado",
}

EXPLICACOES = {
    LOCAL_DIVERGENTE: (
        "Foi bipado aqui, mas para o sistema está em outro lugar. Em geral é "
        "movimentação que ninguém bipou — material que voltou da sala sem "
        "registro, ou que passou de uma farmácia para a outra."
    ),
    NAO_DEVERIA_EXISTIR: (
        "O material está fisicamente aqui, mas o sistema o considera utilizado, "
        "baixado ou devolvido ao fornecedor. É o oposto de uma falta: revise o "
        "registro que deu baixa."
    ),
    EXCEDENTE: (
        "Existe mais unidade física deste material do que o sistema tem "
        "registrado neste local. Costuma ser entrada que não foi lançada."
    ),
    DESCONHECIDO: (
        "O código bipado não corresponde a material nenhum do cadastro. "
        "Material sem cadastro não tem rastreabilidade — cadastre antes de usar."
    ),
}


def locais() -> dict[str, str]:
    """Locais que podem ser contados, na ordem em que o material caminha."""
    # Cada farmácia tem o seu estoque (Bloco e Hemodinâmica), contado à parte.
    return {LOCAL_ALMOXARIFADO: "Almoxarifado", **FARMACIAS}


def rotulo_local(local: str) -> str:
    return locais().get(texto(local), texto(local) or "—")


def _filtro_esperado(local: str) -> tuple[str, list]:
    """O que o sistema espera encontrar fisicamente naquele local.

    No almoxarifado entra também o que está como divergência: material em
    divergência continua parado lá, esperando decisão, e quem conta a prateleira
    vai encontrá-lo. Na farmácia entra o que está separado em kit: o kit ainda
    está na farmácia, na prateleira do paciente — não contá-lo faria o kit
    inteiro aparecer como falta.
    """
    if texto(local) == LOCAL_ALMOXARIFADO:
        return "u.status IN (?, ?)", [EM_ESTOQUE_RECEBIMENTO, DIVERGENCIA]
    return "u.status IN (?, ?) AND u.farmacia = ?", [EM_ESTOQUE_FARMACIA, SEPARADO, texto(local)]


# =========================================================
# ABRIR, LISTAR, ENCERRAR
# =========================================================

def _proximo_id(conn) -> str:
    """Sequencial por ano: INV-2026-001, lido e gravado na transação do chamador."""
    ano = db.agora()[:4]
    prefixo = f"INV-{ano}-"
    ultimo = conn.execute(
        """SELECT COALESCE(MAX(CAST(substr(id_inventario, ?) AS INTEGER)), 0)
           FROM inventarios WHERE id_inventario LIKE ?""",
        (len(prefixo) + 1, f"{prefixo}%"),
    ).fetchone()[0]
    return f"{prefixo}{int(ultimo) + 1:03d}"


def abrir(local: str, usuario: str, observacao: str = "") -> tuple[bool, str, str]:
    local = texto(local)
    if local not in locais():
        return False, "Escolha o local a contar.", ""

    aberto = db.consultar_um(
        "SELECT id_inventario FROM inventarios WHERE local = ? AND status = 'aberto'",
        (local,))
    if aberto:
        # Duas contagens abertas no mesmo local se atrapalhariam: cada leitura
        # iria para uma delas e as duas terminariam incompletas.
        return False, (f"Já existe uma contagem aberta em {rotulo_local(local)} "
                       f"({aberto['id_inventario']}). Continue essa, ou encerre-a antes "
                       f"de começar outra."), aberto["id_inventario"]

    with db.transacao() as conn:
        id_inventario = _proximo_id(conn)
        conn.execute(
            """INSERT INTO inventarios (id_inventario, local, status, observacao,
                                        criado_em, criado_por)
               VALUES (?,?,'aberto',?,?,?)""",
            (id_inventario, local, texto(observacao), db.agora(), texto(usuario)),
        )
    log.info(f"inventário aberto · {id_inventario} · local={local}", usuario)
    return True, f"Contagem {id_inventario} aberta em {rotulo_local(local)}.", id_inventario


def buscar(id_inventario: str) -> dict | None:
    linha = db.consultar_um(
        "SELECT * FROM inventarios WHERE id_inventario = ?", (texto(id_inventario),))
    if linha:
        linha["local_rotulo"] = rotulo_local(linha["local"])
    return linha


def listar(limite: int = 50) -> list[dict]:
    linhas = db.consultar(
        """SELECT i.*,
                  (SELECT COUNT(*) FROM inventario_leituras l
                    WHERE l.id_inventario = i.id_inventario) AS leituras
           FROM inventarios i ORDER BY i.criado_em DESC LIMIT ?""", (limite,))
    for linha in linhas:
        linha["local_rotulo"] = rotulo_local(linha["local"])
    return linhas


def encerrar(id_inventario: str, usuario: str) -> tuple[bool, str]:
    inventario = buscar(id_inventario)
    if not inventario:
        return False, "Contagem não encontrada."
    if inventario["status"] != "aberto":
        return False, "Esta contagem já está encerrada."
    db.executar(
        """UPDATE inventarios SET status = 'encerrado', encerrado_em = ?, encerrado_por = ?
           WHERE id_inventario = ?""",
        (db.agora(), texto(usuario), inventario["id_inventario"]),
    )
    log.info(f"inventário encerrado · {inventario['id_inventario']}", usuario)
    return True, f"Contagem {inventario['id_inventario']} encerrada."


# =========================================================
# LEITURA
# =========================================================

def _contadas(id_inventario: str) -> set[str]:
    """Unidades já contadas nesta contagem (só as que conferem ou excedem)."""
    return {l["id_unidade"] for l in db.consultar(
        """SELECT id_unidade FROM inventario_leituras
           WHERE id_inventario = ? AND id_unidade IS NOT NULL""",
        (texto(id_inventario),)) if l["id_unidade"]}


def _candidatas(codigo: str) -> list[dict]:
    """Unidades que respondem ao código bipado (id, código de barras ou série).

    Mesma regra de identificação da bipagem do fluxo — o leitor é o mesmo e o
    operador não deveria descobrir que um código vale numa tela e não na outra.
    """
    return db.consultar(
        """SELECT u.id_unidade, u.codigo_barras, u.codigo_aghu, u.xProd, u.nLote,
                  u.dVal, u.numero_serie, u.fornecedor, u.status, u.farmacia,
                  u.id_atendimento, a.prontuario, a.paciente
           FROM unidades u
           LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE UPPER(u.id_unidade) = UPPER(?)
              OR gtin(u.codigo_barras) = gtin(?)
              OR (u.numero_serie IS NOT NULL AND u.numero_serie <> ''
                  AND REPLACE(u.numero_serie, ' ', '') = ?)
           ORDER BY u.criado_em""",
        (codigo, codigo, codigo),
    )


def _esperada_aqui(unidade: dict, local: str) -> bool:
    if texto(local) == LOCAL_ALMOXARIFADO:
        return unidade["status"] in (EM_ESTOQUE_RECEBIMENTO, DIVERGENCIA)
    return (unidade["status"] in (EM_ESTOQUE_FARMACIA, SEPARADO)
            and texto(unidade["farmacia"]) == texto(local))


def _formatar(unidade: dict) -> dict:
    from ..utils import data_br
    return {
        "id_unidade": unidade.get("id_unidade") or "",
        "aghu": unidade.get("codigo_aghu") or "—",
        "produto": unidade.get("xProd") or "",
        "lote": unidade.get("nLote") or "—",
        "validade": data_br(unidade.get("dVal")) or "—",
        "serie": unidade.get("numero_serie") or "",
        "fornecedor": unidade.get("fornecedor") or "—",
        "status": unidade.get("status") or "",
        "status_rotulo": rotulo(unidade.get("status") or ""),
        "paciente": unidade.get("paciente") or "",
        "prontuario": unidade.get("prontuario") or "",
    }


def bipar(id_inventario: str, codigo: str, usuario: str, quantidade: int = 1) -> dict:
    """v18.11.1: `quantidade` > 1 conta várias unidades iguais num bip (caixa fechada)
    — é o mesmo que bipar o código N vezes; o resumo diz quantas conferiram."""
    try:
        n = max(1, min(500, int(quantidade or 1)))
    except (TypeError, ValueError):
        n = 1
    if n == 1:
        return _bipar_um(id_inventario, codigo, usuario)
    resultados = [_bipar_um(id_inventario, codigo, usuario) for _ in range(n)]
    if not resultados[0].get("ok") or resultados[0].get("situacao") == DESCONHECIDO:
        primeiro = dict(resultados[0])
        if primeiro.get("situacao") == DESCONHECIDO:
            primeiro["mensagem"] += f" ({n} leituras registradas.)"
            primeiro["quantidade"] = n
        return primeiro
    por_situacao: dict[str, int] = {}
    for r in resultados:
        por_situacao[r["situacao"]] = por_situacao.get(r["situacao"], 0) + 1
    confere = por_situacao.get(CONFERE, 0)
    partes = [f"{confere} conferem"] if confere else []
    for sit, q in por_situacao.items():
        if sit != CONFERE:
            partes.append(f"{q} {sit.replace('_', ' ')}")
    pior = next((r for r in resultados if r["situacao"] != CONFERE), resultados[0])
    return {"ok": True, "situacao": CONFERE if confere == n else pior["situacao"],
            "mensagem": f"{n} unidades contadas: " + ", ".join(partes) + "."
                        + ("" if confere == n else " " + pior["mensagem"]),
            "item": resultados[0]["item"], "pendencia": confere != n,
            "quantidade": n, "por_situacao": por_situacao}


def _bipar_um(id_inventario: str, codigo: str, usuario: str) -> dict:
    """Registra uma leitura da contagem. Nunca levanta exceção para o operador."""
    inventario = buscar(id_inventario)
    if not inventario:
        return {"ok": False, "mensagem": "Contagem não encontrada."}
    if inventario["status"] != "aberto":
        return {"ok": False, "mensagem": "Esta contagem já foi encerrada — nada mais é aceito."}

    codigo = normalizar_codigo(codigo)
    if not codigo:
        return {"ok": False, "mensagem": "Bipe ou digite um código."}

    local = inventario["local"]
    candidatas = _candidatas(codigo)

    if not candidatas:
        _gravar(inventario["id_inventario"], codigo, None, DESCONHECIDO, "", usuario)
        return {"ok": True, "situacao": DESCONHECIDO,
                "mensagem": f"Código {codigo} não está cadastrado.",
                "item": {"produto": "Material sem cadastro", "aghu": "—",
                         "lote": "—", "validade": "—", "id_unidade": ""}}

    # v18.11.1: etiqueta GS1 com lote conta primeiro as unidades daquele lote
    try:
        from .. import busca, gs1
        et = busca.interpretar(codigo)
        if et and et.get("lote"):
            lido = gs1.lote_normalizado(et["lote"])
            candidatas.sort(key=lambda u: gs1.lote_normalizado(u.get("nLote")) != lido)
    except Exception:  # noqa: BLE001
        pass

    contadas = _contadas(inventario["id_inventario"])
    aqui = [u for u in candidatas if _esperada_aqui(u, local)]
    nao_contadas = [u for u in aqui if u["id_unidade"] not in contadas]

    if nao_contadas:
        unidade, situacao = nao_contadas[0], CONFERE
    elif aqui:
        # Todas as unidades deste material que o sistema tem aqui já foram
        # bipadas nesta contagem, e apareceu mais uma na mão.
        unidade, situacao = aqui[0], EXCEDENTE
    else:
        fora = [u for u in candidatas if u["id_unidade"] not in contadas] or candidatas
        unidade = fora[0]
        situacao = (NAO_DEVERIA_EXISTIR if unidade["status"] in ESTADOS_FINAIS
                    else LOCAL_DIVERGENTE)

    # O excedente guarda a unidade que ele espelha: sem isso o relatório mostraria
    # só o código bipado, e quem lê não saberia de QUAL material sobrou unidade.
    # Não há risco de inflar a contagem: essa unidade já foi contada como
    # "confere", e `conferidos` conta unidades distintas com aquela situação.
    _gravar(inventario["id_inventario"], codigo, unidade["id_unidade"],
            situacao, unidade["status"], usuario)

    item = _formatar(unidade)
    if situacao == CONFERE:
        mensagem = "Confere."
    elif situacao == EXCEDENTE:
        mensagem = (f"Unidade a mais: o sistema tem {len(aqui)} deste material em "
                    f"{rotulo_local(local)}, e esta é a {len(aqui) + 1}ª bipada.")
    elif situacao == NAO_DEVERIA_EXISTIR:
        mensagem = f"O sistema marca este material como “{item['status_rotulo']}”."
    else:
        mensagem = f"Para o sistema está como “{item['status_rotulo']}”, não aqui."

    return {"ok": True, "situacao": situacao, "mensagem": mensagem, "item": item,
            "pendencia": situacao != CONFERE}


def _gravar(id_inventario: str, codigo: str, id_unidade: str | None,
            situacao: str, status: str, usuario: str) -> None:
    db.executar(
        """INSERT INTO inventario_leituras (id_inventario, codigo_lido, id_unidade,
                                            situacao, status_no_sistema, lido_em, lido_por)
           VALUES (?,?,?,?,?,?,?)""",
        (id_inventario, codigo, id_unidade, situacao, texto(status),
         db.agora(), texto(usuario)),
    )


# =========================================================
# PROGRESSO E RELATÓRIO
# =========================================================

def progresso(id_inventario: str) -> dict:
    """Contadores da tela de contagem, enquanto ela acontece."""
    inventario = buscar(id_inventario)
    if not inventario:
        return {"esperados": 0, "conferidos": 0, "faltam": 0, "pendencias": 0}

    filtro, params = _filtro_esperado(inventario["local"])
    esperados = db.escalar(f"SELECT COUNT(*) FROM unidades u WHERE {filtro}", params) or 0
    conferidos = db.escalar(
        """SELECT COUNT(DISTINCT id_unidade) FROM inventario_leituras
           WHERE id_inventario = ? AND situacao = ?""",
        (inventario["id_inventario"], CONFERE)) or 0
    pendencias = db.escalar(
        """SELECT COUNT(*) FROM inventario_leituras
           WHERE id_inventario = ? AND situacao <> ?""",
        (inventario["id_inventario"], CONFERE)) or 0
    return {"esperados": esperados, "conferidos": conferidos,
            "faltam": max(esperados - conferidos, 0), "pendencias": pendencias}


def leituras(id_inventario: str, limite: int = 300) -> list[dict]:
    """Leituras da contagem, da mais recente para a mais antiga."""
    linhas = db.consultar(
        """SELECT l.id_leitura, l.codigo_lido, l.situacao, l.status_no_sistema, l.lido_em,
                  l.lido_por, u.id_unidade, u.codigo_aghu, u.xProd, u.nLote, u.dVal,
                  u.numero_serie, u.fornecedor, u.farmacia, a.paciente, a.prontuario,
                  COALESCE(NULLIF(u.descritivo_hospital, ''), NULLIF(m.descritivo_hospital, ''), u.xProd) AS descricao_aghu
           FROM inventario_leituras l
           LEFT JOIN unidades u ON u.id_unidade = l.id_unidade
           LEFT JOIN materiais_mestre m ON m.codigo_aghu = u.codigo_aghu
           LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE l.id_inventario = ?
           ORDER BY l.id_leitura DESC LIMIT ?""",
        (texto(id_inventario), limite),
    )
    for linha in linhas:
        linha["situacao_rotulo"] = SITUACOES.get(linha["situacao"], linha["situacao"])
        linha["status_rotulo"] = rotulo(linha["status_no_sistema"] or "")
    return linhas


def nao_encontrados(id_inventario: str) -> list[dict]:
    """O que o sistema esperava no local e não foi bipado — a falta.

    É a pendência principal do inventário, e a única que não aparece durante a
    contagem: só se sabe que faltou quando a contagem termina.
    """
    inventario = buscar(id_inventario)
    if not inventario:
        return []
    filtro, params = _filtro_esperado(inventario["local"])
    return db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.nLote, u.dVal, u.numero_serie,
                   u.fornecedor, u.status, u.farmacia, u.id_atendimento,
                   a.paciente, a.prontuario, COALESCE(NULLIF(u.descritivo_hospital, ''), NULLIF(m.descritivo_hospital, ''), u.xProd) AS descricao_aghu
            FROM unidades u
            LEFT JOIN materiais_mestre m ON m.codigo_aghu = u.codigo_aghu
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE {filtro}
              AND u.id_unidade NOT IN (
                    SELECT id_unidade FROM inventario_leituras
                     WHERE id_inventario = ? AND id_unidade IS NOT NULL)
            ORDER BY COALESCE(NULLIF(u.codigo_aghu,''),'zzz'), u.xProd, u.nLote""",
        params + [inventario["id_inventario"]],
    )


def consolidado(id_inventario: str) -> list[dict]:
    """Uma linha por material (código AGHU): quanto o sistema esperava no local,
    quanto foi encontrado na contagem, quanto faltou e quanto apareceu a mais
    (bipado aqui mas que, para o sistema, é de outro lugar, já foi baixado ou
    excede o registrado). Material sem cadastro fica numa linha à parte."""
    inventario = buscar(id_inventario)
    if not inventario:
        return []
    filtro, params = _filtro_esperado(inventario["local"])
    conferidas = {l["id_unidade"] for l in db.consultar(
        "SELECT id_unidade FROM inventario_leituras WHERE id_inventario = ? AND situacao = ?",
        (inventario["id_inventario"], CONFERE)) if l["id_unidade"]}
    por_aghu: dict[str, dict] = {}

    def linha(aghu: str, descricao: str) -> dict:
        chave = aghu or "—"
        if chave not in por_aghu:
            por_aghu[chave] = {"codigo_aghu": chave, "descricao": descricao or "",
                               "esperado": 0, "encontrado": 0, "nao_encontrado": 0, "a_mais": 0}
        elif not por_aghu[chave]["descricao"] and descricao:
            por_aghu[chave]["descricao"] = descricao
        return por_aghu[chave]

    for u in db.consultar(
            f"""SELECT u.id_unidade, u.codigo_aghu, {DESC_SQL}
                FROM unidades u LEFT JOIN materiais_mestre m ON m.codigo_aghu = u.codigo_aghu
                WHERE {filtro}""", params):
        l = linha(u["codigo_aghu"], u["descricao_aghu"])
        l["esperado"] += 1
        if u["id_unidade"] in conferidas:
            l["encontrado"] += 1
        else:
            l["nao_encontrado"] += 1
    for lt in leituras(id_inventario, limite=100000):
        if lt["situacao"] == CONFERE:
            continue
        if lt["situacao"] == DESCONHECIDO:
            l = linha("sem cadastro", "Código não cadastrado no sistema")
        else:
            l = linha(lt["codigo_aghu"], lt["descricao_aghu"])
        l["a_mais"] += 1
    linhas = sorted(por_aghu.values(), key=lambda x: (x["codigo_aghu"] in ("—", "sem cadastro"), x["codigo_aghu"]))
    for l in linhas:
        if l["nao_encontrado"] and l["a_mais"]:
            l["resultado"] = f"faltam {l['nao_encontrado']} · {l['a_mais']} a mais"
        elif l["nao_encontrado"]:
            l["resultado"] = f"faltam {l['nao_encontrado']}"
        elif l["a_mais"]:
            l["resultado"] = f"{l['a_mais']} a mais"
        else:
            l["resultado"] = "confere"
    return linhas


DESC_SQL = "COALESCE(NULLIF(u.descritivo_hospital, ''), NULLIF(m.descritivo_hospital, ''), u.xProd) AS descricao_aghu"


def relatorio(id_inventario: str) -> dict:
    """Relatório final: o resumo e cada grupo de pendência, pronto para agir.

    Cinco grupos, porque cada um pede uma ação diferente de quem lê: procurar o
    material que faltou; bipar a movimentação que ninguém registrou; revisar a
    baixa indevida; lançar a entrada que não foi lançada; cadastrar o material
    sem cadastro.
    """
    inventario = buscar(id_inventario)
    if not inventario:
        return {}

    faltando = nao_encontrados(id_inventario)
    todas = leituras(id_inventario, limite=100000)
    grupos = {
        situacao: [l for l in todas if l["situacao"] == situacao]
        for situacao in (LOCAL_DIVERGENTE, NAO_DEVERIA_EXISTIR, EXCEDENTE, DESCONHECIDO)
    }
    conferidos = [l for l in todas if l["situacao"] == CONFERE]

    return {
        "inventario": inventario,
        "resumo": progresso(id_inventario),
        "nao_encontrados": faltando,
        "grupos": grupos,
        "conferidos": conferidos,
        "consolidado": consolidado(id_inventario),
        "total_pendencias": len(faltando) + sum(len(g) for g in grupos.values()),
        "situacoes": SITUACOES,
        "explicacoes": EXPLICACOES,
    }


def consolidado_para_exportar(id_inventario: str) -> list[dict]:
    return [{"codigo_aghu": l["codigo_aghu"], "descricao_aghu": l["descricao"],
             "esperado_no_sistema": l["esperado"], "encontrado": l["encontrado"],
             "nao_encontrado": l["nao_encontrado"], "a_mais_ou_fora_do_lugar": l["a_mais"],
             "resultado": l["resultado"]} for l in consolidado(id_inventario)]


def para_exportar(id_inventario: str) -> list[dict]:
    """Uma linha por pendência, achatada — é o que se leva para conferir a pé."""
    dados = relatorio(id_inventario)
    if not dados:
        return []

    linhas: list[dict] = []
    for unidade in dados["nao_encontrados"]:
        linhas.append({
            "situacao": "Não encontrado na contagem",
            "id_unidade": unidade["id_unidade"], "codigo_aghu": unidade["codigo_aghu"],
            "xProd": unidade["xProd"], "nLote": unidade["nLote"], "dVal": unidade["dVal"],
            "numero_serie": unidade["numero_serie"], "fornecedor": unidade["fornecedor"],
            "status": unidade["status"], "paciente": unidade["paciente"] or "",
            "prontuario": unidade["prontuario"] or "", "codigo_lido": "",
        })
    for situacao, itens in dados["grupos"].items():
        for leitura in itens:
            linhas.append({
                "situacao": SITUACOES[situacao],
                "id_unidade": leitura["id_unidade"] or "",
                "codigo_aghu": leitura["codigo_aghu"] or "",
                "xProd": leitura["xProd"] or "", "nLote": leitura["nLote"] or "",
                "dVal": leitura["dVal"] or "", "numero_serie": leitura["numero_serie"] or "",
                "fornecedor": leitura["fornecedor"] or "",
                "status": leitura["status_no_sistema"] or "",
                "paciente": leitura["paciente"] or "",
                "prontuario": leitura["prontuario"] or "",
                "codigo_lido": leitura["codigo_lido"],
            })
    return linhas
