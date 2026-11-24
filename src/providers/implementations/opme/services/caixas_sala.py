"""Caixa de consignado na SALA pelo dia (turno).

A caixa não vai para um paciente: ela é emprestada a uma sala (unidade + sala)
e fica lá o dia todo, servindo a todos os procedimentos daquela sala.

1. A farmácia ENVIA a caixa para a sala (um bip na caixa). Os itens de dentro
   ficam "dispensado — aguardando a sala", sem paciente.
2. A sala dá CIÊNCIA DA CAIXA (não item a item), no login de quem está logado.
   Os itens passam a "na sala".
3. Em cada procedimento daquela sala, a sala bipa a caixa e o item usado no
   paciente (Registrar uso). O item sai da caixa e vai para o prontuário.
4. Até as 23:59 do dia, a sala DEVOLVE a caixa à farmácia.
5. A farmácia CONFERE A CAIXA: se a quantidade bate, um clique; se não bate,
   desmarca o que faltou — a caixa fica BLOQUEADA com pendência e a sala é
   avisada (se foi uso não bipado, a sala ainda bipa no paciente certo).
   Depois a farmácia reabastece a caixa com o que foi usado.

Para usar a caixa em outra sala, ela precisa voltar à farmácia antes.
"""

from __future__ import annotations

from datetime import datetime

from .. import busca, db, log
from ..erros import ErroDeNegocio
from ..config import UNIDADES_ATIVAS, rotulo_unidade
from ..domain import EM_SALA, ESTOQUE_LIVRE, TRANSITO_SALA, UTILIZADO, estoque_de_volta
from ..utils import gerar_id, hoje_iso, texto
from . import alertas, caixas

ATIVOS = ("enviada", "na_sala", "devolvida")
PAPEIS_DA_SALA = ("sala-procedimento", "supervisao", "admin")

ROTULOS = {
    "enviada": "a caminho da sala — aguardando ciência",
    "na_sala": "na sala",
    "devolvida": "devolvida — aguardando a conferência da farmácia",
    "conferida": "conferida pela farmácia",
    "divergente": "pendência — faltaram itens no retorno",
    "cancelada": "envio cancelado",
}


def _sala(valor) -> str:
    v = texto(valor).strip().upper()
    return v.lstrip("0") or v


def mesma_sala(t: dict, unidade: str, sala: str) -> bool:
    return (texto(t["unidade"]).upper() == texto(unidade).upper()
            and _sala(t["sala"]) == _sala(sala))


def fora_do_prazo(t: dict) -> bool:
    return t["status"] in ("enviada", "na_sala") and db.agora() > texto(t["prazo"])


def _enfeitar(t: dict | None) -> dict | None:
    if not t:
        return None
    t = dict(t)
    t["status_rotulo"] = ROTULOS.get(t["status"], t["status"])
    t["unidade_rotulo"] = rotulo_unidade(t["unidade"])
    t["local"] = f"{t['unidade_rotulo']} — Sala {t['sala']}"
    t["fora_do_prazo"] = fora_do_prazo(t)
    cont = db.consultar(
        """SELECT i.situacao, u.status, u.id_caixa FROM caixa_turno_itens i
           JOIN unidades u ON u.id_unidade = i.id_unidade WHERE i.id_turno = ?""", (t["id_turno"],))
    t["usados"] = sum(1 for c in cont if c["situacao"] == "usado")
    t["restam"] = sum(1 for c in cont if c["situacao"] == "na_caixa")
    t["faltaram"] = sum(1 for c in cont if c["situacao"] == "faltou" and c["status"] == EM_SALA)
    cx = db.consultar_um("SELECT nome, fornecedor FROM caixas WHERE id_caixa = ?", (t["id_caixa"],)) or {}
    t["nome_caixa"] = cx.get("nome") or ""
    t["fornecedor"] = cx.get("fornecedor") or ""
    return t


def buscar(id_turno: str) -> dict | None:
    return _enfeitar(db.consultar_um("SELECT * FROM caixa_turnos WHERE id_turno = ?", (texto(id_turno),)))


def ativo_da_caixa(id_caixa: str) -> dict | None:
    return _enfeitar(db.consultar_um(
        f"""SELECT * FROM caixa_turnos WHERE UPPER(id_caixa) = UPPER(?)
            AND status IN ({','.join('?' for _ in ATIVOS)}) ORDER BY enviada_em DESC LIMIT 1""",
        (texto(id_caixa), *ATIVOS)))


def pendente_da_caixa(id_caixa: str) -> dict | None:
    """Último turno da caixa com pendência (faltaram itens no retorno)."""
    return _enfeitar(db.consultar_um(
        """SELECT * FROM caixa_turnos WHERE UPPER(id_caixa) = UPPER(?) AND status = 'divergente'
           ORDER BY enviada_em DESC LIMIT 1""", (texto(id_caixa),)))


def listar(unidade: str = "", status: tuple = ATIVOS + ("divergente",), limite: int = 200) -> list[dict]:
    params: list = list(status)
    filtro = ""
    if texto(unidade):
        filtro = " AND unidade = ?"
        params.append(texto(unidade))
    params.append(limite)
    linhas = db.consultar(
        f"""SELECT * FROM caixa_turnos WHERE status IN ({','.join('?' for _ in status)}){filtro}
            ORDER BY enviada_em DESC LIMIT ?""", params)
    return [_enfeitar(l) for l in linhas]


def contar(unidade: str = "") -> dict:
    ls = listar(unidade)
    return {"enviadas": sum(1 for t in ls if t["status"] == "enviada"),
            "na_sala": sum(1 for t in ls if t["status"] == "na_sala"),
            "devolvidas": sum(1 for t in ls if t["status"] == "devolvida"),
            "divergentes": sum(1 for t in ls if t["status"] == "divergente"),
            "fora_do_prazo": sum(1 for t in ls if t["fora_do_prazo"])}


def itens(id_turno: str) -> list[dict]:
    return db.consultar(
        """SELECT i.situacao, i.id_atendimento, u.id_unidade, u.codigo_aghu, u.codigo_barras, u.numero_serie,
                  COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS produto, u.nLote, u.dVal,
                  u.status, a.prontuario, a.paciente, a.especialidade,
                  (SELECT ev.data_evento FROM eventos ev WHERE ev.id_unidade = u.id_unidade AND ev.tipo = 'registrar_uso'
                     AND ev.id_atendimento = i.id_atendimento ORDER BY ev.id_evento DESC LIMIT 1) AS usado_em,
                  (SELECT ev.usuario FROM eventos ev WHERE ev.id_unidade = u.id_unidade AND ev.tipo = 'registrar_uso'
                     AND ev.id_atendimento = i.id_atendimento ORDER BY ev.id_evento DESC LIMIT 1) AS usado_por
           FROM caixa_turno_itens i JOIN unidades u ON u.id_unidade = i.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = i.id_atendimento
           WHERE i.id_turno = ? ORDER BY produto, u.nLote, u.id_unidade""", (texto(id_turno),))


def identificar_item(id_turno: str, codigo: str) -> dict:
    """v18.2 — conferência do retorno bipando: quais itens que devem voltar o código atende."""
    from ..utils import normalizar_codigo
    from .. import gs1
    bruto = texto(codigo)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    alvos = {bruto.upper(), texto(normalizar_codigo(bruto)).upper()}
    etiqueta = busca.interpretar(bruto)
    achados = []
    for i in itens(id_turno):
        if i["situacao"] != "na_caixa":
            continue
        cods = {texto(i["codigo_barras"]).upper(), texto(normalizar_codigo(i["codigo_barras"] or "")).upper(),
                texto(i["numero_serie"]).upper(), texto(i["id_unidade"]).upper()} - {""}
        if cods & alvos:
            achados.append(i)
    if etiqueta and etiqueta.get("lote") and achados:
        do_lote = [i for i in achados if gs1._confere(i["nLote"], etiqueta["lote"], etiqueta.get("lote_ate_o_fim"))]
        achados = do_lote or achados
    if not achados:
        return {"ok": False, "mensagem": f"O código {bruto} não está entre os itens que devem voltar nesta caixa."}
    return {"ok": True, "itens": [i["id_unidade"] for i in achados]}


# ------------------------------------------------------------------ 1. envio

def enviar(id_caixa: str, unidade: str, sala: str, usuario: str) -> tuple[bool, str, str]:
    cx = db.consultar_um("SELECT * FROM caixas WHERE UPPER(id_caixa) = UPPER(?)", (texto(id_caixa),))
    if not cx:
        return False, f"Caixa {texto(id_caixa)} não encontrada.", ""
    if cx["encerrada_em"]:
        return False, "Esta caixa foi encerrada.", ""
    if cx["bloqueada"]:
        return False, (f"A caixa {cx['id_caixa']} está BLOQUEADA ({texto(cx['bloqueio_motivo'])}). "
                       f"Confira e libere antes de enviar."), ""
    unidade = texto(unidade).upper()
    if unidade not in UNIDADES_ATIVAS or not texto(sala):
        return False, "Escolha a unidade e a sala de destino.", ""
    local_cx = texto(cx["local"]) if "local" in cx.keys() else ""
    if local_cx == "almoxarifado":
        return False, f"A caixa {cx['id_caixa']} está no almoxarifado. O almoxarifado dispensa para a farmácia primeiro.", ""
    if local_cx == "transito":
        return False, (f"A caixa {cx['id_caixa']} está a caminho da farmácia. Dê ciência do recebimento "
                       "(Farmácia → Caixas de consignado) antes de enviar para a sala."), ""
    ativo = ativo_da_caixa(cx["id_caixa"])
    if ativo:
        return False, (f"A caixa {cx['id_caixa']} já está fora da farmácia ({ativo['local']}, "
                       f"{ativo['status_rotulo']}). Para ir a outra sala, ela precisa voltar à farmácia."), ""
    dentro = db.consultar("SELECT id_unidade, status, nLote, codigo_aghu FROM unidades WHERE id_caixa = ?",
                          (cx["id_caixa"],))
    from . import recall  # v18.4.1: caixa com lote em recall não vai para a sala
    travadas = recall.bloqueadas([dict(u) for u in dentro if u["status"] in ESTOQUE_LIVRE])
    if travadas:
        u, b = travadas[0]
        return False, (f"A caixa {cx['id_caixa']} tem material de lote em RECALL. "
                       + recall.mensagem_bloqueio(u, b) + " Tire o item da caixa antes de enviar."), ""
    if any(u["status"] in (TRANSITO_SALA, EM_SALA) for u in dentro):
        return False, (f"A caixa {cx['id_caixa']} está dispensada para um paciente. Ela precisa voltar "
                       f"à farmácia antes de ir para a sala pelo dia."), ""
    livres = [u for u in dentro if u["status"] in ESTOQUE_LIVRE]
    if not livres:
        return False, f"A caixa {cx['id_caixa']} está vazia no sistema.", ""
    hoje = hoje_iso()
    id_turno = gerar_id("CT")
    agora = db.agora()
    marcador = f"[{cx['id_caixa']}]"
    destino = f"{rotulo_unidade(unidade)} — Sala {texto(sala)}"
    try:
        with db.transacao() as conn:
            conn.execute(
                """INSERT INTO caixa_turnos (id_turno, id_caixa, unidade, sala, data, prazo, status, qtd_enviada,
                                             enviada_em, enviada_por)
                   VALUES (?,?,?,?,?,?,'enviada',?,?,?)""",
                (id_turno, cx["id_caixa"], unidade, texto(sala), hoje, f"{hoje}T23:59:59", len(livres),
                 agora, usuario))
            # v18.4.1: a caixa não pode ter saído para outra sala enquanto isto rodava.
            # v18.4.2: recall e validade conferidos DENTRO da transação.
            from . import recall
            dados = [dict(r) for r in conn.execute(
                "SELECT id_unidade, nLote, codigo_aghu, dVal FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],))
                if r["id_unidade"] in {x["id_unidade"] for x in livres}]
            travadas = recall.bloqueadas(dados, conn)
            if travadas:
                u, b = travadas[0]
                raise ErroDeNegocio(f"A caixa {cx['id_caixa']} tem material de lote em RECALL. "
                                    + recall.mensagem_bloqueio(u, b) + " Tire o item da caixa antes de enviar.")
            vencidos = [d for d in dados if texto(d.get("dVal")) and texto(d["dVal"])[:10] < hoje]
            if vencidos:
                raise ErroDeNegocio(f"A caixa {cx['id_caixa']} tem {len(vencidos)} item(ns) VENCIDO(S) "
                                    f"(lote {vencidos[0]['nLote'] or '—'}). Tire da caixa antes de enviar.")
            if conn.execute(f"SELECT 1 FROM caixa_turnos WHERE id_caixa = ? AND status IN ({','.join('?' for _ in ATIVOS)}) "
                            "AND id_turno <> ?", (cx["id_caixa"], *ATIVOS, id_turno)).fetchone():
                raise ErroDeNegocio(f"A caixa {cx['id_caixa']} acabou de ser enviada por outra pessoa.")
            for u in livres:
                cur = conn.execute("""UPDATE unidades SET status = ?, id_atendimento = NULL, atualizado_em = ?,
                                      atualizado_por = ? WHERE id_unidade = ? AND status = ?""",
                                   (TRANSITO_SALA, agora, usuario, u["id_unidade"], u["status"]))
                if cur.rowcount != 1:
                    raise ErroDeNegocio("Um item da caixa acabou de ser movimentado por outra pessoa. Tente de novo.")
                conn.execute("INSERT INTO caixa_turno_itens (id_turno, id_unidade) VALUES (?,?)",
                             (id_turno, u["id_unidade"]))
                db.registrar_evento(conn, tipo="caixa_para_sala", id_unidade=u["id_unidade"],
                                    status_anterior=u["status"], status_novo=TRANSITO_SALA, usuario=usuario,
                                    observacao=f"{marcador} caixa enviada para {destino} (pelo dia; {id_turno})")
            db.registrar_evento(conn, tipo="caixa_para_sala", usuario=usuario,
                                motivo=f"{len(livres)} item(ns) na caixa",
                                observacao=f"{marcador} caixa enviada para {destino} (pelo dia; {id_turno})")
    except ErroDeNegocio as recusa:
        return False, str(recusa), ""
    log.info(f"caixa enviada à sala · {cx['id_caixa']} · {destino}", usuario)
    return True, (f"Caixa {cx['id_caixa']} enviada para {destino} com {len(livres)} item(ns). "
                  f"A sala dá ciência da caixa; ela deve voltar à farmácia até as 23:59 de hoje."), id_turno


def cancelar_envio(id_turno: str, usuario: str) -> tuple[bool, str]:
    t = buscar(id_turno)
    if not t or t["status"] != "enviada":
        return False, "Só dá para cancelar o envio antes de a sala dar ciência."
    agora = db.agora()
    with db.transacao() as conn:
        for i in conn.execute("SELECT id_unidade FROM caixa_turno_itens WHERE id_turno = ?", (t["id_turno"],)).fetchall():
            farm = conn.execute("SELECT farmacia FROM unidades WHERE id_unidade = ?", (i[0],)).fetchone()
            volta = estoque_de_volta(farm[0] if farm else "")
            conn.execute("""UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                            WHERE id_unidade = ? AND status = ?""", (volta, agora, usuario, i[0], TRANSITO_SALA))
        conn.execute("UPDATE caixa_turnos SET status = 'cancelada', observacao = ? WHERE id_turno = ?",
                     (f"envio cancelado por {usuario} em {agora}", t["id_turno"]))
        db.registrar_evento(conn, tipo="caixa_envio_cancelado", usuario=usuario,
                            observacao=f"[{t['id_caixa']}] envio para {t['local']} cancelado")
    return True, f"Envio da caixa {t['id_caixa']} cancelado. Os itens voltaram ao estoque da farmácia."


# ------------------------------------------------------------------ 2. ciência da sala

def _quem(logado: dict) -> tuple[bool, str]:
    if not logado or logado.get("papel") not in PAPEIS_DA_SALA:
        return False, "Quem dá ciência da caixa é a sala de procedimento. Entre com o usuário da sala."
    return True, ""


def receber(ids_turno: list[str], logado: dict) -> tuple[bool, str]:
    ok, msg = _quem(logado)
    if not ok:
        return False, msg
    ids = [texto(i) for i in ids_turno if texto(i)]
    if not ids:
        return False, "Marque (ou bipe) a caixa que chegou."
    agora, feitas = db.agora(), []
    nome = logado.get("nome") or logado["username"]
    with db.transacao() as conn:
        for id_turno in ids:
            t = conn.execute("SELECT * FROM caixa_turnos WHERE id_turno = ?", (id_turno,)).fetchone()
            if not t or t["status"] != "enviada":
                continue
            conn.execute("""UPDATE caixa_turnos SET status = 'na_sala', recebida_em = ?, recebida_por = ?,
                            recebida_nome = ? WHERE id_turno = ?""", (agora, logado["username"], nome, id_turno))
            for (id_unidade,) in conn.execute("SELECT id_unidade FROM caixa_turno_itens WHERE id_turno = ?",
                                              (id_turno,)).fetchall():
                conn.execute("""UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                                WHERE id_unidade = ? AND status = ?""",
                             (EM_SALA, agora, logado["username"], id_unidade, TRANSITO_SALA))
            db.registrar_evento(conn, tipo="caixa_recebida_sala", usuario=logado["username"], recebido_por=nome,
                                observacao=f"[{t['id_caixa']}] ciência da caixa na sala {t['sala']} "
                                           f"({t['qtd_enviada']} item(ns)), por {nome}")
            feitas.append(t["id_caixa"])
    if not feitas:
        return False, "Nenhuma caixa aguardando ciência foi marcada."
    return True, f"Ciência registrada da(s) caixa(s) {', '.join(feitas)}, em nome de {nome}."


def identificar(codigo: str, unidade: str = "") -> dict:
    """Bip da caixa na tela da sala: devolve o turno ativo dela."""
    from ..utils import normalizar_codigo
    t = ativo_da_caixa(normalizar_codigo(codigo))
    if not t or (texto(unidade) and t["unidade"] != texto(unidade)):
        return {"ok": False, "mensagem": f"{codigo}: esta caixa não foi enviada para esta unidade."}
    return {"ok": True, "id_turno": t["id_turno"], "status": t["status"], "id_caixa": t["id_caixa"]}


# ------------------------------------------------------------------ 3. uso

def permite_uso(id_caixa: str, id_atendimento: str) -> tuple[bool | None, str, int]:
    """A caixa pode ser aberta no registro de uso deste atendimento?

    None = a caixa não está numa sala (regra antiga vale). True/False com o motivo.
    """
    at = db.consultar_um("SELECT unidade, sala FROM atendimentos WHERE id_atendimento = ?",
                         (texto(id_atendimento),)) or {}
    t = ativo_da_caixa(id_caixa)
    if t:
        if not mesma_sala(t, at.get("unidade"), at.get("sala")):
            return False, (f"A caixa {t['id_caixa']} está na {t['local']}. Só pode ser usada nos procedimentos "
                           f"dessa sala; para outra sala ela precisa voltar à farmácia."), 0
        if t["status"] == "enviada":
            return False, (f"A caixa {t['id_caixa']} chegou, mas a sala ainda não deu ciência. Dê ciência em "
                           f"Sala de procedimento → Caixas na sala antes de usar."), 0
        if t["status"] == "devolvida":
            return False, (f"A caixa {t['id_caixa']} já foi devolvida à farmácia e está aguardando a "
                           f"conferência."), 0
        return True, "", t["restam"]
    p = pendente_da_caixa(id_caixa)
    if p and p["faltaram"] and mesma_sala(p, at.get("unidade"), at.get("sala")):
        return True, "pendencia", p["faltaram"]
    return None, "", 0


def marcar_uso(conn, id_unidade: str, id_atendimento: str) -> None:
    conn.execute(
        f"""UPDATE caixa_turno_itens SET situacao = 'usado', id_atendimento = ?
            WHERE id_unidade = ? AND situacao IN ('na_caixa', 'faltou') AND id_turno IN (
                SELECT id_turno FROM caixa_turnos WHERE status IN ('na_sala', 'divergente'))""",
        (id_atendimento, id_unidade))


def desmarcar_uso(conn, id_unidade: str) -> None:
    """Bip de uso excluído: o item volta a constar na caixa do turno."""
    conn.execute(
        """UPDATE caixa_turno_itens SET situacao = CASE
                 WHEN (SELECT status FROM caixa_turnos t WHERE t.id_turno = caixa_turno_itens.id_turno) = 'divergente'
                 THEN 'faltou' ELSE 'na_caixa' END, id_atendimento = NULL
           WHERE id_unidade = ? AND situacao = 'usado' AND id_turno IN (
                SELECT id_turno FROM caixa_turnos WHERE status IN ('na_sala', 'divergente'))""", (id_unidade,))


def item_do_turno(id_unidade: str) -> bool:
    return bool(db.escalar(
        """SELECT 1 FROM caixa_turno_itens i JOIN caixa_turnos t ON t.id_turno = i.id_turno
           WHERE i.id_unidade = ? AND t.status IN ('na_sala', 'divergente')""", (texto(id_unidade),)))


# ------------------------------------------------------------------ 4. devolução pela sala

def devolver(id_turno: str, logado: dict) -> tuple[bool, str]:
    ok, msg = _quem(logado)
    if not ok:
        return False, msg
    t = buscar(id_turno)
    if not t or t["status"] != "na_sala":
        return False, "Esta caixa não está na sala (já foi devolvida ou ainda aguarda ciência)."
    nome = logado.get("nome") or logado["username"]
    with db.transacao() as conn:
        conn.execute("""UPDATE caixa_turnos SET status = 'devolvida', devolvida_em = ?, devolvida_por = ?,
                        devolvida_nome = ? WHERE id_turno = ?""", (db.agora(), logado["username"], nome, t["id_turno"]))
        db.registrar_evento(conn, tipo="caixa_devolvida_sala", usuario=logado["username"], devolvido_por=nome,
                            motivo=f"{t['usados']} usado(s), {t['restam']} devem voltar",
                            observacao=f"[{t['id_caixa']}] caixa devolvida pela sala {t['sala']} à farmácia")
    alertas.criar(modulo_destino="farmacia", titulo=f"Caixa {t['id_caixa']} devolvida — conferir",
                  mensagem=(f"A {t['local']} devolveu a caixa {t['id_caixa']}: {t['restam']} item(ns) devem "
                            f"voltar ({t['usados']} usado(s) nos pacientes)."),
                  usuario=logado["username"], link=f"/farmacia/caixas-sala/{t['id_turno']}")
    return True, (f"Caixa {t['id_caixa']} devolvida à farmácia: {t['restam']} item(ns) devem voltar. "
                  f"A farmácia confere a caixa.")


# ------------------------------------------------------------------ 5. conferência da farmácia

def conferir(id_turno: str, logado: dict, presentes: set[str] | None) -> tuple[bool, str]:
    """`presentes` = None → a contagem confere (tudo voltou). Senão, os ids que voltaram."""
    t = buscar(id_turno)
    if not t or t["status"] != "devolvida":
        return False, "Esta caixa não está aguardando conferência."
    nome = logado.get("nome") or logado["username"]
    agora = db.agora()
    marcador = f"[{t['id_caixa']}]"
    devem = [i for i in itens(t["id_turno"]) if i["situacao"] == "na_caixa"]
    voltou = devem if presentes is None else [i for i in devem if i["id_unidade"] in presentes]
    faltou = [i for i in devem if i not in voltou]
    with db.transacao() as conn:
        for i in voltou:
            farm = conn.execute("SELECT farmacia FROM unidades WHERE id_unidade = ?", (i["id_unidade"],)).fetchone()
            volta = estoque_de_volta(farm[0] if farm else "")
            conn.execute("""UPDATE unidades SET status = ?, id_atendimento = NULL, atualizado_em = ?,
                            atualizado_por = ? WHERE id_unidade = ?""", (volta, agora, logado["username"], i["id_unidade"]))
            conn.execute("UPDATE caixa_turno_itens SET situacao = 'voltou' WHERE id_turno = ? AND id_unidade = ?",
                         (t["id_turno"], i["id_unidade"]))
            db.registrar_evento(conn, tipo="caixa_retorno_conferido", id_unidade=i["id_unidade"],
                                status_anterior=i["status"], status_novo=volta, usuario=logado["username"],
                                recebido_por=nome, devolvido_por=t.get("devolvida_nome") or "",
                                observacao=f"{marcador} voltou na caixa da {t['local']}; conferido por {nome}")
        for i in faltou:
            conn.execute("UPDATE caixa_turno_itens SET situacao = 'faltou' WHERE id_turno = ? AND id_unidade = ?",
                         (t["id_turno"], i["id_unidade"]))
            db.registrar_evento(conn, tipo="caixa_item_faltou", id_unidade=i["id_unidade"],
                                status_anterior=i["status"], status_novo=i["status"], usuario=logado["username"],
                                observacao=f"{marcador} não voltou na caixa da {t['local']}")
        status = "divergente" if faltou else "conferida"
        conn.execute("""UPDATE caixa_turnos SET status = ?, conferida_em = ?, conferida_por = ?, conferida_nome = ?,
                        qtd_usada = ?, qtd_voltou = ?, qtd_faltou = ? WHERE id_turno = ?""",
                     (status, agora, logado["username"], nome, t["usados"], len(voltou), len(faltou), t["id_turno"]))
        motivo = ""
        if faltou:
            motivo = (f"Retorno da {t['local']}: faltaram {len(faltou)} item(ns) de {len(devem)}.")
            conn.execute("""UPDATE caixas SET bloqueada = 1, bloqueio_motivo = ?, bloqueio_atendimento = NULL,
                            bloqueada_em = ?, bloqueada_por = ? WHERE id_caixa = ?""",
                         (motivo, agora, logado["username"], t["id_caixa"]))
        db.registrar_evento(conn, tipo="caixa_conferida_farmacia", usuario=logado["username"], recebido_por=nome,
                            motivo=f"{len(voltou)} voltaram, {len(faltou)} faltaram, {t['usados']} usados",
                            observacao=f"{marcador} retorno da {t['local']} conferido por {nome}")
    if faltou:
        lista = "; ".join(f"{i['produto']} (lote {i['nLote'] or '—'})" for i in faltou[:10])
        alertas.criar(modulo_destino="sala-procedimento",
                      titulo=f"Caixa {t['id_caixa']}: {len(faltou)} item(ns) não voltaram",
                      mensagem=(f"Na conferência da farmácia faltaram: {lista}. Se algum foi usado e não bipado, "
                                f"bipe a caixa e o item no paciente certo (Registrar uso). Se não, avise a farmácia."),
                      usuario=logado["username"], link="/sala-procedimento/caixas")
        alertas.criar(modulo_destino="farmacia", titulo=f"Caixa {t['id_caixa']} BLOQUEADA — faltaram itens",
                      mensagem=motivo + " A sala foi avisada. Depois de resolver, confira e libere a caixa.",
                      usuario=logado["username"], link=f"/farmacia/caixas-consignado/{t['id_caixa']}")
        return True, (f"{len(voltou)} item(ns) voltaram ao estoque. {len(faltou)} NÃO voltaram: a caixa "
                      f"{t['id_caixa']} ficou BLOQUEADA com pendência e a sala foi avisada.")
    return True, (f"Caixa {t['id_caixa']} conferida: {len(voltou)} item(ns) voltaram ao estoque"
                  + (f", {t['usados']} usado(s) nos pacientes — reabasteça a caixa." if t["usados"] else "."))


def liberar_pendencias_da_caixa(conn, id_caixa: str) -> None:
    """Chamado quando a farmácia confere e libera a caixa bloqueada."""
    conn.execute("UPDATE caixa_turnos SET status = 'conferida' WHERE UPPER(id_caixa) = UPPER(?) AND status = 'divergente'",
                 (texto(id_caixa),))


def para_relatorio(inicio: str, fim: str, farmacia: str = "", termo: str = "") -> list[dict]:
    """Linhas do relatório de movimentações de dispensa (farmácia → sala, caixa do dia)."""
    from ..config import FARMACIAS, rotulo_farmacia
    from ..domain import rotulo
    params: list = [inicio, fim]
    filtro = ""
    if farmacia:
        filtro += " AND t.unidade = ?"
        params.append(farmacia)
    if texto(termo):
        filtro += (" AND (u.codigo_aghu LIKE ? OR u.xProd LIKE ? OR u.nLote LIKE ? OR u.numero_serie LIKE ?"
                   " OR t.id_caixa LIKE ?)")
        params += [f"%{texto(termo)}%"] * 5
    linhas = db.consultar(
        f"""SELECT t.*, i.situacao AS sit_item, u.id_unidade, u.codigo_aghu, u.nLote, u.dVal, u.numero_serie,
                   COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS descricao, u.status AS status_atual,
                   a.prontuario, a.paciente, a.especialidade
            FROM caixa_turnos t JOIN caixa_turno_itens i ON i.id_turno = t.id_turno
            JOIN unidades u ON u.id_unidade = i.id_unidade
            LEFT JOIN atendimentos a ON a.id_atendimento = i.id_atendimento
            WHERE date(t.enviada_em) BETWEEN date(?) AND date(?){filtro}""", params)
    sit = {"na_caixa": "na caixa", "usado": "usado no paciente", "voltou": "voltou na caixa",
           "faltou": "não voltou na caixa"}
    saida = []
    for l in linhas:
        farm = l["unidade"]
        saida.append({
            "data": l["enviada_em"], "tipo": "Farmácia → Sala (caixa do dia)",
            "origem": rotulo_farmacia(farm) if farm in FARMACIAS else "Farmácia",
            "destino": f"Sala {l['sala']}", "documento": f"{l['id_caixa']} · {l['id_turno']}",
            "prontuario": l["prontuario"] or "", "paciente": l["paciente"] or "",
            "unidade": rotulo_unidade(farm), "sala": l["sala"], "especialidade": l["especialidade"] or "",
            "codigo_aghu": l["codigo_aghu"] or "", "descricao": l["descricao"] or "", "lote": l["nLote"] or "",
            "validade": l["dVal"], "serie": l["numero_serie"] or "", "por": l["enviada_por"] or "",
            "situacao": f"caixa {ROTULOS.get(l['status'], l['status'])} · item {sit.get(l['sit_item'], l['sit_item'])}",
            "conta": l["status"] != "cancelada",
            "recebido_por": l["recebida_nome"] or "", "situacao_atual": rotulo(l["status_atual"] or ""),
            "id_unidade": l["id_unidade"], "chave_farmacia": farm,
        })
    return saida
