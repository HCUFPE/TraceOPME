"""v17 — devolução do que não foi utilizado, em duas etapas.

1. A SALA bipa o que voltou sem uso — na própria sala ou na porta da farmácia
   — informando quem está devolvendo. Os itens (ou a caixa, pela contagem)
   entram numa devolução PENDENTE do atendimento. Nada é "devolvido" ainda.
2. A FARMÁCIA confirma com a própria senha — na mesma tela, se estiver junto,
   ou depois, em Farmácia → Devoluções a confirmar, quando o material chegar.
   O que ela não encontrar é desmarcado: o item vai para DIVERGÊNCIA (a caixa
   fica bloqueada para conferência) e gera alerta.

Só na confirmação são gravados os eventos `devolver_nao_utilizado` /
`confirmar_devolver_nao_utilizado` / `devolver_caixa`, com quem devolveu e quem
recebeu — é o que relatórios, histórico e prontuário leem.
"""

from .. import busca, db, gs1, log
from ..erros import ErroDeNegocio
from ..domain import (DIVERGENCIA, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, EM_SALA, OPERACOES,
                      TRANSITO_SALA, estoque_de_volta)
from ..utils import data_br, gerar_id, inteiro, normalizar_codigo, texto
from . import alertas, caixas, caixas_consignado, usuarios

OPERACAO = "devolver_nao_utilizado"


# ---------------------------------------------------------------- consultas

def pendente_do_atendimento(id_atendimento: str) -> dict | None:
    return db.consultar_um(
        "SELECT * FROM devolucoes WHERE id_atendimento = ? AND status = 'pendente' "
        "ORDER BY criado_em DESC LIMIT 1", (texto(id_atendimento),))


def buscar(id_devolucao: str) -> dict | None:
    dev = db.consultar_um(
        """SELECT d.*, a.prontuario, a.paciente, a.sala, a.unidade, a.especialidade,
                  a.data_procedimento
           FROM devolucoes d LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.id_devolucao = ?""", (texto(id_devolucao),))
    if not dev:
        return None
    dev = dict(dev)
    dev["itens"] = itens(dev["id_devolucao"])
    dev["pendentes"] = [i for i in dev["itens"] if i["situacao"] == "pendente"]
    return dev


def itens(id_devolucao: str, so_pendentes: bool = False) -> list[dict]:
    filtro = "AND i.situacao = 'pendente'" if so_pendentes else "AND i.situacao <> 'removido'"
    return db.consultar(
        f"""SELECT i.*, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                   u.numero_serie, u.codigo_barras, u.status AS status_unidade, c.nome AS nome_caixa,
                   c.fornecedor AS fornecedor_caixa
            FROM devolucao_itens i
            LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
            LEFT JOIN caixas c ON c.id_caixa = i.id_caixa
            WHERE i.id_devolucao = ? {filtro}
            ORDER BY i.id_item""", (texto(id_devolucao),))


def listar_pendentes() -> list[dict]:
    """Devoluções bipadas pela sala que a farmácia ainda não confirmou."""
    return db.consultar(
        """SELECT d.*, a.prontuario, a.paciente, a.sala, a.unidade, a.especialidade,
                  (SELECT COUNT(*) FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                     AND i.situacao = 'pendente' AND i.tipo = 'item') AS qtd_itens,
                  (SELECT COUNT(*) FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                     AND i.situacao = 'pendente' AND i.tipo = 'caixa') AS qtd_caixas,
                  (SELECT MAX(bipado_em) FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                     AND i.situacao = 'pendente') AS ultimo_bip
           FROM devolucoes d LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.status = 'pendente'
             AND EXISTS (SELECT 1 FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                           AND i.situacao = 'pendente')
           ORDER BY d.criado_em""")


def recentes_confirmadas(limite: int = 20) -> list[dict]:
    return db.consultar(
        """SELECT d.*, a.prontuario, a.sala, a.unidade,
                  (SELECT COUNT(*) FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                     AND i.situacao = 'recebido') AS recebidos,
                  (SELECT COUNT(*) FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                     AND i.situacao = 'nao_recebido') AS nao_recebidos
           FROM devolucoes d LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.status = 'confirmada' ORDER BY d.confirmada_em DESC LIMIT ?""", (limite,))


def unidades_aguardando() -> set[str]:
    """Unidades bipadas numa devolução ainda não confirmada (inclui as de caixa)."""
    soltas = {r["id_unidade"] for r in db.consultar(
        """SELECT i.id_unidade FROM devolucao_itens i JOIN devolucoes d ON d.id_devolucao = i.id_devolucao
           WHERE i.tipo = 'item' AND i.situacao = 'pendente' AND d.status = 'pendente'""")}
    return soltas


def pendentes_do_atendimento(id_atendimento: str) -> list[dict]:
    dev = pendente_do_atendimento(id_atendimento)
    return itens(dev["id_devolucao"], so_pendentes=True) if dev else []


# ---------------------------------------------------------------- avisos de situação

def aviso_situacao(unidade: dict, id_atendimento: str) -> str:
    """v17 (out/2026): explica, na hora do bip da devolução, de onde vem o item."""
    status = unidade.get("status")
    dono = texto(unidade.get("id_atendimento"))
    if status == EM_SALA and dono == id_atendimento:
        return ("Item dispensado pela farmácia para este paciente e não usado — volta ao estoque "
                "quando a farmácia confirmar.")
    if status == TRANSITO_SALA and dono == id_atendimento:
        return ("Atenção: item dispensado para este paciente, mas a sala NÃO tinha confirmado o "
                "recebimento com a senha. Volta ao estoque quando a farmácia confirmar.")
    if status in (EM_SALA, TRANSITO_SALA):
        pront = db.escalar("SELECT prontuario FROM atendimentos WHERE id_atendimento = ?", (dono,)) or "—"
        return (f"Atenção: este item foi dispensado para OUTRO paciente (prontuário {pront}). "
                f"A devolução fica registrada neste atendimento.")
    return ("Atenção: este item NÃO foi dispensado pela farmácia — no sistema ele já estava no "
            "estoque. A devolução fica registrada para conferência.")


def _aviso_caixa(id_caixa: str, id_atendimento: str) -> str:
    linhas = db.consultar("SELECT status, id_atendimento FROM unidades WHERE id_caixa = ?", (id_caixa,))
    dispensados = [l for l in linhas if l["status"] in (EM_SALA, TRANSITO_SALA)]
    if not dispensados:
        return ("Atenção: esta caixa NÃO foi dispensada pela farmácia — no sistema ela já estava no "
                "estoque. A devolução fica registrada para conferência.")
    if any(texto(l["id_atendimento"]) != id_atendimento for l in dispensados):
        return "Atenção: esta caixa foi dispensada para OUTRO paciente."
    if any(l["status"] == TRANSITO_SALA for l in dispensados):
        return ("Atenção: caixa dispensada para este paciente, mas a sala NÃO tinha confirmado o "
                "recebimento com a senha.")
    return "Caixa dispensada pela farmácia para este paciente — volta ao estoque quando a farmácia confirmar."


# ---------------------------------------------------------------- 1ª etapa: sala bipa

def _abrir_ou_pegar(conn, id_atendimento: str, usuario: str, devolvido_por: str) -> str:
    linha = conn.execute(
        "SELECT id_devolucao FROM devolucoes WHERE id_atendimento = ? AND status = 'pendente' "
        "ORDER BY criado_em DESC LIMIT 1", (id_atendimento,)).fetchone()
    if linha:
        conn.execute("UPDATE devolucoes SET devolvido_por = ? WHERE id_devolucao = ?",
                     (devolvido_por, linha[0]))
        return linha[0]
    id_devolucao = gerar_id("DV")
    conn.execute(
        """INSERT INTO devolucoes (id_devolucao, id_atendimento, status, devolvido_por,
                                   criado_por, criado_em)
           VALUES (?,?,'pendente',?,?,?)""",
        (id_devolucao, id_atendimento, devolvido_por, usuario, db.agora()))
    return id_devolucao


def abrir_retorno(conn, id_atendimento: str, usuario: str, *, unidades: list[str] = (),
                  caixas: dict | None = None, origem: str = "") -> str | None:
    """v18: material que volta à farmácia SEM a sala bipar a devolução
    (procedimento cancelado depois da ciência da sala; uso estornado).

    Entra numa devolução PENDENTE do atendimento, como os não utilizados: o item
    continua "na sala", ligado ao paciente, até a farmácia dar ciência em
    Farmácia → Não utilizados — dar ciência. `caixas` = {id_caixa: quantidade}."""
    if not unidades and not caixas:
        return None
    id_devolucao = _abrir_ou_pegar(conn, id_atendimento, usuario, origem or usuario)
    agora = db.agora()
    for id_unidade in unidades:
        conn.execute(
            """INSERT INTO devolucao_itens (id_devolucao, tipo, id_unidade, devolvido_por, bipado_por,
                                            bipado_em, motivo)
               VALUES (?,'item',?,?,?,?,?)""",
            (id_devolucao, id_unidade, origem or usuario, usuario, agora, origem))
    for id_caixa, quantidade in (caixas or {}).items():
        conn.execute(
            """INSERT INTO devolucao_itens (id_devolucao, tipo, id_caixa, quantidade, devolvido_por,
                                            bipado_por, bipado_em, motivo)
               VALUES (?,'caixa',?,?,?,?,?,?)""",
            (id_devolucao, id_caixa, int(quantidade), origem or usuario, usuario, agora, origem))
    return id_devolucao


def incluir_sem_destino(id_devolucao: str, id_unidade: str, usuario: dict) -> tuple[bool, str]:
    """v18.22: a farmácia está com o material na mão, mas ele ficou "sem destino".

    Caso real (HC-UFPE, 17/11/2026): a sala finalizou sem bipar o uso e sem pôr
    o item na lista de não utilizados. O material voltou fisicamente, mas a
    conferência só mostrava o alerta — a farmácia não tinha onde marcar e a
    sala achava que não podia mais mexer. Agora a farmácia inclui o item nesta
    mesma lista, já conferido, e dá ciência junto com o resto.
    """
    dev = db.consultar_um("SELECT * FROM devolucoes WHERE id_devolucao = ?", (texto(id_devolucao),))
    if not dev:
        return False, "Lista de não utilizados não encontrada."
    if texto(dev["status"]) != "pendente":
        return False, "Esta lista já foi confirmada."
    uni = db.consultar_um(
        """SELECT u.id_unidade, u.status, u.id_atendimento, u.id_caixa, u.nLote,
                  COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS material
           FROM unidades u WHERE u.id_unidade = ?""", (texto(id_unidade),))
    if not uni or texto(uni["id_atendimento"]) != texto(dev["id_atendimento"]):
        return False, "Este material não é deste procedimento."
    if texto(uni["status"]) not in (EM_SALA, TRANSITO_SALA):
        return False, ("Este material não está mais com o paciente — confira a situação dele "
                       "no histórico do item.")
    if texto(uni["id_caixa"]):
        return False, ("Este material está dentro de uma caixa de consignado: a devolução é "
                       "pela caixa.")
    ja = db.escalar("SELECT COUNT(*) FROM devolucao_itens WHERE id_unidade = ? AND situacao = 'pendente'",
                    (texto(id_unidade),))
    if ja:
        return False, "Este material já está na lista."
    nome = usuario.get("nome") or usuario["username"]
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO devolucao_itens (id_devolucao, tipo, id_unidade, devolvido_por,
                                            bipado_por, bipado_em, motivo)
               VALUES (?,'item',?,?,?,?,?)""",
            (texto(id_devolucao), texto(id_unidade), nome, usuario["username"], db.agora(),
             "sem destino — recebido de volta pela farmácia"))
        db.registrar_evento(
            conn, tipo="sem_destino_incluido", id_unidade=texto(id_unidade),
            id_atendimento=texto(dev["id_atendimento"]), usuario=usuario["username"],
            observacao=(f"{nome} recebeu de volta na farmácia um material que a sala não bipou "
                        f"nem colocou na lista (lote {uni['nLote'] or '—'})."))
    return True, (f"{uni['material']} incluído na lista de não utilizados. Confirme o recebimento "
                  "junto com os demais.")


def _resumo(id_devolucao: str) -> dict:
    from ..utils import data_br, data_hora_br
    pend = itens(id_devolucao, so_pendentes=True)
    lista = [{"id_item": i["id_item"], "tipo": i["tipo"], "id_caixa": i["id_caixa"] or "",
              "quantidade": i["quantidade"], "descricao": i["descritivo_hospital"] or i["xProd"] or "",
              "lote": i["nLote"] or "", "quando": data_hora_br(i["bipado_em"]),
              "aghu": i["codigo_aghu"] or "", "validade": data_br(i["dVal"]) or "",
              "por": i["devolvido_por"] or "",
              "remover": f"/devolucoes/item/{i['id_item']}/remover"} for i in pend]
    return {"id_devolucao": id_devolucao,
            "itens": sum(1 for i in pend if i["tipo"] == "item"),
            "caixas": sum(1 for i in pend if i["tipo"] == "caixa"), "lista": lista}


def bipar(*, codigo: str, id_atendimento: str, usuario: str, devolvido_por: str,
          id_unidade: str = "", quantidade: str = "") -> dict:
    """A sala bipa um item (ou uma caixa) que voltou sem uso. Formato de `fluxo.bipar`."""
    from .fluxo import (CAMPOS_ITEM, ErroDeFluxo, EscolhaNecessaria, _selecionar,
                        formatar_item)

    op = OPERACOES[OPERACAO]
    etiqueta = busca.interpretar(codigo)
    bipado = texto(codigo)          # v18.43.2: o texto como veio do leitor
    codigo = normalizar_codigo(codigo)
    id_atendimento = texto(id_atendimento)
    devolvido_por = " ".join(texto(devolvido_por).split())
    if not devolvido_por:
        return {"ok": False, "mensagem": ("Informe quem está devolvendo o material "
                                          "(nome de quem entrega à farmácia).")}
    if not codigo:
        return {"ok": False, "mensagem": "Bipe ou digite um código."}
    if not id_atendimento:
        return {"ok": False, "mensagem": "Selecione o atendimento antes de bipar."}
    atendimento = db.consultar_um("SELECT status FROM atendimentos WHERE id_atendimento = ?",
                                  (id_atendimento,))
    if not atendimento:
        return {"ok": False, "mensagem": "Atendimento não encontrado."}

    aviso = "Aguardando a confirmação da farmácia com a senha."

    # Caixa de consignado: conta em vez de bipar item a item.
    if caixas.e_codigo_caixa(codigo):
        r = caixas_consignado.devolver(id_caixa=codigo, id_atendimento=id_atendimento,
                                       quantidade=quantidade, usuario=usuario,
                                       devolvido_por=devolvido_por)
        if not r.get("ok"):
            return r
        with db.transacao() as conn:
            id_devolucao = _abrir_ou_pegar(conn, id_atendimento, usuario, devolvido_por)
            conn.execute(
                """INSERT INTO devolucao_itens (id_devolucao, tipo, id_caixa, quantidade,
                                                devolvido_por, bipado_por, bipado_em)
                   VALUES (?,'caixa',?,?,?,?,?)""",
                (id_devolucao, r["caixa"]["id_caixa"], r["informado"], devolvido_por,
                 usuario, db.agora()))
            db.registrar_evento(
                conn, tipo="bipar_devolucao", id_atendimento=id_atendimento, usuario=usuario,
                devolvido_por=devolvido_por,
                motivo=f"{r['informado']} item(ns) na caixa, contagem confere",
                observacao=f"[{r['caixa']['id_caixa']}] caixa bipada na devolução; aguardando a farmácia")
        return {"ok": True, "pendente": True, "caixa": r["caixa"], "itens": [],
                "devolvido_por": devolvido_por, "devolucao": _resumo(id_devolucao),
                "mensagem": f"Caixa {r['caixa']['id_caixa']} bipada na devolução "
                            f"({r['informado']} item(ns), contagem confere). {aviso}",
                "alertas": [_aviso_caixa(r["caixa"]["id_caixa"], id_atendimento)]}

    try:
        with db.transacao() as conn:
            candidatas = [dict(r) for r in conn.execute(
                f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
                    FROM unidades u
                    LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                    WHERE UPPER(u.id_unidade) = UPPER(?)
                       OR gtin(u.codigo_barras) = gtin(?)
                       OR (u.numero_serie IS NOT NULL AND u.numero_serie <> ''
                           AND REPLACE(u.numero_serie, ' ', '') = ?)
                    ORDER BY CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                             u.dVal, u.criado_em""",
                (codigo, codigo, codigo)).fetchall()]
            if not candidatas:
                # v17: etiqueta secundária (só validade/lote, sem GTIN): acha pelo lote.
                cond, extra = gs1.sql_por_lote(etiqueta)
                if cond:
                    candidatas = [dict(r) for r in conn.execute(
                        f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
                            FROM unidades u
                            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                            WHERE {cond}
                            ORDER BY CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                                     u.dVal, u.criado_em""", extra).fetchall()]
            # v18.43.2: o texto bipado inteiro é o código — se alguma unidade tem
            # exatamente ele, a busca é essa e não abre a lista de lotes do produto.
            candidatas = busca.preferir_exatos(candidatas, bipado)
            candidatas, _ = gs1.filtrar(candidatas, etiqueta)
            if candidatas:
                ids = [c["id_unidade"] for c in candidatas]
                marca = ",".join("?" for _ in ids)
                ja_devolvidas = {r[0] for r in conn.execute(
                    f"""SELECT DISTINCT id_unidade FROM eventos WHERE tipo = ? AND id_atendimento = ?
                        AND id_unidade IN ({marca})""", (OPERACAO, id_atendimento, *ids)).fetchall()}
                aguardando = {r[0] for r in conn.execute(
                    f"""SELECT i.id_unidade FROM devolucao_itens i
                        JOIN devolucoes d ON d.id_devolucao = i.id_devolucao
                        WHERE i.situacao = 'pendente' AND d.status = 'pendente'
                          AND i.id_unidade IN ({marca})""", ids).fetchall()}
                restantes = [c for c in candidatas
                             if c["id_unidade"] not in ja_devolvidas | aguardando]
                if not [c for c in restantes if c["status"] in op.de]:
                    if aguardando & {c["id_unidade"] for c in candidatas if c["status"] in op.de}:
                        raise ErroDeFluxo("Este material já foi bipado nesta devolução e está "
                                          "aguardando a confirmação da farmácia.")
                    if ja_devolvidas:
                        raise ErroDeFluxo("Este material já foi devolvido neste atendimento. "
                                          "Não é preciso bipar de novo.")
                candidatas = restantes or candidatas

            # v17: devolve primeiro o que foi dispensado para este paciente.
            meus = [c for c in candidatas if c["status"] in (TRANSITO_SALA, EM_SALA)
                    and texto(c.get("id_atendimento")) == id_atendimento]
            if meus:
                candidatas = meus
            unidade = _selecionar(op, candidatas, id_atendimento, "", id_unidade)

            id_devolucao = _abrir_ou_pegar(conn, id_atendimento, usuario, devolvido_por)
            conn.execute(
                """INSERT INTO devolucao_itens (id_devolucao, tipo, id_unidade, devolvido_por,
                                                bipado_por, bipado_em)
                   VALUES (?,'item',?,?,?,?)""",
                (id_devolucao, unidade["id_unidade"], devolvido_por, usuario, db.agora()))
            db.registrar_evento(
                conn, tipo="bipar_devolucao", id_unidade=unidade["id_unidade"],
                id_atendimento=id_atendimento, usuario=usuario, devolvido_por=devolvido_por,
                observacao="Bipado na devolução pela sala; aguardando a confirmação da farmácia")
    except EscolhaNecessaria as ambiguo:
        return {"ok": False, "escolha": True,
                "mensagem": "Mais de um item responde a este código — escolha qual é.",
                "opcoes": [formatar_item(c) for c in ambiguo.candidatas]}
    except ErroDeFluxo as recusa:
        log.info(f"devolução recusada · codigo={codigo} · {recusa}", usuario)
        return {"ok": False, "mensagem": str(recusa)}

    return {"ok": True, "pendente": True, "item": formatar_item(unidade),
            "devolvido_por": devolvido_por, "devolucao": _resumo(id_devolucao),
            "mensagem": f"{unidade.get('xProd')} bipado na devolução. {aviso}",
            "alertas": [aviso_situacao(unidade, id_atendimento)]}


def remover_item(id_item: int, usuario: str, motivo: str = "") -> tuple[bool, str, str]:
    """A sala tira da devolução pendente algo bipado por engano."""
    linha = db.consultar_um(
        """SELECT i.*, d.id_atendimento, d.status AS status_devolucao FROM devolucao_itens i
           JOIN devolucoes d ON d.id_devolucao = i.id_devolucao WHERE i.id_item = ?""",
        (inteiro(id_item, 0),))
    if not linha or linha["situacao"] != "pendente" or linha["status_devolucao"] != "pendente":
        return False, "Este item não está mais pendente nesta devolução.", ""
    with db.transacao() as conn:
        conn.execute(
            """UPDATE devolucao_itens SET situacao = 'removido', resolvido_em = ?, resolvido_por = ?,
                      motivo = ? WHERE id_item = ?""",
            (db.agora(), usuario, texto(motivo) or "Bipado por engano", linha["id_item"]))
        db.registrar_evento(
            conn, tipo="remover_da_devolucao", id_unidade=linha["id_unidade"],
            id_atendimento=linha["id_atendimento"], usuario=usuario,
            motivo=texto(motivo) or "Bipado por engano",
            observacao=(f"[{linha['id_caixa']}] caixa tirada da devolução" if linha["tipo"] == "caixa"
                        else "Tirado da devolução antes da confirmação da farmácia"))
    return True, "Retirado da devolução.", linha["id_atendimento"]


# ---------------------------------------------------------------- 2ª etapa: farmácia confirma

def confirmar(*, id_devolucao: str, operador: str, usuario_farmacia: str = "", senha: str = "",
              nao_recebidos: list | None = None, observacao: str = "",
              responsavel: dict | None = None, encerrar_auto: bool = True,
              bipados: set | None = None) -> tuple[bool, str]:
    """A farmácia confirma o recebimento com a própria senha.

    `nao_recebidos` são os `id_item` que a farmácia desmarcou (não encontrou):
    item vai para DIVERGÊNCIA, caixa fica bloqueada para conferência, e sai um
    alerta. O resto é recebido. Pode ser confirmada pela própria farmacêutica
    logada (ela digita a senha de novo) ou na tela da sala, com a senha dela.
    """
    dev = db.consultar_um("SELECT * FROM devolucoes WHERE id_devolucao = ?", (texto(id_devolucao),))
    if not dev:
        return False, "Devolução não encontrada."
    if dev["status"] != "pendente":
        return False, "Esta devolução já foi confirmada."
    pend = itens(dev["id_devolucao"], so_pendentes=True)
    if not pend:
        return False, "Não há nada pendente nesta devolução."

    if responsavel:
        # v17 (out/2026): na tela da Farmácia, a ciência é de quem está logado.
        quem = responsavel
    else:
        if not texto(usuario_farmacia) or not senha:
            return False, "A farmácia precisa escolher o próprio nome e digitar a senha para confirmar."
        ok_login, quem = usuarios.autenticar(usuario_farmacia, senha)
        if not ok_login:
            return False, quem
    if quem["papel"] not in ("farmacia", "admin"):
        return False, f"{quem['nome']} não está cadastrado(a) como farmácia e não pode confirmar a devolução."

    faltam = {inteiro(i, 0) for i in (nao_recebidos or [])}
    id_atendimento = dev["id_atendimento"]
    agora = db.agora()
    recebidos, divergentes, ignorados = 0, [], 0
    caixas_para_alertar = []
    try:
        with db.transacao() as conn:
            # v18.4.1: duas ciências ao mesmo tempo — só a primeira vale; a segunda
            # vê a devolução já confirmada e não grava nada.
            st = conn.execute("SELECT status FROM devolucoes WHERE id_devolucao = ?",
                              (dev["id_devolucao"],)).fetchone()
            if not st or st[0] != "pendente":
                raise ErroDeNegocio("Esta devolução já foi confirmada por outra pessoa.")
            ainda = {r[0] for r in conn.execute("SELECT id_item FROM devolucao_itens WHERE id_devolucao = ? "
                                                "AND situacao = 'pendente'", (dev["id_devolucao"],)).fetchall()}
            pend = [i for i in pend if i["id_item"] in ainda]
            for i in pend:
                devolvente = texto(i["devolvido_por"]) or texto(dev["devolvido_por"])
                if i["tipo"] == "caixa" and i["id_item"] in faltam:
                    # v17 (out/2026): a caixa que não voltou continua com o paciente;
                    # a sala confere (usou? bipa no prontuário; está na sala? devolve).
                    db.registrar_evento(
                        conn, tipo="devolucao_nao_recebida", id_atendimento=id_atendimento,
                        usuario=quem["username"], devolvido_por=devolvente, recebido_por=quem["nome"],
                        motivo="Na lista de não utilizados, mas não recebida pela farmácia.",
                        observacao=f"[{i['id_caixa']}] desmarcada por {quem['nome']}; a sala vai conferir")
                    situacao = "nao_recebido"
                    divergentes.append(f"caixa {i['id_caixa']}")
                elif i["tipo"] == "caixa":
                    ok, motivo = caixas_consignado.receber(
                        conn, id_caixa=i["id_caixa"], id_atendimento=id_atendimento,
                        informado=inteiro(i["quantidade"], 0), bipado_por=i["bipado_por"],
                        devolvido_por=devolvente, responsavel=quem,
                        nao_recebida=i["id_item"] in faltam)
                    situacao = "recebido" if ok else "nao_recebido"
                    if ok:
                        recebidos += inteiro(i["quantidade"], 0)
                    else:
                        divergentes.append(f"caixa {i['id_caixa']}")
                        caixas_para_alertar.append((i["id_caixa"], motivo))
                else:
                    atual = conn.execute("SELECT status FROM unidades WHERE id_unidade = ?",
                                         (i["id_unidade"],)).fetchone()
                    status = atual[0] if atual else ""
                    if i["id_item"] in faltam:
                        # v17 (out/2026): o item que não voltou continua com o paciente
                        # (não vai para divergência): a sala confere e bipa o uso ou
                        # devolve; a farmácia conclui.
                        motivo = "Na lista de não utilizados, mas não recebido pela farmácia."
                        db.registrar_evento(
                            conn, tipo="devolucao_nao_recebida", id_unidade=i["id_unidade"],
                            id_atendimento=id_atendimento, status_anterior=status,
                            status_novo=status, usuario=quem["username"], motivo=motivo,
                            devolvido_por=devolvente, recebido_por=quem["nome"],
                            observacao=f"Desmarcado por {quem['nome']}; a sala vai conferir")
                        situacao = "nao_recebido"
                        divergentes.append(i["xProd"] or i["id_unidade"])
                    elif status not in (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA, TRANSITO_SALA, EM_SALA):
                        situacao = "ignorado"
                        ignorados += 1
                    else:
                        farm = conn.execute("SELECT farmacia FROM unidades WHERE id_unidade = ?",
                                            (i["id_unidade"],)).fetchone()
                        volta = estoque_de_volta(farm[0] if farm else "")
                        if status not in (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA):
                            # Tinha sido dispensado para a sala: volta ao estoque da farmácia, sem paciente.
                            conn.execute(
                                """UPDATE unidades SET status = ?, id_atendimento = NULL, atualizado_em = ?,
                                   atualizado_por = ? WHERE id_unidade = ?""",
                                (volta, agora, quem["username"], i["id_unidade"]))
                        db.registrar_evento(
                            conn, tipo=OPERACAO, id_unidade=i["id_unidade"], id_atendimento=id_atendimento,
                            status_anterior=status, status_novo=volta, usuario=i["bipado_por"],
                            devolvido_por=devolvente, recebido_por=quem["nome"],
                            observacao=f"Bipado em {i['bipado_em']}; confirmado pela farmácia")
                        db.registrar_evento(
                            conn, tipo=f"confirmar_{OPERACAO}", id_unidade=i["id_unidade"],
                            id_atendimento=id_atendimento, usuario=quem["username"],
                            devolvido_por=devolvente, recebido_por=quem["nome"],
                            observacao=((f"Ciência de {quem['nome']}" if responsavel else
                                         f"Recebimento confirmado com a senha de {quem['nome']}")
                                        + ("; volta confirmada pelo bip na farmácia"
                                           if bipados and str(i["id_item"]) in bipados else "")
                                        + f"; devolvido por {devolvente}; bipado por {i['bipado_por']}."))
                        situacao = "recebido"
                        recebidos += 1
                conn.execute(
                    "UPDATE devolucao_itens SET situacao = ?, resolvido_em = ?, resolvido_por = ? "
                    "WHERE id_item = ?", (situacao, agora, quem["username"], i["id_item"]))
            conn.execute(
                """UPDATE devolucoes SET status = 'confirmada', confirmada_em = ?, confirmada_por = ?,
                          recebido_por = ?, observacao = ? WHERE id_devolucao = ?""",
                (agora, quem["username"], quem["nome"], texto(observacao), dev["id_devolucao"]))
    except ErroDeNegocio as recusa:
        return False, str(recusa)

    # Alertas depois do commit (cada um abre a própria transação).
    for id_caixa, motivo in caixas_para_alertar:
        caixa = caixas_consignado.buscar(id_caixa)
        caixas_consignado.alertar_bloqueio(
            caixa, id_atendimento, motivo, quem["username"],
            f"Devolvida por {texto(dev['devolvido_por'])}; conferida por {quem['nome']}.")
    if divergentes:
        at = db.consultar_um("SELECT prontuario, sala FROM atendimentos WHERE id_atendimento = ?",
                             (id_atendimento,)) or {}
        alertas.criar(
            modulo_destino="sala-procedimento",
            titulo="Conferir: material que a farmácia não recebeu de volta",
            mensagem=(f"Prontuário {at.get('prontuario') or '—'}, sala {at.get('sala') or '—'}: "
                      f"{quem['nome']} não recebeu {len(divergentes)} item(ns) da lista de não "
                      f"utilizados: {', '.join(divergentes)}. Confira: se foi usado, bipe no "
                      f"prontuário do paciente; se está na sala, devolva à farmácia."),
            usuario=quem["username"], id_atendimento=id_atendimento,
            ids_unidade=[i["id_unidade"] for i in pend if i["id_item"] in faltam and i["tipo"] == "item"],
            link=f"/sala-procedimento/atendimento/{id_atendimento}")

    # v17 (out/2026): sala já finalizou os utilizados e não ficou nada pendente
    # → a ciência da farmácia encerra o procedimento.
    from . import fechamento
    encerrou = encerrar_auto and fechamento.encerrar_se_completo(id_atendimento, quem["username"])

    partes = [f"{recebidos} item(ns) recebido(s) por {quem['nome']}"]
    if divergentes:
        partes.append(f"não recebido(s): {', '.join(divergentes)} — a sala foi avisada para conferir")
    if encerrou:
        partes.append("procedimento encerrado")
    if ignorados:
        partes.append(f"{ignorados} item(ns) já tinham outra situação e ficaram de fora")
    return True, "Ciência da devolução registrada: " + "; ".join(partes) + "."


def identificar_bip(id_devolucao: str, codigo: str) -> dict:
    """Conferência bipando: quais linhas pendentes desta lista o código lido atende.

    Aceita o código de barras do material (também a etiqueta GS1 completa), o
    número de série, o ID da unidade ou o código da caixa. Devolve os itens na
    ordem da lista; a tela marca o primeiro que ainda não foi bipado.
    """
    from ..utils import normalizar_codigo
    bruto = texto(codigo)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    lido = normalizar_codigo(bruto)
    alvos = {bruto.upper(), texto(lido).upper()}
    achados = []
    for i in itens(id_devolucao, so_pendentes=True):
        candidatos = ({texto(i["id_caixa"]).upper()} if i["tipo"] == "caixa" else
                      {texto(normalizar_codigo(i["codigo_barras"] or "")).upper(),
                       texto(i["codigo_barras"]).upper(), texto(i["numero_serie"]).upper(),
                       texto(i["id_unidade"]).upper()})
        if alvos & {c for c in candidatos if c}:
            achados.append(i["id_item"])
    if not achados:
        return {"ok": False, "mensagem": f"O código {bruto} não está nesta lista de não utilizados."}
    return {"ok": True, "itens": achados}


# =========================================================
# v18.2 — balanço do paciente na ciência dos não utilizados
# =========================================================

def balanco(id_devolucao: str) -> dict:
    """Tudo o que foi para o paciente, item a item, e o que aconteceu com cada um.

    Na ciência, a farmácia vê a lista do que mandou (dispensado, inclusive os
    itens das caixas) e cada item vem marcado:
      * ``usado``        — bipado no paciente (com a hora e quem bipou);
      * ``voltando``     — está nesta lista de não utilizados: conferir;
      * ``na_caixa``     — não foi usado e volta dentro de uma caixa desta lista;
      * ``ja_voltou``    — já voltou numa devolução anterior;
      * ``sem_destino``  — não foi usado e não está voltando: a sala precisa
                           bipar o uso ou devolver.
    Também entra o que foi usado sem passar pela dispensação.
    """
    dev = buscar(id_devolucao)
    if not dev:
        return {"linhas": [], "resumo": {}}
    ida = dev["id_atendimento"]
    pend_item = {i["id_unidade"]: i["id_item"] for i in dev["pendentes"] if i["tipo"] == "item" and i["id_unidade"]}
    pend_caixa = {texto(i["id_caixa"]).upper(): i["id_item"] for i in dev["pendentes"] if i["tipo"] == "caixa"}
    linhas = db.consultar(
        """WITH enviados AS (
               SELECT di.id_unidade, MIN(di.bipado_em) AS dispensado_em, MAX(di.id_caixa) AS caixa_envio
               FROM dispensacao_itens di JOIN dispensacoes d ON d.id_dispensacao = di.id_dispensacao
               WHERE d.id_atendimento = ? AND COALESCE(d.status,'') <> 'cancelada'
                 AND COALESCE(di.situacao,'') NOT IN ('removido')
               GROUP BY di.id_unidade
           ), usados AS (
               SELECT id_unidade FROM unidades WHERE id_atendimento = ? AND status = 'utilizado'
           ), todos AS (
               SELECT id_unidade FROM enviados UNION SELECT id_unidade FROM usados
           )
           SELECT u.id_unidade, u.status, u.id_atendimento, u.id_caixa, u.codigo_aghu, u.nLote, u.dVal,
                  u.numero_serie, COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS material,
                  e.dispensado_em, e.caixa_envio,
                  (SELECT ev.data_evento FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.id_atendimento = ? AND ev.tipo IN ('registrar_uso','uso_nao_cadastrado','selecao_manual')
                     ORDER BY ev.id_evento DESC LIMIT 1) AS usado_em,
                  (SELECT ev.usuario FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.id_atendimento = ? AND ev.tipo IN ('registrar_uso','uso_nao_cadastrado','selecao_manual')
                     ORDER BY ev.id_evento DESC LIMIT 1) AS usado_por,
                  (SELECT 1 FROM devolucao_itens di JOIN devolucoes d2 ON d2.id_devolucao = di.id_devolucao
                     WHERE di.id_unidade = u.id_unidade AND d2.id_atendimento = ? AND di.situacao = 'recebido'
                     LIMIT 1) AS ja_voltou
           FROM todos t JOIN unidades u ON u.id_unidade = t.id_unidade
           LEFT JOIN enviados e ON e.id_unidade = u.id_unidade
           ORDER BY material, u.nLote, u.id_unidade""", (ida, ida, ida, ida, ida))
    saida = []
    for l in linhas:
        l = dict(l)
        caixa = texto(l["id_caixa"] or l["caixa_envio"]).upper()
        if l["status"] == "utilizado" and l["id_atendimento"] == ida:
            sit = "usado"
        elif l["id_unidade"] in pend_item:
            sit = "voltando"
            l["id_item"] = pend_item[l["id_unidade"]]
        elif l["id_caixa"] and texto(l["id_caixa"]).upper() in pend_caixa:
            sit = "na_caixa"
            l["id_item"] = pend_caixa[texto(l["id_caixa"]).upper()]
        elif l["ja_voltou"] or l["status"] in ("em_estoque_farmacia", "em_estoque_recebimento"):
            sit = "ja_voltou"
        else:
            sit = "sem_destino"
        l["situacao"] = sit
        l["caixa"] = caixa
        l["sem_dispensacao"] = not l["dispensado_em"]
        l["validade"] = data_br(l["dVal"]) if l.get("dVal") else ""
        saida.append(l)
    conta = {k: sum(1 for l in saida if l["situacao"] == k)
             for k in ("usado", "voltando", "na_caixa", "ja_voltou", "sem_destino")}
    conta["dispensados"] = sum(1 for l in saida if not l["sem_dispensacao"])
    conta["total"] = len(saida)
    return {"linhas": saida, "resumo": conta}
