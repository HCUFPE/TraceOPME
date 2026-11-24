"""Caixa da especialidade: o estoque que anda em conjunto e só se abre na sala.

O almoxarifado monta **uma** caixa por especialidade — a caixa de ortopedia, a de
vascular. Ela não é montada de novo a cada cirurgia: existe uma vez e vai sendo
**completada** conforme o fornecedor repõe o que foi consumido. Dali ela circula:
o almoxarifado dispensa a caixa para a farmácia, a farmácia dispensa para a sala
quando é necessário, a sala confirma o recebimento e usa o material item a item,
e o que sobra volta para a farmácia dentro da mesma caixa.

Sem este módulo, cada uma dessas etapas custava 40 bipagens. Pior: a farmácia era
obrigada a "conferir" item por item uma caixa que ela fisicamente não abre, o que
produz bipagem no escuro — registro que existe no banco e não aconteceu no mundo.
É pior do que não registrar, porque parece verdade.

## A escolha de projeto

A caixa é um **contêiner**, não um item novo. As unidades lá dentro continuam com
o seu próprio `status`, igual às soltas; bipar a caixa aplica a operação a todas
elas numa transação só. Por isso os indicadores, o recall, os empenhos e o
prontuário continuam corretos sem saber que caixa existe: eles contam unidades, e
as unidades continuam lá.

O caminho oposto — dar estado à caixa e deixar os itens suspensos enquanto ela
está fechada — é mais simples de escrever e apaga justamente a resposta que
importa: *onde está o material do lote X agora?* Numa caixa fechada em trânsito,
essa pergunta continua tendo resposta aqui.

## A grade, e por que ela existe

Cada caixa tem uma **grade**: quantos itens de cada produto ela deve conter
quando está completa. Sem uma meta declarada, o sistema só saberia dizer *o que
saiu*; com ela, sabe dizer *o que falta* — que é o que o almoxarifado precisa
para comprar. A grade também pega o que o registro de uso não pega: item perdido,
retirado por vencimento, ou que nunca chegou.

A grade muda com o tempo, conforme a demanda real. Toda alteração passa por
`caixa_grade_historico`, com motivo: mudar a grade muda o que o hospital compra,
e isso não pode ser uma edição silenciosa.

## Reposição: quem faz o quê

O almoxarifado é quem decide e supre — ele vê a falta de todas as caixas, separa
o material e **destina** cada unidade a uma caixa (`unidades.caixa_destino`). A
partir daí aquele item deixa de contar como falta, porque está a caminho: sem
isso o almoxarifado veria a mesma falta na semana seguinte e mandaria material
repetido.

Quem coloca fisicamente o item na caixa é quem está com ela — a caixa vive na
farmácia, não volta ao almoxarifado para ser completada. A regra que sustenta
isso é uma só: **um item só entra na caixa se estiver na mesma situação que ela.**
Um item em estoque na farmácia entra numa caixa que está na farmácia; não entra
numa que já foi para a sala.

## Quem pode abrir

Só a sala, no uso. Um item dentro de caixa é recusado em qualquer outra operação
(ver `fluxo._selecionar`), e a mensagem diz em que caixa ele está. Fora disso, a
única saída é `retirar_item`, que exige motivo e grava evento — uma exceção com
trilha de auditoria, em vez de uma porta aberta.
"""

from .. import db, log
from ..domain import (
    EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, ESTADOS, OPERACOES,
    SEPARADO, TRANSITO_FARMACIA, TRANSITO_RETORNO, TRANSITO_SALA, EM_SALA,
    UTILIZADO, rotulo,
)
from ..config import GRADE_DAS_CAIXAS, rotulo_farmacia
from ..erros import ErroDeNegocio
from ..utils import (
    data_br, dias_para, inteiro, normalizar_codigo, padronizar_especialidade, texto,
)
from . import alertas, recall

# Prefixo reservado. Precisa ser inconfundível com código de barras de fábrica,
# porque é ele que decide, na bipagem, se o que foi lido é caixa ou item.
PREFIXO_CAIXA = "CX"

# Motivos de saída de um item da caixa, para `caixa_itens.motivo_saida`.
SAIDA_USO = "uso"
SAIDA_RETIRADA = "retirada"

# Quem é responsável pela caixa em cada situação. É este mapa que responde
# "quem pode completar a caixa agora": quem está fisicamente com ela.
MODULO_POR_STATUS = {
    EM_ESTOQUE_RECEBIMENTO: "almoxarifado",
    TRANSITO_FARMACIA: "farmacia",
    "transito_almoxarifado": "almoxarifado",
    EM_ESTOQUE_FARMACIA: "farmacia",
    SEPARADO: "farmacia",
    TRANSITO_RETORNO: "farmacia",
    TRANSITO_SALA: "sala-procedimento",
    EM_SALA: "sala-procedimento",
}

CAMPOS_CAIXA = """
    c.id_caixa, c.nome, c.especialidade, c.farmacia, c.status,
    c.id_atendimento, c.observacao, c.criado_em, c.criado_por,
    c.atualizado_em, c.atualizado_por, c.encerrada_em, c.encerrada_por
"""


class ErroDeCaixa(ErroDeNegocio):
    """Recusa de regra com mensagem pronta para o operador."""


# =========================================================
# IDENTIFICAÇÃO
# =========================================================

def e_codigo_caixa(codigo) -> bool:
    return normalizar_codigo(codigo).upper().startswith(f"{PREFIXO_CAIXA}-")


def modulo_responsavel(status: str) -> str:
    """Setor que está com a caixa agora — e que pode, portanto, completá-la."""
    return MODULO_POR_STATUS.get(texto(status), "almoxarifado")


def _sigla(especialidade: str) -> str:
    nome = padronizar_especialidade(especialidade)
    if nome.startswith("CIRURGIA ") and len(nome) > 9:
        nome = nome[9:].removeprefix("DE ")
    limpa = "".join(c for c in nome if c.isalnum())
    return limpa[:4] or "GER"


def _proximo_id(conn, especialidade: str) -> str:
    """Sequencial por especialidade: CX-ORTO-01.

    A numeração é lida e gravada dentro da transação do chamador, que já é
    `BEGIN IMMEDIATE` — então duas pessoas criando caixa ao mesmo tempo não
    recebem o mesmo número.
    """
    prefixo = f"{PREFIXO_CAIXA}-{_sigla(especialidade)}-"
    ultimo = conn.execute(
        """SELECT COALESCE(MAX(CAST(substr(id_caixa, ?) AS INTEGER)), 0)
           FROM caixas WHERE id_caixa LIKE ?""",
        (len(prefixo) + 1, f"{prefixo}%"),
    ).fetchone()[0]
    return f"{prefixo}{int(ultimo) + 1:02d}"


def _marcador(id_caixa: str) -> str:
    """Marca gravada em `eventos.observacao` para reagrupar por caixa depois.

    Não existe coluna `id_caixa` em `eventos` de propósito: `eventos` é a tabela
    imutável de auditoria da unidade, e alargá-la a cada agrupamento novo é como
    o esquema da versão 13 se espalhou. A marca em texto resolve a consulta de
    tela sem tocar no núcleo.
    """
    return f"[{texto(id_caixa)}]"


# =========================================================
# CONSULTA
# =========================================================

def buscar(id_caixa: str) -> dict | None:
    return db.consultar_um(
        f"""SELECT {CAMPOS_CAIXA},
                   (SELECT COUNT(*) FROM unidades u WHERE u.id_caixa = c.id_caixa) AS total,
                   (SELECT COALESCE(SUM(quantidade),0) FROM caixa_grade g
                     WHERE g.id_caixa = c.id_caixa) AS padrao,
                   a.prontuario, a.paciente, a.sala, a.data_procedimento
            FROM caixas c
            LEFT JOIN atendimentos a ON a.id_atendimento = c.id_atendimento
            WHERE UPPER(c.id_caixa) = UPPER(?)""",
        (texto(id_caixa),),
    )


def conteudo(id_caixa: str) -> list[dict]:
    """Itens que estão dentro da caixa agora, na ordem do código AGHU."""
    return db.consultar(
        """SELECT u.*, ci.entrou_em
           FROM unidades u
           JOIN caixa_itens ci ON ci.id_unidade = u.id_unidade AND ci.saiu_em IS NULL
           WHERE u.id_caixa = ?
           ORDER BY COALESCE(NULLIF(u.codigo_aghu,''),'zzz'), u.xProd, u.dVal""",
        (texto(id_caixa),),
    )


def saidas(id_caixa: str, limite: int = 200, de: str = "", ate: str = "") -> list[dict]:
    """O que já saiu da caixa — usado no paciente, retirado ou baixado.
    v18.11.7: filtro por período (datas ISO AAAA-MM-DD, inclusivas)."""
    filtro, params = "", [texto(id_caixa)]
    if texto(de):
        filtro += " AND substr(ci.saiu_em, 1, 10) >= ?"
        params.append(texto(de)[:10])
    if texto(ate):
        filtro += " AND substr(ci.saiu_em, 1, 10) <= ?"
        params.append(texto(ate)[:10])
    return db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.descritivo_hospital, u.nLote, u.dVal, u.status,
                  ci.saiu_em, ci.saiu_por, ci.motivo_saida, a.prontuario, a.sala
           FROM caixa_itens ci
           JOIN unidades u ON u.id_unidade = ci.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE ci.id_caixa = ? AND ci.saiu_em IS NOT NULL{filtro}
           ORDER BY ci.saiu_em DESC LIMIT ?""",
        (*params, limite),
    )


def caixa_da_unidade(id_unidade: str) -> dict | None:
    linha = db.consultar_um(
        "SELECT id_caixa FROM unidades WHERE id_unidade = ?", (texto(id_unidade),))
    if not linha or not texto(linha.get("id_caixa")):
        return None
    return buscar(linha["id_caixa"])


def caixas_por_onde_passou(id_unidade: str) -> list[dict]:
    """Caixas em que esta unidade já esteve, com o motivo da saída."""
    return db.consultar(
        """SELECT ci.id_caixa, ci.entrou_em, ci.saiu_em, ci.motivo_saida,
                  c.nome, c.especialidade
           FROM caixa_itens ci
           JOIN caixas c ON c.id_caixa = ci.id_caixa
           WHERE ci.id_unidade = ?
           ORDER BY ci.entrou_em DESC""",
        (texto(id_unidade),),
    )


def listar(status: str = "", termo: str = "", especialidade: str = "",
           incluir_encerradas: bool = False, limite: int = 200) -> list[dict]:
    condicoes: list[str] = []
    params: list = []

    if not incluir_encerradas:
        condicoes.append("c.encerrada_em IS NULL")
    if texto(status):
        condicoes.append("c.status = ?")
        params.append(texto(status))
    if texto(especialidade):
        condicoes.append("c.especialidade = ?")
        params.append(padronizar_especialidade(especialidade))
    if texto(termo):
        condicoes.append("(c.id_caixa LIKE ? OR c.nome LIKE ? OR c.especialidade LIKE ?)")
        curinga = f"%{texto(termo)}%"
        params += [curinga, curinga, curinga]

    onde = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    params.append(limite)
    return db.consultar(
        f"""SELECT {CAMPOS_CAIXA},
                   (SELECT COUNT(*) FROM unidades u WHERE u.id_caixa = c.id_caixa) AS total,
                   (SELECT COALESCE(SUM(quantidade),0) FROM caixa_grade g
                     WHERE g.id_caixa = c.id_caixa) AS padrao,
                   a.prontuario, a.sala
            FROM caixas c
            LEFT JOIN atendimentos a ON a.id_atendimento = c.id_atendimento
            {onde}
            ORDER BY c.especialidade, c.id_caixa
            LIMIT ?""",
        params,
    )


def historico(id_caixa: str, limite: int = 300) -> list[dict]:
    """Movimentos das unidades desta caixa, agrupados por leitura da caixa.

    Cada bipagem de caixa grava um evento por unidade — o histórico individual
    tem que continuar completo, é o que o recall lê. Aqui esses eventos são
    reagrupados para a tela não mostrar 40 linhas iguais.
    """
    return db.consultar(
        """SELECT e.tipo, e.status_anterior, e.status_novo, e.usuario,
                  substr(e.data_evento, 1, 16) AS quando,
                  COUNT(*) AS itens, MAX(e.motivo) AS motivo
           FROM eventos e
           WHERE e.observacao LIKE ?
           GROUP BY e.tipo, e.status_anterior, e.status_novo, e.usuario, quando
           ORDER BY quando DESC LIMIT ?""",
        (f"%{_marcador(id_caixa)}%", limite),
    )


# =========================================================
# GRADE (COMPOSIÇÃO ESPERADA)
# =========================================================

def grade(id_caixa: str) -> list[dict]:
    return db.consultar(
        """SELECT codigo_aghu, descricao, quantidade, observacao,
                  atualizado_em, atualizado_por
           FROM caixa_grade WHERE id_caixa = ?
           ORDER BY codigo_aghu""",
        (texto(id_caixa),),
    )


def grade_historico(id_caixa: str, limite: int = 100) -> list[dict]:
    return db.consultar(
        """SELECT codigo_aghu, descricao, quantidade_anterior, quantidade_nova,
                  motivo, data_registro, usuario
           FROM caixa_grade_historico WHERE id_caixa = ?
           ORDER BY id_registro DESC LIMIT ?""",
        (texto(id_caixa), limite),
    )


def definir_grade(id_caixa: str, dados: dict, usuario: str) -> tuple[bool, str]:
    """Cria ou altera uma linha da grade. Quantidade 0 remove a linha.

    Toda alteração exige motivo: mudar a grade muda o que o hospital compra e o
    que a farmácia cobra do almoxarifado. É decisão, não digitação.
    """
    if not GRADE_DAS_CAIXAS:
        return False, "A grade das caixas está desligada neste sistema."

    codigo = normalizar_codigo(dados.get("codigo_aghu")).upper()
    descricao = texto(dados.get("descricao"))
    quantidade = inteiro(dados.get("quantidade"), -1)
    motivo = texto(dados.get("motivo"))

    if not codigo:
        return False, "Informe o código AGHU do material."
    if quantidade < 0:
        return False, "Informe uma quantidade válida (0 remove o item da grade)."
    if quantidade and not descricao:
        return False, "Informe a descrição do material."
    if len(motivo) < 5:
        return False, "Informe o motivo da alteração da grade."

    caixa = buscar(id_caixa)
    if not caixa:
        return False, "Caixa não encontrada."

    anterior = db.consultar_um(
        "SELECT quantidade, descricao FROM caixa_grade WHERE id_caixa = ? AND codigo_aghu = ?",
        (caixa["id_caixa"], codigo),
    )
    qtd_anterior = anterior["quantidade"] if anterior else None
    if qtd_anterior == quantidade:
        return False, "A quantidade informada é a que já está na grade."

    with db.transacao() as conn:
        if quantidade == 0:
            conn.execute("DELETE FROM caixa_grade WHERE id_caixa = ? AND codigo_aghu = ?",
                         (caixa["id_caixa"], codigo))
        else:
            conn.execute(
                """INSERT INTO caixa_grade
                   (id_caixa, codigo_aghu, descricao, quantidade, observacao,
                    atualizado_em, atualizado_por)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(id_caixa, codigo_aghu) DO UPDATE SET
                     descricao = excluded.descricao,
                     quantidade = excluded.quantidade,
                     observacao = excluded.observacao,
                     atualizado_em = excluded.atualizado_em,
                     atualizado_por = excluded.atualizado_por""",
                (caixa["id_caixa"], codigo, descricao or (anterior or {}).get("descricao", ""),
                 quantidade, texto(dados.get("observacao")), db.agora(), usuario),
            )
        conn.execute(
            """INSERT INTO caixa_grade_historico
               (id_caixa, codigo_aghu, descricao, quantidade_anterior, quantidade_nova,
                motivo, data_registro, usuario)
               VALUES (?,?,?,?,?,?,?,?)""",
            (caixa["id_caixa"], codigo, descricao, qtd_anterior, quantidade,
             motivo, db.agora(), usuario),
        )

    log.info(f"grade da caixa alterada · {caixa['id_caixa']} · {codigo} · "
             f"{qtd_anterior} → {quantidade} · motivo={motivo}", usuario)
    if quantidade == 0:
        return True, f"{codigo} removido da grade da caixa."
    return True, f"Grade atualizada: {codigo} passa a ter {quantidade} unidade(s)."


# =========================================================
# REPOSIÇÃO
# =========================================================

def falta(id_caixa: str) -> list[dict]:
    """O que falta para a caixa ficar completa, produto a produto.

    `falta = grade − dentro da caixa − a caminho dela`.

    O "a caminho" é o que impede o almoxarifado de mandar material repetido:
    depois de destinar as unidades à caixa, aquela falta some da lista mesmo que
    o item ainda não tenha entrado fisicamente.

    Com a grade desligada (`config.GRADE_DAS_CAIXAS`) não existe falta: tudo que
    deriva dela — reposição, alerta ao almoxarifado, "faltando" — fica quieto por
    passar por aqui.
    """
    if not GRADE_DAS_CAIXAS:
        return []
    return db.consultar(
        """SELECT g.codigo_aghu, g.descricao, g.quantidade AS padrao,
                  (SELECT COUNT(*) FROM unidades u
                    WHERE u.id_caixa = g.id_caixa
                      AND UPPER(COALESCE(u.codigo_aghu,'')) = g.codigo_aghu) AS dentro,
                  (SELECT COUNT(*) FROM unidades u
                    WHERE u.caixa_destino = g.id_caixa AND u.id_caixa IS NULL
                      AND UPPER(COALESCE(u.codigo_aghu,'')) = g.codigo_aghu) AS a_caminho
           FROM caixa_grade g
           WHERE g.id_caixa = ?
           ORDER BY g.codigo_aghu""",
        (texto(id_caixa),),
    )


def falta_pendente(id_caixa: str) -> list[dict]:
    """Só as linhas em que ainda falta alguma coisa."""
    linhas = []
    for linha in falta(id_caixa):
        restante = linha["padrao"] - linha["dentro"] - linha["a_caminho"]
        if restante > 0:
            linhas.append(linha | {"falta": restante})
    return linhas


def reposicao_geral() -> list[dict]:
    """A lista de compras do almoxarifado: o que falta em todas as caixas."""
    pendencias = []
    for caixa in listar():
        for linha in falta_pendente(caixa["id_caixa"]):
            pendencias.append(linha | {
                "id_caixa": caixa["id_caixa"],
                "caixa": caixa["nome"],
                "especialidade": caixa["especialidade"],
                "status_caixa": caixa["status"],
            })
    return sorted(pendencias, key=lambda p: (-p["falta"], p["id_caixa"], p["codigo_aghu"]))


def destinar(id_caixa: str, codigo: str, usuario: str) -> dict:
    """Marca uma unidade solta como destinada a uma caixa.

    Feito pelo almoxarifado ao separar a reposição. A unidade continua se movendo
    item a item pelo fluxo normal (envio, conferência) até chegar onde a caixa
    está; ali alguém a coloca dentro com `adicionar_item`.
    """
    codigo = normalizar_codigo(codigo)
    if not codigo:
        return {"ok": False, "mensagem": "Bipe ou digite um código."}

    try:
        with db.transacao() as conn:
            caixa = _caixa_ativa(conn, id_caixa)
            unidade = _unidade_livre(conn, codigo)
            if texto(unidade.get("caixa_destino")) == caixa["id_caixa"]:
                raise ErroDeCaixa(f"Este item já está destinado à caixa {caixa['id_caixa']}.")
            if texto(unidade.get("caixa_destino")):
                raise ErroDeCaixa(
                    f"Este item já está destinado à caixa {unidade['caixa_destino']}.")

            conn.execute(
                """UPDATE unidades SET caixa_destino = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (caixa["id_caixa"], db.agora(), usuario, unidade["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="destinar_caixa", id_unidade=unidade["id_unidade"],
                status_anterior=unidade["status"], status_novo=unidade["status"],
                usuario=usuario, motivo=f"Reposição da caixa {caixa['id_caixa']}",
                observacao=_marcador(caixa["id_caixa"]),
            )
    except ErroDeNegocio as recusa:
        return {"ok": False, "mensagem": str(recusa)}
    except Exception as falha_tecnica:
        log.erro(f"falha ao destinar à caixa · caixa={id_caixa} · codigo={codigo}",
                 usuario, falha_tecnica)
        return {"ok": False, "mensagem": ("Não foi possível registrar por uma falha do "
                                          "sistema. Nada foi gravado. Tente novamente.")}

    return {
        "ok": True,
        "mensagem": f"{unidade['xProd']} destinado à caixa {caixa['id_caixa']}.",
        "item": unidade,
        "alertas": _avisos_do_item(unidade),
        "pendente": len(falta_pendente(caixa["id_caixa"])),
    }


def a_caminho(id_caixa: str) -> list[dict]:
    """Unidades destinadas à caixa que ainda não entraram nela."""
    return db.consultar(
        """SELECT * FROM unidades
           WHERE caixa_destino = ? AND id_caixa IS NULL
           ORDER BY COALESCE(NULLIF(codigo_aghu,''),'zzz'), dVal""",
        (texto(id_caixa),),
    )


def alertar_reposicao(id_caixa: str, usuario: str, contexto: str = "") -> None:
    """Avisa o almoxarifado do que passou a faltar. Chamado no registro de uso.

    A lista de falta já responde isso a qualquer momento — mas quem tem que
    comprar não fica olhando tela. O alerta é o empurrão; a lista é a consulta.
    """
    pendentes = falta_pendente(id_caixa)
    if not pendentes:
        return
    caixa = buscar(id_caixa)
    linhas = [f"  · {p['codigo_aghu']} {p['descricao']} — faltam {p['falta']} "
              f"(padrão {p['padrao']}, na caixa {p['dentro']})"
              for p in pendentes[:15]]
    if len(pendentes) > 15:
        linhas.append(f"  · … e mais {len(pendentes) - 15} item(ns).")
    cabecalho = f"{caixa['nome']} — {caixa['especialidade']}."
    if texto(contexto):
        cabecalho += f"\n{texto(contexto)}"
    alertas.criar(
        modulo_destino="almoxarifado",
        titulo=f"Caixa {id_caixa} precisa de reposição",
        mensagem=(f"{cabecalho}\n{len(pendentes)} produto(s) abaixo da grade:\n"
                  + "\n".join(linhas)),
        usuario=usuario,
        link="/almoxarifado/reposicao",
    )


# =========================================================
# MONTAGEM E COMPLEMENTO
# =========================================================

def criar(dados: dict, usuario: str) -> tuple[bool, str, str]:
    nome = texto(dados.get("nome"))
    especialidade = padronizar_especialidade(dados.get("especialidade"))

    if not nome:
        return False, "Dê um nome à caixa (ex.: “Caixa de Ortopedia”).", ""
    if not especialidade:
        return False, "Informe a especialidade — ela compõe o código da caixa.", ""

    with db.transacao() as conn:
        id_caixa = _proximo_id(conn, especialidade)
        conn.execute(
            """INSERT INTO caixas
               (id_caixa, nome, especialidade, status, observacao,
                criado_em, criado_por, atualizado_em, atualizado_por)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (id_caixa, nome, especialidade, EM_ESTOQUE_RECEBIMENTO,
             texto(dados.get("observacao")), db.agora(), usuario, db.agora(), usuario),
        )
        db.registrar_evento(
            conn, tipo="criar_caixa", status_novo=EM_ESTOQUE_RECEBIMENTO,
            usuario=usuario, motivo=f"Caixa {nome} criada",
            observacao=_marcador(id_caixa),
        )
    log.info(f"caixa criada · {id_caixa} · especialidade={especialidade}", usuario)
    return True, (f"Caixa {id_caixa} criada. Defina a grade — quantos itens de cada "
                  f"produto ela deve ter — e depois bipe o material."), id_caixa


def adicionar_item(id_caixa: str, codigo: str, usuario: str) -> dict:
    """Coloca uma unidade dentro da caixa. É a montagem e é o complemento.

    Não há duas operações porque não há duas coisas: a caixa é montada uma vez e
    completada para sempre. A regra é sempre a mesma — o item precisa estar na
    mesma situação da caixa.
    """
    codigo = normalizar_codigo(codigo)
    if not codigo:
        return {"ok": False, "mensagem": "Bipe ou digite um código."}
    from . import caixas_sala
    turno = caixas_sala.ativo_da_caixa(id_caixa)
    if turno:
        return {"ok": False, "mensagem": (f"A caixa está na {turno['local']} ({turno['status_rotulo']}). "
                                          f"Reabasteça depois que ela voltar e for conferida.")}

    try:
        with db.transacao() as conn:
            caixa = _caixa_ativa(conn, id_caixa)
            unidade = _unidade_para_a_caixa(conn, codigo, caixa)

            conn.execute(
                """UPDATE unidades
                   SET id_caixa = ?, caixa_destino = NULL, farmacia = COALESCE(?, farmacia),
                       id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (caixa["id_caixa"], caixa["farmacia"], caixa["id_atendimento"],
                 db.agora(), usuario, unidade["id_unidade"]),
            )
            conn.execute(
                """INSERT OR REPLACE INTO caixa_itens (id_caixa, id_unidade, entrou_em, entrou_por)
                   VALUES (?,?,?,?)""",
                (caixa["id_caixa"], unidade["id_unidade"], db.agora(), usuario),
            )
            db.registrar_evento(
                conn, tipo="entrar_caixa", id_unidade=unidade["id_unidade"],
                status_anterior=unidade["status"], status_novo=unidade["status"],
                usuario=usuario, motivo=f"Colocado na caixa {caixa['id_caixa']}",
                observacao=_marcador(caixa["id_caixa"]),
            )
    except ErroDeNegocio as recusa:
        log.info(f"entrada na caixa recusada · caixa={id_caixa} · codigo={codigo} · "
                 f"{recusa}", usuario)
        return {"ok": False, "mensagem": str(recusa)}
    except Exception as falha_tecnica:
        log.erro(f"falha ao completar caixa · caixa={id_caixa} · codigo={codigo}",
                 usuario, falha_tecnica)
        return {"ok": False, "mensagem": ("Não foi possível registrar por uma falha do "
                                          "sistema. Nada foi gravado. Tente novamente.")}

    pendentes = falta_pendente(caixa["id_caixa"])
    return {
        "ok": True,
        "mensagem": f"{unidade['xProd']} colocado na caixa.",
        "item": unidade,
        "alertas": _avisos_do_item(unidade),
        "total": db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?",
                            (caixa["id_caixa"],)),
        "falta": sum(p["falta"] for p in pendentes),
    }


def _caixa_ativa(conn, id_caixa: str) -> dict:
    linha = conn.execute(
        "SELECT * FROM caixas WHERE UPPER(id_caixa) = UPPER(?)", (texto(id_caixa),)
    ).fetchone()
    if not linha:
        raise ErroDeCaixa(f"Caixa {texto(id_caixa)} não encontrada.")
    caixa = dict(linha)
    if caixa["encerrada_em"]:
        raise ErroDeCaixa("Esta caixa foi encerrada e não pode ser movimentada.")
    return caixa


def _unidade_livre(conn, codigo: str) -> dict:
    """Unidade solta que responde ao código — para destinar à reposição."""
    candidatas = [dict(r) for r in conn.execute(
        """SELECT * FROM unidades
           WHERE UPPER(id_unidade) = UPPER(?)
              OR gtin(codigo_barras) = gtin(?)
              OR (numero_serie IS NOT NULL AND numero_serie <> ''
                  AND REPLACE(numero_serie, ' ', '') = ?)
           ORDER BY CASE WHEN dVal IS NULL OR dVal = '' THEN 1 ELSE 0 END,
                    dVal, criado_em""",
        (codigo, codigo, codigo),
    ).fetchall()]
    if not candidatas:
        raise ErroDeCaixa(
            "Código não encontrado. Confirme se o item foi cadastrado no Almoxarifado.")
    soltas = [c for c in candidatas if not texto(c.get("id_caixa"))]
    if not soltas:
        raise ErroDeCaixa(f"Este item já está dentro da caixa {candidatas[0]['id_caixa']}.")
    sem_destino = [c for c in soltas if not texto(c.get("caixa_destino"))] or soltas
    return sem_destino[0]  # FEFO: a lista já vem ordenada pela validade


def _unidade_para_a_caixa(conn, codigo: str, caixa: dict) -> dict:
    """Escolhe a unidade que entra na caixa, ou explica por que nenhuma pode.

    FEFO deixa de ser aplicado na saída quando o material anda em caixa — quem
    bipa a caixa leva o que está lá dentro, e ponto. Por isso o FEFO passa a ser
    responsabilidade *daqui*: é ao completar a caixa que a escolha do lote
    acontece.
    """
    candidatas = [dict(r) for r in conn.execute(
        """SELECT * FROM unidades
           WHERE UPPER(id_unidade) = UPPER(?)
              OR gtin(codigo_barras) = gtin(?)
              OR (numero_serie IS NOT NULL AND numero_serie <> ''
                  AND REPLACE(numero_serie, ' ', '') = ?)
           ORDER BY CASE WHEN dVal IS NULL OR dVal = '' THEN 1 ELSE 0 END,
                    dVal, criado_em""",
        (codigo, codigo, codigo),
    ).fetchall()]

    if not candidatas:
        raise ErroDeCaixa(
            "Código não encontrado. Confirme se o item foi cadastrado no Almoxarifado.")

    livres = [c for c in candidatas if not texto(c.get("id_caixa"))]
    if not livres:
        raise ErroDeCaixa(f"Este item já está na caixa {candidatas[0]['id_caixa']}.")

    # A regra que faz a reposição funcionar onde a caixa estiver: item e caixa
    # precisam estar na mesma situação. Um item em estoque na farmácia entra
    # numa caixa que está na farmácia; não entra numa que já subiu para a sala.
    # Estoque do almoxarifado e o da farmácia são ambos "parados": a caixa de
    # consignado pode receber item de qualquer um dos dois.
    parados = (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA)
    # nov/2026: caixa do almoxarifado só recebe material do estoque do almoxarifado;
    # caixa a caminho da farmácia não recebe nada até a ciência.
    local_caixa = texto(caixa.get("local"))
    if local_caixa == "transito":
        raise ErroDeCaixa("A caixa está a caminho da farmácia. Complete depois da ciência do recebimento.")
    if local_caixa == "almoxarifado":
        livres_almox = [c for c in livres if c["status"] == EM_ESTOQUE_RECEBIMENTO]
        if not livres_almox:
            raise ErroDeCaixa("A caixa está no almoxarifado: só entra material que está no estoque do almoxarifado.")
        livres = livres_almox
    if local_caixa != "almoxarifado" and caixa["status"] in parados:
        # v18.11.4: caixa na farmácia só recebe o estoque da farmácia — o material do
        # almoxarifado chega unitário (envio + ciência) e só então monta/repõe a caixa.
        livres_farm = [c for c in livres if c["status"] == EM_ESTOQUE_FARMACIA]
        if not livres_farm:
            raise ErroDeCaixa(
                f"Este material está como “{rotulo(livres[0]['status'])}”. A caixa está na farmácia: "
                f"só entra material do estoque da farmácia. Envie o item para a farmácia, dê ciência "
                f"do recebimento e bipe de novo.")
        livres = livres_farm
    juntos = [c for c in livres if c["status"] == caixa["status"]
              or (c["status"] in parados and caixa["status"] in parados)]
    if not juntos:
        atual = rotulo(livres[0]["status"])
        raise ErroDeCaixa(
            f"A caixa está como “{rotulo(caixa['status'])}” e este item está como "
            f"“{atual}”. Para entrar na caixa, o item precisa estar no mesmo lugar "
            f"que ela — envie o material até onde a caixa está e bipe de novo."
        )

    if caixa["status"] in (EM_ESTOQUE_FARMACIA, SEPARADO) and texto(caixa.get("farmacia")):
        da_farmacia = [c for c in juntos if texto(c.get("farmacia")) == caixa["farmacia"]]
        if not da_farmacia:
            raise ErroDeCaixa(
                f"Este material pertence a outro estoque. A caixa está na "
                f"{rotulo_farmacia(caixa['farmacia'])}."
            )
        juntos = da_farmacia

    validos = [c for c in juntos
               if not texto(c.get("dVal")) or (dias_para(c.get("dVal")) or 0) >= 0]
    if not validos:
        vencido = juntos[0]
        raise ErroDeCaixa(
            f"Material com validade vencida em {data_br(vencido.get('dVal'))}. Não pode "
            f"entrar na caixa. Registre a baixa em Almoxarifado → Baixar item."
        )

    # Preferir o que já foi destinado a esta caixa: é a reposição chegando.
    destinados = [c for c in validos if texto(c.get("caixa_destino")) == caixa["id_caixa"]]
    escolhida = (destinados or validos)[0]

    bloqueio = recall.bloqueio_do_item(escolhida.get("nLote"), escolhida.get("codigo_aghu"))
    if bloqueio:
        raise ErroDeCaixa(
            f"Lote {escolhida.get('nLote')} BLOQUEADO: {bloqueio['motivo']}. "
            f"Não coloque este material na caixa."
        )
    return escolhida


def _avisos_do_item(unidade: dict) -> list[str]:
    """Avisos que só fazem sentido ao pôr material na caixa.

    O principal é o FEFO: se ficou na prateleira uma unidade do mesmo produto
    vencendo antes desta, quem completa a caixa precisa saber *agora* — depois
    que a caixa sai, o item mais velho fica parado até vencer.
    """
    avisos: list[str] = []
    dias = dias_para(unidade.get("dVal"))
    if dias is not None and dias <= 90:
        avisos.append(f"Validade em {data_br(unidade.get('dVal'))} — {dias} dia(s).")
    if not texto(unidade.get("dVal")):
        avisos.append("Item sem data de validade cadastrada.")

    mais_velho = db.consultar_um(
        """SELECT nLote, dVal FROM unidades
           WHERE status = ? AND id_caixa IS NULL AND gtin(codigo_barras) = gtin(?)
             AND dVal IS NOT NULL AND dVal <> '' AND dVal < ?
           ORDER BY dVal LIMIT 1""",
        (unidade.get("status"), unidade.get("codigo_barras"),
         texto(unidade.get("dVal")) or "9999-12-31"),
    )
    if mais_velho:
        avisos.append(
            f"FEFO: há uma unidade deste produto (lote {mais_velho.get('nLote') or '—'}) "
            f"vencendo antes, em {data_br(mais_velho.get('dVal'))}. Prefira aquela."
        )
    return avisos


def retirar_item(id_caixa: str, id_unidade: str, usuario: str,
                 motivo: str) -> tuple[bool, str]:
    """Tira um item da caixa fora do fluxo de uso. v18.11.3: motivo opcional
    (montagem/ajuste da caixa); fica registrado na auditoria."""
    motivo = texto(motivo) or "retirado na montagem/ajuste da caixa"
    from . import caixas_sala
    if caixas_sala.ativo_da_caixa(id_caixa):
        return False, "A caixa está fora da farmácia (na sala). Retire itens depois que ela voltar e for conferida."

    try:
        with db.transacao() as conn:
            linha = conn.execute(
                "SELECT status, xProd, id_caixa FROM unidades WHERE id_unidade = ?",
                (texto(id_unidade),)).fetchone()
            if not linha:
                raise ErroDeCaixa("Item não encontrado.")
            if texto(linha["id_caixa"]).upper() != texto(id_caixa).upper():
                raise ErroDeCaixa("Este item não está nesta caixa.")
            _registrar_saida(conn, texto(id_unidade), usuario, SAIDA_RETIRADA, motivo)
            db.registrar_evento(
                conn, tipo="retirar_da_caixa", id_unidade=texto(id_unidade),
                status_anterior=linha["status"], status_novo=linha["status"],
                usuario=usuario, motivo=motivo,
                observacao=f"{_marcador(id_caixa)} retirado da caixa",
            )
            produto = linha["xProd"]
    except ErroDeNegocio as recusa:
        return False, str(recusa)

    log.aviso(f"item retirado da caixa · caixa={id_caixa} · unidade={id_unidade} · "
              f"motivo={motivo}", usuario)
    return True, f"{produto} retirado da caixa e voltou a ser um item solto."


def _registrar_saida(conn, id_unidade: str, usuario: str, motivo_saida: str,
                     motivo: str = "") -> None:
    conn.execute(
        """UPDATE caixa_itens SET saiu_em = ?, saiu_por = ?, motivo_saida = ?
           WHERE id_unidade = ? AND saiu_em IS NULL""",
        (db.agora(), usuario, f"{motivo_saida}: {motivo}".strip(": "), id_unidade),
    )
    conn.execute("UPDATE unidades SET id_caixa = NULL WHERE id_unidade = ?", (id_unidade,))


# =========================================================
# A CAIXA ACOMPANHA O KIT
#
# A tela de revisão do kit (dispensar, cancelar, trocar de paciente) move os
# itens um a um, direto no banco — ela nasceu antes das caixas. Sem isto, os
# itens de uma caixa iam para a sala e a caixa ficava registrada como
# "Separado", e a devolução pela caixa era recusada. Estas funções rodam dentro
# da transação da tela do kit, para itens e caixa mudarem juntos.
# =========================================================

MOTIVO_FORA_DO_KIT = "Desmarcado na dispensação do kit — não foi para a sala."


def _atualizar_caixa(conn, id_caixa: str, status: str, id_atendimento, usuario: str) -> None:
    conn.execute(
        """UPDATE caixas SET status = ?, id_atendimento = ?,
                             atualizado_em = ?, atualizado_por = ?
           WHERE id_caixa = ?""",
        (status, id_atendimento, db.agora(), usuario, id_caixa),
    )


def _por_caixa(itens: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for item in itens:
        if texto(item.get("id_caixa")):
            grupos.setdefault(item["id_caixa"], []).append(item)
    return grupos


def acompanhar_dispensa_do_kit(conn, *, itens_kit: list[dict], ids_enviados: set[str],
                               id_atendimento: str, usuario: str) -> None:
    """Depois de `fluxo.dispensar_kit` mover os itens: a caixa vai junto.

    Se algo da caixa foi para a sala, a caixa foi — e o que foi desmarcado sai
    dela, porque fisicamente ficou na farmácia. Se nada da caixa foi, ela volta
    inteira ao estoque, como os itens (que a tela do kit já devolveu).
    """
    for id_caixa, itens in _por_caixa(itens_kit).items():
        foram = [i for i in itens if i["id_unidade"] in ids_enviados]
        ficaram = [i for i in itens if i["id_unidade"] not in ids_enviados]
        if foram:
            for item in ficaram:
                _registrar_saida(conn, item["id_unidade"], usuario, SAIDA_RETIRADA,
                                 MOTIVO_FORA_DO_KIT)
                db.registrar_evento(
                    conn, tipo="retirar_da_caixa", id_unidade=item["id_unidade"],
                    id_atendimento=id_atendimento, status_anterior=SEPARADO,
                    status_novo=EM_ESTOQUE_FARMACIA, usuario=usuario,
                    motivo=MOTIVO_FORA_DO_KIT,
                    observacao=f"{_marcador(id_caixa)} fora na dispensação do kit",
                )
            _atualizar_caixa(conn, id_caixa, EM_SALA, id_atendimento, usuario)
        else:
            _atualizar_caixa(conn, id_caixa, EM_ESTOQUE_FARMACIA, None, usuario)


def acompanhar_cancelamento_do_kit(conn, *, itens_kit: list[dict], usuario: str) -> None:
    """Kit cancelado: as caixas dele voltam ao estoque, com tudo dentro."""
    for id_caixa in _por_caixa(itens_kit):
        _atualizar_caixa(conn, id_caixa, EM_ESTOQUE_FARMACIA, None, usuario)


def acompanhar_troca_de_paciente(conn, *, itens_kit: list[dict], destino: str,
                                 usuario: str) -> None:
    """Kit passado a outro atendimento: as caixas dele mudam de paciente junto."""
    for id_caixa in _por_caixa(itens_kit):
        _atualizar_caixa(conn, id_caixa, SEPARADO, destino, usuario)


def reconciliar(usuario: str = "sistema") -> list[str]:
    """Corrige caixas cujo estado ficou diferente do estado dos itens de dentro.

    Roda na abertura do sistema. Existe por causa do defeito da tela do kit
    (corrigido acima), que deixou caixas "Separado" com os itens já na sala. Só
    age quando TODOS os itens da caixa estão no mesmo estado e no mesmo
    atendimento — aí não há o que adivinhar: a caixa é onde o conteúdo está.
    Caixa vazia ou com itens em estados diferentes entre si fica como está.
    """
    corrigidas = []
    for caixa in db.consultar(
            "SELECT id_caixa, status, id_atendimento FROM caixas WHERE encerrada_em IS NULL"):
        estados = db.consultar(
            "SELECT DISTINCT status, id_atendimento FROM unidades WHERE id_caixa = ?",
            (caixa["id_caixa"],))
        if len(estados) != 1:
            continue
        status, atendimento = estados[0]["status"], estados[0]["id_atendimento"]
        if status == caixa["status"] and texto(atendimento) == texto(caixa["id_atendimento"]):
            continue
        db.executar(
            """UPDATE caixas SET status = ?, id_atendimento = ?,
                                 atualizado_em = ?, atualizado_por = ?
               WHERE id_caixa = ?""",
            (status, atendimento, db.agora(), usuario, caixa["id_caixa"]),
        )
        log.aviso(f"caixa reconciliada com o conteúdo · {caixa['id_caixa']} · "
                  f"{caixa['status']} → {status} · atendimento {caixa['id_atendimento']} "
                  f"→ {atendimento}", usuario)
        corrigidas.append(caixa["id_caixa"])
    return corrigidas


def registrar_saida_por_uso(conn, id_unidade: str, usuario: str) -> None:
    """Chamado por `fluxo.bipar` quando o uso é registrado.

    É o único ponto em que um item sai da caixa sem ninguém pedir: usar é abrir.
    """
    _registrar_saida(conn, id_unidade, usuario, SAIDA_USO)


def encerrar(id_caixa: str, usuario: str, motivo: str) -> tuple[bool, str]:
    caixa = buscar(id_caixa)
    if not caixa:
        return False, "Caixa não encontrada."
    if caixa["encerrada_em"]:
        return False, "Esta caixa já foi encerrada."
    if caixa["total"]:
        return False, (f"A caixa ainda tem {caixa['total']} item(ns) dentro. Esvazie-a "
                       f"antes de encerrar — os itens não podem sumir junto com ela.")
    if len(texto(motivo)) < 5:
        return False, "Informe o motivo do encerramento."

    with db.transacao() as conn:
        conn.execute(
            """UPDATE caixas SET encerrada_em = ?, encerrada_por = ?,
                                 atualizado_em = ?, atualizado_por = ?
               WHERE id_caixa = ?""",
            (db.agora(), usuario, db.agora(), usuario, caixa["id_caixa"]),
        )
        db.registrar_evento(
            conn, tipo="encerrar_caixa", status_anterior=caixa["status"],
            status_novo=caixa["status"], usuario=usuario, motivo=motivo,
            observacao=_marcador(caixa["id_caixa"]),
        )
    return True, f"Caixa {caixa['id_caixa']} encerrada."


# =========================================================
# BIPAGEM DA CAIXA INTEIRA
# =========================================================

def aplicar_operacao(
    *, operacao: str, id_caixa: str, usuario: str, id_atendimento: str = "",
    motivo: str = "", observacao: str = "", farmacia: str = "",
    excluir: list[str] | None = None,
) -> dict:
    """Aplica uma operação do fluxo a todas as unidades dentro da caixa.

    Chamado por `fluxo.bipar` quando o código lido é de uma caixa. Devolve o
    mesmo formato de `fluxo.bipar` para a tela de bipagem não precisar saber a
    diferença — mais um campo `caixa` com o resumo.

    **Tudo ou nada.** Se um dos 40 itens estiver vencido ou em lote bloqueado, a
    caixa não passa e a recusa diz exatamente quais itens travam. Mover os 39 que
    passam e ejetar o problemático seria abrir a caixa sem ninguém saber — o
    caminho certo é `retirar_item`, que exige motivo.

    `excluir` é o resultado da conferência na tela (ver `revisao`): unidades que a
    pessoa marcou como "não vai" (no envio) ou "não está na caixa" (na
    devolução). Elas saem da caixa na MESMA transação em que o resto se move —
    ou as duas coisas acontecem, ou nenhuma. Cada saída fica registrada com o
    motivo de quando aconteceu. As regras de vencido e recall valem só para o
    que de fato vai: tirar o item vencido na conferência é exatamente a saída
    prevista para ele.
    """
    op = OPERACOES.get(operacao)
    if op is None:
        return {"ok": False, "mensagem": "Operação desconhecida."}
    if not op.aceita_caixa:
        return {"ok": False, "mensagem": (
            f"“{op.titulo}” é feita item a item — a caixa não pode ser bipada aqui. "
            f"No registro de uso isso é de propósito: é ali que a caixa se abre, e "
            f"cada item precisa ficar vinculado ao paciente individualmente.")}

    try:
        with db.transacao() as conn:
            caixa = _caixa_para_operacao(conn, op, id_caixa, id_atendimento, farmacia)
            itens = [dict(r) for r in conn.execute(
                """SELECT * FROM unidades WHERE id_caixa = ?
                   ORDER BY COALESCE(NULLIF(codigo_aghu,''),'zzz'), xProd""",
                (caixa["id_caixa"],),
            ).fetchall()]

            excluidos = _excluir_da_caixa(conn, op, caixa, itens, excluir, usuario)
            if excluidos:
                fora = {e["id_unidade"] for e in excluidos}
                itens = [i for i in itens if i["id_unidade"] not in fora]

            _conferir_itens(op, caixa, itens)

            novo_atendimento = caixa["id_atendimento"]
            if op.define_atendimento:
                novo_atendimento = texto(id_atendimento) or None
            elif op.limpa_atendimento:
                novo_atendimento = None

            nova_farmacia = caixa["farmacia"]
            if op.define_farmacia:
                nova_farmacia = farmacia

            marca = f"{_marcador(caixa['id_caixa'])} {op.verbo} dentro da caixa"
            agora = db.agora()
            for item in itens:
                conn.execute(
                    """UPDATE unidades
                       SET status = ?, id_atendimento = ?, farmacia = ?,
                           atualizado_em = ?, atualizado_por = ?
                       WHERE id_unidade = ?""",
                    (op.para, novo_atendimento, nova_farmacia, agora, usuario,
                     item["id_unidade"]),
                )
                # Um evento por unidade, não um da caixa: o histórico individual
                # é o que o recall lê, e ele tem que continuar completo mesmo
                # quando o material se moveu em conjunto.
                db.registrar_evento(
                    conn, tipo=op.codigo, id_unidade=item["id_unidade"],
                    id_atendimento=novo_atendimento or item["id_atendimento"],
                    status_anterior=item["status"], status_novo=op.para,
                    usuario=usuario, motivo=motivo,
                    observacao=f"{marca}. {texto(observacao)}".strip(),
                )

            conn.execute(
                """UPDATE caixas SET status = ?, id_atendimento = ?, farmacia = ?,
                                     atualizado_em = ?, atualizado_por = ?
                   WHERE id_caixa = ?""",
                (op.para, novo_atendimento, nova_farmacia, agora, usuario,
                 caixa["id_caixa"]),
            )
    except ErroDeNegocio as recusa:
        log.info(f"bipagem de caixa recusada · operacao={operacao} · "
                 f"caixa={id_caixa} · {recusa}", usuario)
        return {"ok": False, "mensagem": str(recusa)}
    except Exception as falha_tecnica:
        log.erro(f"falha ao bipar caixa · operacao={operacao} · caixa={id_caixa}",
                 usuario, falha_tecnica)
        return {"ok": False, "mensagem": ("Não foi possível registrar por uma falha do "
                                          "sistema. Nada foi gravado. Tente novamente.")}

    log.info(f"caixa bipada · operacao={operacao} · caixa={caixa['id_caixa']} · "
             f"itens={len(itens)} · fora={len(excluidos)}", usuario)
    if excluidos and op.codigo == "devolver_farmacia":
        _alertar_faltas_na_devolucao(caixa, excluidos, usuario)

    mensagem = f"Caixa {caixa['id_caixa']} · {len(itens)} item(ns) {op.verbo}."
    if excluidos:
        mensagem += (f" {len(excluidos)} item(ns) ficaram fora: "
                     + ("continuam na sala, como pendência."
                        if op.codigo == "devolver_farmacia"
                        else "voltaram ao estoque da farmácia."))
    return {
        "ok": True,
        "mensagem": mensagem,
        "excluidos": [_resumo_item(e) for e in excluidos],
        "caixa": {
            "id_caixa": caixa["id_caixa"],
            "nome": caixa["nome"],
            "especialidade": caixa["especialidade"],
            "total": len(itens),
            "status": op.para,
            "status_rotulo": rotulo(op.para),
        },
        "itens": [{"id_unidade": i["id_unidade"],
                   "aghu": i.get("codigo_aghu") or "—",
                   "produto": i.get("xProd", ""),
                   "lote": i.get("nLote") or "—",
                   "validade": data_br(i.get("dVal")) or "—"} for i in itens],
        "alertas": _avisos_da_caixa(caixa["id_caixa"], itens),
    }


# O motivo gravado em cada unidade que ficou de fora — diz o que aconteceu, e
# no caso da devolução diz também o que investigar.
MOTIVO_FORA = {
    "devolver_farmacia": ("Não estava na caixa na devolução à farmácia — pode ter "
                          "sido usado sem registro. Continua na sala até ser localizado."),
    "dispensar_sala": "Retirado da caixa no envio à sala — não vai para este procedimento.",
    "enviar_sala": "Retirado da caixa no envio à sala — não vai para este procedimento.",
}


def _resumo_item(i: dict) -> dict:
    return {"id_unidade": i["id_unidade"],
            "aghu": i.get("codigo_aghu") or "—",
            "produto": i.get("xProd", ""),
            "lote": i.get("nLote") or "—",
            "validade": data_br(i.get("dVal")) or "—"}


def _excluir_da_caixa(conn, op, caixa: dict, itens: list[dict],
                      excluir: list[str] | None, usuario: str) -> list[dict]:
    """Tira da caixa o que a conferência marcou, dentro da transação do chamador."""
    ids = list(dict.fromkeys(texto(i) for i in (excluir or []) if texto(i)))
    if not ids:
        return []
    por_id = {i["id_unidade"]: i for i in itens}
    estranhos = [i for i in ids if i not in por_id]
    if estranhos:
        raise ErroDeCaixa("A conferência marcou um item que não está nesta caixa. "
                          "Bipe a caixa de novo para atualizar a lista.")
    if len(ids) == len(itens):
        raise ErroDeCaixa("Todos os itens foram marcados como fora. Se nada vai, "
                          "não bipe a caixa — use a caixa quando houver o que mover.")

    motivo = MOTIVO_FORA.get(op.codigo, "Retirado da caixa na conferência.")
    agora = db.agora()
    excluidos = []
    for id_unidade in ids:
        item = por_id[id_unidade]
        _registrar_saida(conn, id_unidade, usuario, SAIDA_RETIRADA, motivo)
        db.registrar_evento(
            conn, tipo="retirar_da_caixa", id_unidade=id_unidade,
            id_atendimento=item.get("id_atendimento"),
            status_anterior=item["status"], status_novo=item["status"],
            usuario=usuario, motivo=motivo,
            observacao=f"{_marcador(caixa['id_caixa'])} fora na conferência de {op.codigo}",
        )
        # No envio de um kit em caixa, o item separado que não vai não pode ficar
        # reservado ao paciente sem ir junto: volta ao estoque, como os itens
        # desmarcados na revisão do kit.
        if item["status"] == SEPARADO:
            conn.execute(
                """UPDATE unidades SET status = ?, id_atendimento = NULL,
                                       atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (EM_ESTOQUE_FARMACIA, agora, usuario, id_unidade),
            )
            db.registrar_evento(
                conn, tipo="cancelar_separacao", id_unidade=id_unidade,
                id_atendimento=item.get("id_atendimento"),
                status_anterior=SEPARADO, status_novo=EM_ESTOQUE_FARMACIA,
                usuario=usuario, motivo="Retirado da caixa no envio",
            )
        excluidos.append(item)
    return excluidos


def _alertar_faltas_na_devolucao(caixa: dict, excluidos: list[dict], usuario: str) -> None:
    """A caixa voltou sem alguns itens: a sala precisa explicar onde estão.

    É o caso que a conferência na devolução existe para pegar — o material
    usado no paciente sem ninguém bipar. Descoberto no mesmo dia, a equipe ainda
    lembra da cirurgia; descoberto no inventário, semanas depois, não.
    """
    linhas = [f"  · {e.get('codigo_aghu') or '—'} {e.get('xProd', '')} — lote "
              f"{e.get('nLote') or '—'} ({e['id_unidade']})" for e in excluidos[:20]]
    alertas.criar(
        modulo_destino="sala-procedimento",
        titulo=f"Caixa {caixa['id_caixa']} voltou sem {len(excluidos)} item(ns)",
        mensagem=(f"{caixa['nome']}. Na devolução à farmácia, estes itens não estavam "
                  f"na caixa e continuam como pendência da sala. Se foram usados, "
                  f"registre o uso no paciente; se não, localize e devolva:\n"
                  + "\n".join(linhas)),
        usuario=usuario,
        id_atendimento=texto(caixa.get("id_atendimento")),
        ids_unidade=[e["id_unidade"] for e in excluidos],
    )


def revisao(*, operacao: str, id_caixa: str, id_atendimento: str = "",
            farmacia: str = "") -> dict:
    """O que a caixa tem, agrupado para conferir de olho antes de confirmar.

    Não move nada. Agrupa por produto, lote e série, porque é assim que se conta
    uma bandeja: "12 parafusos deste lote", não 12 linhas iguais. Cada grupo
    leva os ids das unidades, para a tela poder dizer quais ficaram de fora.
    As mesmas regras da operação são checadas aqui (caixa no lugar certo, do
    paciente certo) — para não pedir uma conferência que depois vai ser recusada.
    """
    op = OPERACOES.get(operacao)
    if op is None or not op.aceita_caixa:
        return {"ok": False, "mensagem": "Operação inválida para caixa."}
    try:
        with db.transacao() as conn:
            caixa = _caixa_para_operacao(conn, op, id_caixa, id_atendimento, farmacia)
            itens = [dict(r) for r in conn.execute(
                """SELECT * FROM unidades WHERE id_caixa = ?
                   ORDER BY COALESCE(NULLIF(codigo_aghu,''),'zzz'), xProd, nLote,
                            numero_serie, id_unidade""",
                (caixa["id_caixa"],),
            ).fetchall()]
    except ErroDeNegocio as recusa:
        return {"ok": False, "mensagem": str(recusa)}
    if not itens:
        return {"ok": False, "mensagem": f"A caixa {caixa['id_caixa']} está vazia."}

    grupos: dict[tuple, dict] = {}
    for i in itens:
        chave = (texto(i.get("codigo_aghu")), texto(i.get("xProd")),
                 texto(i.get("nLote")), texto(i.get("numero_serie")))
        g = grupos.setdefault(chave, {
            "aghu": i.get("codigo_aghu") or "—",
            "produto": i.get("descritivo_hospital") or i.get("xProd") or "",
            "produto_fornecedor": i.get("xProd") or "",
            "lote": i.get("nLote") or "—",
            "serie": i.get("numero_serie") or "",
            "validade": data_br(i.get("dVal")) or "—",
            "ids": [],
        })
        g["ids"].append(i["id_unidade"])
    lista = list(grupos.values())
    for g in lista:
        g["quantidade"] = len(g["ids"])

    devolucao = op.codigo == "devolver_farmacia"
    return {
        "ok": False,
        "revisao_caixa": {
            "id_caixa": caixa["id_caixa"],
            "nome": caixa["nome"],
            "total": len(itens),
            "grupos": lista,
            "devolucao": devolucao,
            "rotulo_fora": "não está na caixa" if devolucao else "não vai",
        },
        "mensagem": "Confira o conteúdo da caixa antes de confirmar.",
    }


def _caixa_para_operacao(conn, op, id_caixa: str, id_atendimento: str,
                         farmacia: str) -> dict:
    caixa = _caixa_ativa(conn, id_caixa)

    if caixa["status"] not in op.de:
        esperados = " ou ".join(rotulo(s) for s in op.de)
        raise ErroDeCaixa(
            f"A caixa está como “{rotulo(caixa['status'])}”. Para esta operação ela "
            f"precisa estar como “{esperados}”."
        )
    if op.escopo_farmacia and texto(farmacia) and texto(caixa.get("farmacia")) \
            and texto(caixa["farmacia"]) != texto(farmacia):
        raise ErroDeCaixa(
            f"Esta caixa pertence ao estoque da "
            f"{rotulo_farmacia(caixa['farmacia'])} e não pode ser movimentada a "
            f"partir da {rotulo_farmacia(farmacia)}."
        )
    if op.exige_atendimento and not op.define_atendimento:
        if texto(caixa.get("id_atendimento")) != texto(id_atendimento):
            raise ErroDeCaixa(
                "Esta caixa está vinculada a outro atendimento. Confira o paciente "
                "selecionado antes de bipar."
            )
    return caixa


def _conferir_itens(op, caixa: dict, itens: list[dict]) -> None:
    """Tudo ou nada: a caixa só anda se todos os itens de dentro puderem andar."""
    if not itens:
        raise ErroDeCaixa(f"A caixa {caixa['id_caixa']} está vazia. Não há o que movimentar.")

    fora_do_estado = [i for i in itens if i["status"] != caixa["status"]]
    if fora_do_estado:
        raise ErroDeCaixa(
            f"{len(fora_do_estado)} item(ns) dentro da caixa estão em situação "
            f"diferente da caixa. Abra a ficha da caixa e trate a divergência antes "
            f"de movimentá-la."
        )

    if op.barra_vencido:
        vencidos = [i for i in itens
                    if texto(i.get("dVal")) and (dias_para(i.get("dVal")) or 0) < 0]
        if vencidos:
            raise ErroDeCaixa(_recusa_lista(
                "vencido(s)", vencidos,
                "Retire-o(s) na ficha da caixa (exige motivo) e movimente o resto."))

    if op.codigo in ("enviar_farmacia", "separar", "dispensar_sala",
                     "enviar_sala", "conferir_sala"):
        bloqueados = [i for i in itens
                      if recall.bloqueio_do_item(i.get("nLote"), i.get("codigo_aghu"))]
        if bloqueados:
            raise ErroDeCaixa(_recusa_lista(
                "de lote BLOQUEADO por recall", bloqueados,
                "Não movimente esta caixa. Retire o material e avise o almoxarifado."))


def _recusa_lista(rotulo_problema: str, itens: list[dict], saida: str) -> str:
    linhas = [
        f"· {i.get('codigo_aghu') or '—'} {i.get('xProd')} — lote "
        f"{i.get('nLote') or '—'} · val. {data_br(i.get('dVal')) or '—'}"
        for i in itens[:8]
    ]
    if len(itens) > 8:
        linhas.append(f"· … e mais {len(itens) - 8}.")
    return (f"A caixa tem {len(itens)} item(ns) {rotulo_problema} e por isso não pode "
            f"ser movimentada:\n" + "\n".join(linhas) + f"\n{saida}")


def _avisos_da_caixa(id_caixa: str, itens: list[dict]) -> list[str]:
    avisos = []
    pendentes = falta_pendente(id_caixa)
    if pendentes:
        total = sum(p["falta"] for p in pendentes)
        avisos.append(f"Caixa incompleta: faltam {total} item(ns) em relação à grade.")
    proximos = [i for i in itens
                if dias_para(i.get("dVal")) is not None
                and 0 <= (dias_para(i.get("dVal")) or 0) <= 30]
    if proximos:
        avisos.append(f"{len(proximos)} item(ns) desta caixa vencem em 30 dias ou menos.")
    sem_validade = [i for i in itens if not texto(i.get("dVal"))]
    if sem_validade:
        avisos.append(f"{len(sem_validade)} item(ns) sem data de validade cadastrada.")
    return avisos


def desfazer_movimento(id_caixa: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    """Desfaz a última bipagem da caixa inteira — o 'ctrl+z' de quem bipou errado.

    Bipar a caixa errada é o engano mais provável deste fluxo, justamente porque
    uma leitura move 40 itens. Sem desfazer, o conserto seria bipar 40 vezes na
    operação inversa, quando ela existir.
    """
    caixa = buscar(id_caixa)
    if not caixa:
        return False, "Caixa não encontrada."

    itens = conteudo(id_caixa)
    if not itens:
        return False, "A caixa está vazia — não há movimento para desfazer."

    ultimo = db.consultar_um(
        """SELECT tipo, status_anterior FROM eventos
           WHERE id_unidade = ? AND status_anterior IS NOT NULL
             AND status_anterior <> status_novo
           ORDER BY id_evento DESC LIMIT 1""",
        (itens[0]["id_unidade"],),
    )
    if not ultimo:
        return False, "Não há movimento para desfazer nesta caixa."

    anterior = ultimo["status_anterior"]
    if anterior not in ESTADOS:
        return False, "O último movimento não pode ser desfeito automaticamente."
    if any(i["status"] != caixa["status"] for i in itens):
        return False, ("Os itens da caixa não estão todos na mesma situação. "
                       "Trate a divergência na ficha da caixa.")

    with db.transacao() as conn:
        for item in itens:
            conn.execute(
                """UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (anterior, db.agora(), usuario, item["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="desfazer", id_unidade=item["id_unidade"],
                id_atendimento=item.get("id_atendimento"),
                status_anterior=caixa["status"], status_novo=anterior, usuario=usuario,
                motivo=motivo or "Correção do operador",
                observacao=f"{_marcador(caixa['id_caixa'])} desfeito: {ultimo['tipo']}",
            )
        conn.execute(
            """UPDATE caixas SET status = ?, atualizado_em = ?, atualizado_por = ?
               WHERE id_caixa = ?""",
            (anterior, db.agora(), usuario, caixa["id_caixa"]),
        )
    log.aviso(f"movimento de caixa desfeito · {caixa['id_caixa']} · "
              f"de={caixa['status']} para={anterior}", usuario)
    return True, (f"Movimento desfeito. A caixa e seus {len(itens)} item(ns) "
                  f"voltaram para “{rotulo(anterior)}”.")


# =========================================================
# CONCILIAÇÃO DO RETORNO
# =========================================================

def conciliacao(id_caixa: str) -> dict:
    """O que estava na caixa, o que foi usado e o que não está em lugar nenhum.

    Como a caixa tem uma grade, a conta do retorno é barata: o que saiu da caixa
    sem virar uso e sem voltar é o buraco. Quase sempre é uso que a sala esqueceu
    de bipar — e o retorno é o único momento barato de perceber isso. Depois vira
    inventário.
    """
    caixa = buscar(id_caixa)
    if not caixa:
        return {}

    dentro = conteudo(id_caixa)
    usados = db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.nLote, u.dVal,
                   a.prontuario, a.sala, ci.saiu_em
            FROM caixa_itens ci
            JOIN unidades u ON u.id_unidade = ci.id_unidade
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE ci.id_caixa = ? AND ci.saiu_em IS NOT NULL
              AND u.status = '{UTILIZADO}'
            ORDER BY ci.saiu_em DESC LIMIT 200""",
        (caixa["id_caixa"],),
    )
    sem_destino = db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.nLote, u.dVal, u.status,
                   ci.saiu_em, ci.saiu_por, ci.motivo_saida
            FROM caixa_itens ci
            JOIN unidades u ON u.id_unidade = ci.id_unidade
            WHERE ci.id_caixa = ? AND ci.saiu_em IS NOT NULL
              AND u.status <> '{UTILIZADO}' AND u.id_caixa IS NULL
              AND u.status NOT IN ('devolvido_fornecedor','baixado')
            ORDER BY ci.saiu_em DESC""",
        (caixa["id_caixa"],),
    )
    pendentes = falta_pendente(id_caixa)
    return {
        "caixa": caixa,
        "dentro": dentro,
        "usados": usados,
        "sem_destino": sem_destino,
        "falta": pendentes,
        "total_falta": sum(p["falta"] for p in pendentes),
        "completa": not pendentes,
    }
