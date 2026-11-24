"""Envio de material do almoxarifado para a farmácia (out/2026).

1. O ALMOXARIFADO escolhe a farmácia (Bloco Cirúrgico ou Hemodinâmica), bipa
   os materiais (com quantidade por bip) e finaliza o envio. Cada item bipado já
   sai do estoque do almoxarifado: fica "em trânsito para a farmácia".
2. A FARMÁCIA confere e dá ciência — pela lista (desmarca o que não chegou) ou
   bipando (só o bipado conta como recebido). O recebido entra no estoque DELA;
   a farmácia só dispensa para a sala o que está no estoque dela.
3. O que não foi recebido vira PENDÊNCIA do envio, com alerta para os dois
   lados. Tratativa: "recebi depois" (farmácia), "voltou ao almoxarifado" ou
   "divergência/extravio" (almoxarifado, com motivo).

nov/2026:
* Enquanto a farmácia não dá ciência, o almoxarifado pode CANCELAR o envio
  (com motivo): tudo volta ao estoque do almoxarifado.
* O caminho inverso usa a mesma estrutura (`sentido = 'farmacia_almox'`): a
  FARMÁCIA bipa o que devolve ao almoxarifado (sai do estoque dela, "em
  devolução para o almoxarifado") e o ALMOXARIFADO dá ciência — bipando ou
  clicando em "dar ciência" com a lista. A farmácia pode cancelar a devolução
  enquanto o almoxarifado não deu ciência.

v18 (dez/2026): TRANSFERÊNCIA entre farmácias (`sentido = 'farmacia_farmacia'`).
A farmácia de origem (Bloco ↔ Hemodinâmica) bipa o que vai mandar — sai do
estoque dela, "em trânsito para a farmácia" já com a farmácia de destino — e a
farmácia de DESTINO confere e dá ciência na mesma tela de "Receber". `farmacia`
é sempre o destino; `farmacia_origem` guarda de onde saiu. A origem pode
cancelar enquanto o destino não deu ciência (tudo volta ao estoque dela).
"""

from __future__ import annotations

from .. import busca, db, gs1, log
from ..erros import ErroDeNegocio
from ..config import FARMACIAS, rotulo_farmacia
from ..domain import (DIVERGENCIA, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, TRANSITO_ALMOX,
                      TRANSITO_FARMACIA)
from ..utils import data_br, data_hora_br, gerar_id, hoje_iso, inteiro, normalizar_codigo, texto

ENVIO = "almox_farmacia"        # almoxarifado → farmácia
DEVOLUCAO = "farmacia_almox"    # farmácia → almoxarifado (nov/2026)
TRANSFERENCIA = "farmacia_farmacia"  # farmácia → outra farmácia (v18)
SENTIDOS = (ENVIO, DEVOLUCAO, TRANSFERENCIA)

ORIGEM = {ENVIO: EM_ESTOQUE_RECEBIMENTO, DEVOLUCAO: EM_ESTOQUE_FARMACIA, TRANSFERENCIA: EM_ESTOQUE_FARMACIA}
TRANSITO = {ENVIO: TRANSITO_FARMACIA, DEVOLUCAO: TRANSITO_ALMOX, TRANSFERENCIA: TRANSITO_FARMACIA}
DESTINO = {ENVIO: EM_ESTOQUE_FARMACIA, DEVOLUCAO: EM_ESTOQUE_RECEBIMENTO, TRANSFERENCIA: EM_ESTOQUE_FARMACIA}

TRATATIVAS = {
    "recebido_depois": "Recebido depois pela farmácia",
    "voltou_almoxarifado": "Voltou ao estoque do almoxarifado",
    "divergencia": "Divergência / extravio",
}
TRATATIVAS_DEVOLUCAO = {
    "recebido_depois": "Recebido depois pelo almoxarifado",
    "voltou_farmacia": "Voltou ao estoque da farmácia",
    "divergencia": "Divergência / extravio",
}
TRATATIVAS_TRANSFERENCIA = {
    "recebido_depois": "Recebido depois pela farmácia de destino",
    "voltou_origem": "Voltou ao estoque da farmácia de origem",
    "divergencia": "Divergência / extravio",
}


def outra_farmacia(farmacia: str) -> str:
    """A outra farmácia (só há duas: Bloco Cirúrgico e Hemodinâmica)."""
    f = texto(farmacia).upper()
    outras = [k for k in FARMACIAS if k != f]
    return outras[0] if f in FARMACIAS and outras else ""


def _sentido(valor) -> str:
    return valor if valor in SENTIDOS else ENVIO


def tratativas_de(sentido: str) -> dict:
    s = _sentido(sentido)
    return {DEVOLUCAO: TRATATIVAS_DEVOLUCAO, TRANSFERENCIA: TRATATIVAS_TRANSFERENCIA}.get(s, TRATATIVAS)


def _nomes(sentido: str, farmacia: str, farmacia_origem: str = "") -> dict:
    """Textos de cada lado, para as mensagens servirem aos três sentidos."""
    f = rotulo_farmacia(farmacia)
    if _sentido(sentido) == TRANSFERENCIA:
        o = rotulo_farmacia(farmacia_origem)
        return {"origem": f"estoque da {o}", "destino": f, "documento": "Transferência",
                "quem_recebe": f"a {f}"}
    if _sentido(sentido) == DEVOLUCAO:
        return {"origem": f"estoque da {f}", "destino": "almoxarifado", "documento": "Devolução",
                "quem_recebe": "o almoxarifado"}
    return {"origem": "estoque do almoxarifado", "destino": f, "documento": "Envio",
            "quem_recebe": "a farmácia"}


# ---------------------------------------------------------------- consultas

def buscar(id_remessa: str) -> dict | None:
    r = db.consultar_um("SELECT * FROM remessas WHERE id_remessa = ?", (texto(id_remessa),))
    if not r:
        return None
    r = dict(r)
    r["sentido"] = _sentido(r.get("sentido"))
    r["farmacia_rotulo"] = rotulo_farmacia(r["farmacia"])
    r["farmacia_origem_rotulo"] = rotulo_farmacia(r.get("farmacia_origem")) if r.get("farmacia_origem") else ""
    r["nomes"] = _nomes(r["sentido"], r["farmacia"], r.get("farmacia_origem") or "")
    r["tratativas"] = tratativas_de(r["sentido"])
    r["itens"] = itens(r["id_remessa"])
    r["pendentes"] = [i for i in r["itens"] if i["situacao"] == "pendente"]
    return r


def itens(id_remessa: str, situacao: str = "") -> list[dict]:
    filtro = "AND i.situacao = ?" if situacao else "AND i.situacao <> 'removido'"
    params = (texto(id_remessa), situacao) if situacao else (texto(id_remessa),)
    linhas = db.consultar(
        f"""SELECT i.*, u.codigo_aghu, u.xProd, u.descritivo_hospital, u.nLote, u.dVal, u.codigo_barras,
                   u.numero_serie, u.status AS status_unidade, u.marca_fabricante, u.fornecedor
            FROM remessa_itens i LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
            WHERE i.id_remessa = ? {filtro} ORDER BY i.id_item DESC""", params)
    for l in linhas:
        l["descricao"] = l["descritivo_hospital"] or l["xProd"] or ""
        l["validade"] = data_br(l["dVal"]) or "—"
    return linhas


def listar(status: str = "", farmacia: str = "", limite: int = 100, sentido: str = ENVIO,
           farmacia_origem: str = "") -> list[dict]:
    cond, params = ["COALESCE(r.sentido, 'almox_farmacia') = ?"], [_sentido(sentido)]
    if status:
        cond.append("r.status = ?"); params.append(status)
    if farmacia:
        cond.append("r.farmacia = ?"); params.append(farmacia)
    if farmacia_origem:
        cond.append("r.farmacia_origem = ?"); params.append(farmacia_origem)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    linhas = db.consultar(
        f"""SELECT r.*,
                   (SELECT COUNT(*) FROM remessa_itens i WHERE i.id_remessa = r.id_remessa
                      AND i.situacao <> 'removido') AS qtd,
                   (SELECT COUNT(*) FROM remessa_itens i WHERE i.id_remessa = r.id_remessa
                      AND i.situacao = 'nao_recebido' AND COALESCE(i.tratativa,'') = '') AS nao_recebidos
            FROM remessas r {where} ORDER BY COALESCE(r.enviada_em, r.criado_em) DESC LIMIT {int(limite)}""",
        tuple(params))
    for l in linhas:
        l["farmacia_rotulo"] = rotulo_farmacia(l["farmacia"])
        l["farmacia_origem_rotulo"] = rotulo_farmacia(l.get("farmacia_origem")) if l.get("farmacia_origem") else ""
    return linhas


def pendencias(farmacia: str = "", sentido: str = ENVIO, farmacia_origem: str = "") -> list[dict]:
    """Itens que o destino não recebeu e ainda não tiveram tratativa."""
    filtro, params = "AND COALESCE(r.sentido, 'almox_farmacia') = ?", [_sentido(sentido)]
    if farmacia:
        filtro += " AND r.farmacia = ?"
        params.append(farmacia)
    if farmacia_origem:
        filtro += " AND r.farmacia_origem = ?"
        params.append(farmacia_origem)
    linhas = db.consultar(
        f"""SELECT i.*, r.farmacia, r.farmacia_origem, r.enviada_em, r.conferida_em, r.conferida_nome, u.codigo_aghu, u.xProd,
                   u.descritivo_hospital, u.nLote, u.dVal, u.codigo_barras
            FROM remessa_itens i JOIN remessas r ON r.id_remessa = i.id_remessa
            LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
            WHERE i.situacao = 'nao_recebido' AND COALESCE(i.tratativa,'') = '' {filtro}
            ORDER BY r.conferida_em DESC, i.id_item""", tuple(params))
    for l in linhas:
        l["descricao"] = l["descritivo_hospital"] or l["xProd"] or ""
        l["validade"] = data_br(l["dVal"]) or "—"
        l["farmacia_rotulo"] = rotulo_farmacia(l["farmacia"])
        l["farmacia_origem_rotulo"] = rotulo_farmacia(l.get("farmacia_origem")) if l.get("farmacia_origem") else ""
    return linhas


def contar_a_receber(farmacia: str = "", sentido: str = ENVIO) -> int:
    filtro, params = "AND COALESCE(sentido, 'almox_farmacia') = ?", [_sentido(sentido)]
    if farmacia:
        filtro += " AND farmacia = ?"
        params.append(farmacia)
    return int(db.escalar(f"SELECT COUNT(*) FROM remessas WHERE status = 'enviada' {filtro}", tuple(params)) or 0)


def contar_pendencias(farmacia: str = "", sentido: str = ENVIO) -> int:
    return len(pendencias(farmacia, sentido))


# ---------------------------------------------------------------- almoxarifado: montar o envio

def abrir(farmacia: str, usuario: str, sentido: str = ENVIO) -> tuple[bool, str]:
    """Abre (ou reaproveita a aberta). Na transferência, `farmacia` é a de ORIGEM:
    o destino é a outra farmácia."""
    sentido = _sentido(sentido)
    farmacia = texto(farmacia).upper()
    if sentido == TRANSFERENCIA:
        if farmacia not in FARMACIAS:
            return False, "Escolha de qual farmácia sai a transferência (Bloco Cirúrgico ou Hemodinâmica)."
        destino = outra_farmacia(farmacia)
        aberta = db.consultar_um("SELECT id_remessa FROM remessas WHERE farmacia_origem = ? AND farmacia = ? "
                                 "AND status = 'aberta' AND sentido = ? ORDER BY criado_em DESC LIMIT 1",
                                 (farmacia, destino, TRANSFERENCIA))
        if aberta:
            return True, aberta["id_remessa"]
        novo = gerar_id("TRF")
        db.executar("INSERT INTO remessas (id_remessa, farmacia, farmacia_origem, status, criado_por, criado_em, sentido) "
                    "VALUES (?,?,?,'aberta',?,?,?)", (novo, destino, farmacia, usuario, db.agora(), TRANSFERENCIA))
        return True, novo
    if farmacia not in FARMACIAS:
        return False, ("Escolha a farmácia de destino (Bloco Cirúrgico ou Hemodinâmica)." if sentido == ENVIO
                       else "Escolha de qual farmácia sai a devolução (Bloco Cirúrgico ou Hemodinâmica).")
    aberta = db.consultar_um("SELECT id_remessa FROM remessas WHERE farmacia = ? AND status = 'aberta' "
                             "AND COALESCE(sentido, 'almox_farmacia') = ? ORDER BY criado_em DESC LIMIT 1",
                             (farmacia, sentido))
    if aberta:
        return True, aberta["id_remessa"]
    novo = gerar_id("ENV" if sentido == ENVIO else "DEV")
    db.executar("INSERT INTO remessas (id_remessa, farmacia, status, criado_por, criado_em, sentido) "
                "VALUES (?,?,'aberta',?,?,?)", (novo, farmacia, usuario, db.agora(), sentido))
    return True, novo


def _grupo(u: dict) -> str:
    """Mesmo AGHU + lote + validade = mesmo grupo (v18.11: lote sem diferença de
    maiúscula/minúscula, validade só a data e sem separar por marca — antes o mesmo
    lote aparecia 2 ou 3 vezes para escolher)."""
    return "|".join([texto(u["codigo_aghu"]).upper(), gs1.lote_normalizado(u["nLote"]), texto(u["dVal"])[:10]])


def bipar(id_remessa: str, codigo_lido: str, usuario: str, quantidade=1, grupo: str = "",
          ciencia_validade: bool = False) -> dict:
    rem = db.consultar_um("SELECT * FROM remessas WHERE id_remessa = ?", (texto(id_remessa),))
    if not rem or rem["status"] != "aberta":
        return {"ok": False, "mensagem": "Este envio não está aberto (já foi finalizado ou cancelado)."}
    sentido = _sentido(rem["sentido"])
    origem, transito = ORIGEM[sentido], TRANSITO[sentido]
    nomes = _nomes(sentido, rem["farmacia"], rem.get("farmacia_origem") or "")
    # Na devolução só conta o estoque da farmácia que está devolvendo; na
    # transferência, o da farmácia de origem.
    if sentido == DEVOLUCAO:
        f_sql, f_par = "AND u.farmacia = ?", [rem["farmacia"]]
    elif sentido == TRANSFERENCIA:
        f_sql, f_par = "AND u.farmacia = ?", [rem["farmacia_origem"]]
    else:
        f_sql, f_par = "", []
    bruto = texto(codigo_lido)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    etiqueta = busca.interpretar(bruto)
    codigo = normalizar_codigo(bruto)
    candidatas = [dict(r) for r in db.consultar(
        f"""SELECT u.* FROM unidades u
           WHERE u.status = ? AND COALESCE(u.id_caixa,'') = '' {f_sql}
             AND (UPPER(u.id_unidade) = UPPER(?) OR gtin(u.codigo_barras) = gtin(?)
                  OR (COALESCE(u.numero_serie,'') <> '' AND REPLACE(u.numero_serie,' ','') = ?))
           ORDER BY CASE WHEN COALESCE(u.dVal,'') = '' THEN 1 ELSE 0 END, u.dVal, u.criado_em""",
        (origem, *f_par, codigo, codigo, codigo))]
    if not candidatas:
        cond, extra = gs1.sql_por_lote(etiqueta)
        if cond:
            candidatas = [dict(r) for r in db.consultar(
                f"""SELECT u.* FROM unidades u WHERE u.status = ? AND COALESCE(u.id_caixa,'') = '' {f_sql} AND {cond}
                    ORDER BY CASE WHEN COALESCE(u.dVal,'') = '' THEN 1 ELSE 0 END, u.dVal, u.criado_em""",
                (origem, *f_par, *extra))]
    # v18.43.2: "código de barras é tudo o que eu bipo" (Camila, 20/11/2026).
    # Se alguma unidade tem EXATAMENTE o texto bipado como código, a busca é
    # essa — nada de abrir a lista de lotes do mesmo produto. Vale para o
    # cadastro que guardou a etiqueta inteira: cada peça tem a sua.
    candidatas = busca.preferir_exatos(candidatas, bruto)
    candidatas, aviso_lote = gs1.filtrar(candidatas, etiqueta)
    if not candidatas:
        outros = db.consultar("SELECT status, farmacia, COUNT(*) AS n FROM unidades WHERE gtin(codigo_barras) = gtin(?) "
                              "OR UPPER(id_unidade) = UPPER(?) GROUP BY status, farmacia", (codigo, codigo))
        if outros:
            from ..domain import rotulo
            resumo = ", ".join(f"{o['n']}× {rotulo(o['status'])}"
                               + (f" ({rotulo_farmacia(o['farmacia'])})" if texto(o["farmacia"]) else "") for o in outros)
            return {"ok": False, "titulo": ("Sem estoque no almoxarifado" if sentido == ENVIO
                                            else "Sem estoque nesta farmácia"),
                    "mensagem": (f"O código {codigo} não tem unidade disponível no {nomes['origem']}. "
                                 f"Situação atual: {resumo}.")}
        pend = db.escalar("SELECT COUNT(*) FROM carga_itens WHERE codigo_barras = ? AND situacao = 'pendente'", (codigo,))
        if sentido in (DEVOLUCAO, TRANSFERENCIA):
            return {"ok": False, "titulo": "MATERIAL NÃO CADASTRADO", "nao_cadastrado": True,
                    "mensagem": f"O código {codigo} não está cadastrado no sistema."}
        return {"ok": False, "titulo": "MATERIAL NÃO CADASTRADO", "nao_cadastrado": True,
                "mensagem": (f"O código {codigo} não está cadastrado no sistema. Dê entrada no material "
                             "(nota fiscal, cadastro manual ou planilha de lotes) antes de enviar."
                             + (" Há linhas da planilha de lotes pendentes de bipar com este código." if pend else ""))}
    # v18.4.1: lote em recall não vai para a farmácia (nem para a outra farmácia).
    # A devolução ao almoxarifado continua liberada — é o caminho para tirar o
    # material de circulação.
    if sentido in (ENVIO, TRANSFERENCIA):
        # v18.4.2: vencido não vai para a farmácia (nem para a outra farmácia).
        hoje = hoje_iso()
        vencidas = [c for c in candidatas if texto(c.get("dVal")) and texto(c.get("dVal"))[:10] < hoje]
        if vencidas:
            validas = [c for c in candidatas if c not in vencidas]
            if not validas:
                v = vencidas[0]
                return {"ok": False, "titulo": "MATERIAL VENCIDO",
                        "mensagem": (f"O lote {v.get('nLote') or '—'} venceu em {data_br(v.get('dVal'))}. Material vencido "
                                     "não vai para a farmácia: separe e registre a devolução ao fornecedor ou a baixa.")}
            candidatas = validas
        from . import recall
        travadas = recall.bloqueadas(candidatas)
        if travadas:
            ids_travados = {u["id_unidade"] for u, _b in travadas}
            livres = [c for c in candidatas if c["id_unidade"] not in ids_travados]
            if not livres:
                u, b = travadas[0]
                return {"ok": False, "titulo": "LOTE BLOQUEADO (RECALL)", "mensagem": recall.mensagem_bloqueio(u, b)}
            candidatas = livres
    grupos: dict[str, list[dict]] = {}
    for c in candidatas:
        grupos.setdefault(_grupo(c), []).append(c)
    if grupo:
        if grupo not in grupos:
            return {"ok": False, "mensagem": "O lote escolhido não está mais disponível. Bipe de novo."}
        escolhido = grupos[grupo]
    elif len(grupos) > 1 or aviso_lote:
        # v18.11: lote da etiqueta que não existe no estoque — nunca escolhe sozinho.
        msg = (f"O lote da etiqueta ({etiqueta['lote']}) NÃO foi encontrado no {nomes['origem']}. Confira a "
               f"embalagem. Se o material for mesmo um destes lotes, escolha:" if aviso_lote and etiqueta
               else f"O código {codigo} tem {len(grupos)} lotes no {nomes['origem']}. "
                    f"Escolha qual está {'enviando' if sentido == ENVIO else 'devolvendo'}.")
        return {"ok": False, "escolher": True, "codigo": bruto, "lote_nao_encontrado": bool(aviso_lote),
                "mensagem": msg,
                "opcoes": [{"grupo": k, "aghu": v[0]["codigo_aghu"] or "—",
                            "descricao": v[0]["descritivo_hospital"] or v[0]["xProd"],
                            "lote": v[0]["nLote"] or "—", "validade": data_br(v[0]["dVal"]) or "—",
                            "marca": v[0]["marca_fabricante"] or "—", "disponivel": len(v)}
                           for k, v in grupos.items()]}
    else:
        escolhido = next(iter(grupos.values()))
    qtd = max(1, inteiro(quantidade, 1))
    if qtd > len(escolhido):
        return {"ok": False, "mensagem": (f"Só há {len(escolhido)} unidade(s) deste lote no "
                                          f"{nomes['origem']}. Ajuste a quantidade.")}
    # nov/2026: lote com validade mais próxima no almoxarifado → aviso com ciência
    # (não trava). Ver `validade_aviso`. Na devolução ao almoxarifado não se aplica.
    from . import validade_aviso
    onde_aviso = "no estoque do almoxarifado"
    anterior = (validade_aviso.lote_com_validade_anterior(escolhido[0], estoque=EM_ESTOQUE_RECEBIMENTO)
                if sentido == ENVIO else None)
    if anterior and not ciencia_validade:
        resposta = validade_aviso.resposta_aviso(escolhido[0], anterior, onde_aviso)
        resposta.update({"codigo": bruto, "grupo": _grupo(escolhido[0]), "quantidade": qtd})
        return resposta
    agora = db.agora()
    try:
        _gravar_bipagem(rem, escolhido[:qtd], sentido, origem, transito, usuario, agora, anterior, onde_aviso)
    except ErroDeNegocio as recusa:
        return {"ok": False, "mensagem": str(recusa)}
    u0 = escolhido[0]
    return {"ok": True, "quantidade": qtd, "lista": lista_envio(rem["id_remessa"]),
            "item": {"descricao": u0["descritivo_hospital"] or u0["xProd"], "aghu": u0["codigo_aghu"] or "—",
                     "lote": u0["nLote"] or "—", "validade": data_br(u0["dVal"]) or "—"},
            "mensagem": (f"{qtd} unidade(s) de {(u0['descritivo_hospital'] or u0['xProd'])[:60]} "
                         f"(lote {u0['nLote'] or '—'}) na {nomes['documento'].lower()}."),
            "total": int(db.escalar("SELECT COUNT(*) FROM remessa_itens WHERE id_remessa = ? AND situacao <> 'removido'",
                                    (rem["id_remessa"],)) or 0)}


def _gravar_bipagem(rem, unidades, sentido, origem, transito, usuario, agora, anterior, onde_aviso) -> None:
    """v18.4.1: tudo ou nada, e só move a unidade se ela AINDA estiver na origem.

    Duas bipagens da mesma unidade ao mesmo tempo liam "disponível" antes de
    qualquer uma gravar; as duas gravavam e a unidade aparecia duas vezes. Agora
    o UPDATE confere o status dentro da transação: se outra pessoa levou a
    unidade antes, nada é gravado e a tela pede para bipar de novo."""
    from . import validade_aviso
    with db.transacao() as conn:
        st = conn.execute("SELECT status FROM remessas WHERE id_remessa = ?", (rem["id_remessa"],)).fetchone()
        if not st or st[0] != "aberta":
            raise ErroDeNegocio("Esta remessa já foi finalizada ou cancelada. Atualize a tela.")
        if anterior:
            for u in unidades:
                validade_aviso.registrar_ciencia(conn, u, anterior, usuario, onde_aviso)
        if sentido in (ENVIO, TRANSFERENCIA):
            from . import recall
            travadas = recall.bloqueadas(unidades, conn)
            if travadas:
                u, b = travadas[0]
                raise ErroDeNegocio(recall.mensagem_bloqueio(u, b))
        for u in unidades:
            cur = conn.execute("""UPDATE unidades SET status = ?, farmacia = ?, atualizado_em = ?, atualizado_por = ?
                                  WHERE id_unidade = ? AND status = ? AND COALESCE(id_caixa, '') = ''""",
                               (transito, rem["farmacia"], agora, usuario, u["id_unidade"], origem))
            if cur.rowcount != 1:
                raise ErroDeNegocio("Este material acabou de ser movimentado por outra pessoa. Bipe de novo.")
            conn.execute("""INSERT INTO remessa_itens (id_remessa, id_unidade, bipado_por, bipado_em)
                            VALUES (?,?,?,?)""", (rem["id_remessa"], u["id_unidade"], usuario, agora))
            if sentido == ENVIO:
                db.registrar_evento(conn, tipo="enviar_farmacia", id_unidade=u["id_unidade"],
                                    status_anterior=origem, status_novo=transito, usuario=usuario,
                                    observacao=f"Envio {rem['id_remessa']} para a {rotulo_farmacia(rem['farmacia'])}")
            elif sentido == TRANSFERENCIA:
                db.registrar_evento(conn, tipo="transferir_farmacia", id_unidade=u["id_unidade"],
                                    status_anterior=origem, status_novo=transito, usuario=usuario,
                                    observacao=(f"Transferência {rem['id_remessa']} da "
                                                f"{rotulo_farmacia(rem['farmacia_origem'])} para a "
                                                f"{rotulo_farmacia(rem['farmacia'])}"))
            else:
                db.registrar_evento(conn, tipo="devolver_almoxarifado", id_unidade=u["id_unidade"],
                                    status_anterior=origem, status_novo=transito, usuario=usuario,
                                    observacao=(f"Devolução {rem['id_remessa']} da {rotulo_farmacia(rem['farmacia'])} "
                                                "para o almoxarifado"))


def lista_envio(id_remessa: str) -> list[dict]:
    """O que já está no envio (o último bipado em cima), para a tela redesenhar."""
    return [{"id_item": i["id_item"], "aghu": i["codigo_aghu"] or "—", "descricao": i["descricao"],
             "lote": i["nLote"] or "—", "validade": i["validade"], "quando": data_hora_br(i["bipado_em"]),
             "por": i["bipado_por"] or ""} for i in itens(id_remessa, "pendente")]


def disponiveis(termo: str = "", limite: int = 40, farmacia: str = "") -> list[dict]:
    """Consulta do estoque do almoxarifado (ou, com `farmacia`, do estoque dessa
    farmácia — para a devolução), por AGHU, descrição, lote ou código."""
    from .. import busca
    if texto(farmacia):
        cond, params = ["status = ?", "COALESCE(id_caixa,'') = ''", "farmacia = ?"], [EM_ESTOQUE_FARMACIA, texto(farmacia)]
    else:
        cond, params = ["status = ?", "COALESCE(id_caixa,'') = ''"], [EM_ESTOQUE_RECEBIMENTO]
    etiqueta = busca.interpretar(termo)
    if etiqueta:
        # nov/2026: etiqueta GS1 bipada inteira — procura pelo GTIN/lote dela.
        c, extra, _ = busca.condicao(termo, [], alias="")
        cond.append(c)
        params += extra
    else:
        for p in texto(termo).upper().split():
            cond.append("(codigo_aghu LIKE ? OR UPPER(COALESCE(NULLIF(descritivo_hospital,''), xProd)) LIKE ? "
                        "OR UPPER(nLote) LIKE ? OR codigo_barras LIKE ? OR gtin(codigo_barras) = gtin(?))")
            params += [f"%{p}%"] * 4 + [p]
    linhas = db.consultar(
        f"""SELECT codigo_aghu, COALESCE(NULLIF(descritivo_hospital,''), xProd) AS descricao, nLote, dVal,
                   codigo_barras, COUNT(*) AS quantidade
            FROM unidades WHERE {' AND '.join(cond)}
            GROUP BY codigo_aghu, descricao, nLote, dVal, codigo_barras
            ORDER BY descricao, dVal LIMIT {int(limite)}""", tuple(params))
    for l in linhas:
        l["validade"] = data_br(l["dVal"]) or "—"
    return linhas


def remover_item(id_item, usuario: str) -> tuple[bool, str, str]:
    linha = db.consultar_um(
        """SELECT i.*, r.status AS status_remessa, r.sentido, r.farmacia, r.farmacia_origem FROM remessa_itens i
           JOIN remessas r ON r.id_remessa = i.id_remessa WHERE i.id_item = ?""", (inteiro(id_item, 0),))
    if not linha or linha["status_remessa"] != "aberta" or linha["situacao"] != "pendente":
        return False, "Só dá para tirar item de envio ainda aberto.", linha["id_remessa"] if linha else ""
    sentido = _sentido(linha["sentido"])
    nomes = _nomes(sentido, linha["farmacia"], linha["farmacia_origem"] or "")
    with db.transacao() as conn:
        _voltar_a_origem(conn, linha["id_unidade"], sentido, usuario, linha["farmacia_origem"] or "")
        conn.execute("UPDATE remessa_itens SET situacao = 'removido', resolvido_em = ?, resolvido_por = ? WHERE id_item = ?",
                     (db.agora(), usuario, linha["id_item"]))
        db.registrar_evento(conn, tipo="remover_do_envio", id_unidade=linha["id_unidade"],
                            status_anterior=TRANSITO[sentido], status_novo=ORIGEM[sentido], usuario=usuario,
                            observacao=(f"Tirado {'da devolução' if sentido == DEVOLUCAO else 'do envio'} "
                                        f"{linha['id_remessa']} antes de finalizar; voltou ao {nomes['origem']}"))
    return True, f"Item tirado (voltou ao {nomes['origem']}).", linha["id_remessa"]


def sentido_do_item(id_item) -> str:
    return _sentido(db.escalar("SELECT r.sentido FROM remessa_itens i JOIN remessas r ON r.id_remessa = i.id_remessa "
                               "WHERE i.id_item = ?", (inteiro(id_item, 0),)))


def _voltar_a_origem(conn, id_unidade: str, sentido: str, usuario: str, farmacia_origem: str = "") -> None:
    """Unidade em trânsito volta para onde estava (envio: almoxarifado; devolução:
    a farmácia; transferência: a farmácia de origem)."""
    if sentido == TRANSFERENCIA:
        conn.execute("""UPDATE unidades SET status = ?, farmacia = ?, atualizado_em = ?, atualizado_por = ?
                        WHERE id_unidade = ? AND status = ?""",
                     (ORIGEM[sentido], farmacia_origem, db.agora(), usuario, id_unidade, TRANSITO[sentido]))
        return
    limpa = "farmacia = NULL," if sentido == ENVIO else ""
    conn.execute(f"""UPDATE unidades SET status = ?, {limpa} atualizado_em = ?, atualizado_por = ?
                     WHERE id_unidade = ? AND status = ?""",
                 (ORIGEM[sentido], db.agora(), usuario, id_unidade, TRANSITO[sentido]))


def finalizar_envio(id_remessa: str, usuario: str, observacao: str = "") -> tuple[bool, str]:
    rem = buscar(id_remessa)
    if not rem or rem["status"] != "aberta":
        return False, "Este envio não está aberto."
    if not rem["pendentes"]:
        return False, "Bipe pelo menos um material antes de finalizar."
    devolucao = rem["sentido"] == DEVOLUCAO
    transferencia = rem["sentido"] == TRANSFERENCIA
    with db.transacao() as conn:
        conn.execute("""UPDATE remessas SET status = 'enviada', enviada_em = ?, enviada_por = ?, observacao = ?
                        WHERE id_remessa = ?""", (db.agora(), usuario, texto(observacao), rem["id_remessa"]))
        if transferencia:
            db.registrar_evento(conn, tipo="transferencia_finalizada", usuario=usuario,
                                observacao=(f"Transferência {rem['id_remessa']} da {rem['farmacia_origem_rotulo']} "
                                            f"para a {rem['farmacia_rotulo']}: {len(rem['pendentes'])} item(ns); "
                                            "aguardando a ciência da farmácia de destino"))
        elif devolucao:
            db.registrar_evento(conn, tipo="devolver_almoxarifado", usuario=usuario,
                                observacao=(f"Devolução {rem['id_remessa']} da {rem['farmacia_rotulo']} finalizada: "
                                            f"{len(rem['pendentes'])} item(ns); aguardando a ciência do almoxarifado"))
        else:
            db.registrar_evento(conn, tipo="envio_farmacia_finalizado", usuario=usuario,
                                observacao=(f"Envio {rem['id_remessa']} para a {rem['farmacia_rotulo']}: "
                                            f"{len(rem['pendentes'])} item(ns); aguardando a conferência da farmácia"))
    if transferencia:
        return True, (f"Transferência finalizada: {len(rem['pendentes'])} item(ns) para a {rem['farmacia_rotulo']}. "
                      "A farmácia de destino confere e dá ciência.")
    if devolucao:
        return True, (f"Devolução finalizada: {len(rem['pendentes'])} item(ns) para o almoxarifado. "
                      "O almoxarifado confere e dá ciência.")
    return True, (f"Envio finalizado: {len(rem['pendentes'])} item(ns) para a {rem['farmacia_rotulo']}. "
                  "A farmácia confere e dá ciência.")


def cancelar(id_remessa: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    """nov/2026 — quem enviou cancela, enquanto o outro lado não deu ciência.

    Tudo o que estava no envio volta para a origem (envio: estoque do
    almoxarifado; devolução: estoque da farmácia). Nada é apagado: o envio fica
    "cancelado", com quem cancelou e o motivo, e cada item ganha o evento
    `envio_cancelado` no histórico.
    """
    rem = buscar(id_remessa)
    if not rem:
        return False, "Envio não encontrado."
    if rem["status"] not in ("aberta", "enviada"):
        return False, ("Não dá mais para cancelar: "
                       + ("já foi dada a ciência do recebimento." if rem["status"] == "conferida"
                          else "este envio já foi cancelado."))
    motivo = texto(motivo)
    if len(motivo) < 3:
        return False, "Informe o motivo do cancelamento."
    sentido = rem["sentido"]
    nomes = rem["nomes"]
    agora = db.agora()
    with db.transacao() as conn:
        # Confere dentro da transação: a ciência pode ter sido dada agora há pouco.
        atual = conn.execute("SELECT status FROM remessas WHERE id_remessa = ?", (rem["id_remessa"],)).fetchone()
        if atual["status"] not in ("aberta", "enviada"):
            return False, "Não dá mais para cancelar: o outro lado acabou de dar ciência."
        for i in rem["pendentes"]:
            _voltar_a_origem(conn, i["id_unidade"], sentido, usuario, rem.get("farmacia_origem") or "")
            conn.execute("UPDATE remessa_itens SET situacao = 'cancelado', resolvido_em = ?, resolvido_por = ? "
                         "WHERE id_item = ?", (agora, usuario, i["id_item"]))
            db.registrar_evento(conn, tipo="envio_cancelado", id_unidade=i["id_unidade"],
                                status_anterior=TRANSITO[sentido], status_novo=ORIGEM[sentido], usuario=usuario,
                                motivo=motivo,
                                observacao=(f"{nomes['documento']} {rem['id_remessa']} cancelado(a) antes da ciência; "
                                            f"voltou ao {nomes['origem']}"))
        conn.execute("""UPDATE remessas SET status = 'cancelada', cancelada_em = ?, cancelada_por = ?,
                        motivo_cancelamento = ? WHERE id_remessa = ?""", (agora, usuario, motivo, rem["id_remessa"]))
    log.info(f"remessa cancelada · {rem['id_remessa']} · {len(rem['pendentes'])} item(ns)", usuario)
    return True, (f"{nomes['documento']} cancelado(a): {len(rem['pendentes'])} item(ns) voltaram ao "
                  f"{nomes['origem']}.")


# ---------------------------------------------------------------- farmácia: conferir e dar ciência

def identificar(id_remessa: str, codigo: str) -> dict:
    bruto = texto(codigo)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    lido = {bruto.upper(), texto(normalizar_codigo(bruto)).upper()}
    etiqueta = busca.interpretar(bruto)
    cand = []
    for i in itens(id_remessa, "pendente"):
        cods = {texto(i["codigo_barras"]).upper(), texto(normalizar_codigo(i["codigo_barras"] or "")).upper(),
                texto(i["numero_serie"]).upper(), texto(i["id_unidade"]).upper()} - {""}
        if cods & lido:
            cand.append(i)
    if etiqueta and etiqueta.get("lote") and cand:
        do_lote = [i for i in cand if gs1._confere(i["nLote"], etiqueta["lote"], etiqueta.get("lote_ate_o_fim"))]
        cand = do_lote or cand
    cand.sort(key=lambda i: i["id_item"])
    if not cand:
        return {"ok": False, "mensagem": f"O código {bruto} não está neste envio."}
    return {"ok": True, "itens": [i["id_item"] for i in cand]}


def marcar_conferido(id_remessa: str, ids_item: list, quem: dict,
                     marcar: bool = True) -> tuple[bool, dict]:
    """v18.35: guarda a conferência bipe a bipe, antes da ciência.

    Antes, o que já tinha sido bipado vivia só na tela: sair do recebimento (ou
    o navegador fechar) obrigava a farmácia a conferir tudo de novo. Agora cada
    bipe é gravado e a tela volta do jeito que estava — inclusive para outra
    pessoa continuar a conferência.
    """
    rem = buscar(id_remessa)
    if not rem or rem["status"] != "enviada":
        return False, {"mensagem": "Este envio não está aguardando conferência."}
    pendentes = {str(i["id_item"]) for i in rem["pendentes"]}
    alvos = [str(i) for i in ids_item if str(i) in pendentes]
    if not alvos:
        return False, {"mensagem": "Item não encontrado neste envio."}
    agora = db.agora()
    with db.transacao() as conn:
        for id_item in alvos:
            if marcar:
                conn.execute("""UPDATE remessa_itens SET conferido_em = ?, conferido_por = ?
                                WHERE id_item = ? AND situacao = 'pendente'""",
                             (agora, quem["username"], id_item))
            else:
                conn.execute("""UPDATE remessa_itens SET conferido_em = NULL, conferido_por = NULL
                                WHERE id_item = ?""", (id_item,))
    return True, {"conferidos": conferidos(id_remessa)}


def conferidos(id_remessa: str) -> list[str]:
    """Itens já bipados nesta conferência (ainda sem ciência)."""
    return [str(l["id_item"]) for l in db.consultar(
        """SELECT id_item FROM remessa_itens
           WHERE id_remessa = ? AND situacao = 'pendente' AND COALESCE(conferido_em,'') <> ''
           ORDER BY id_item""", (texto(id_remessa),))]


def limpar_conferencia(id_remessa: str) -> None:
    db.executar("""UPDATE remessa_itens SET conferido_em = NULL, conferido_por = NULL
                   WHERE id_remessa = ?""", (texto(id_remessa),))


def conferir(id_remessa: str, recebidos: set, quem: dict, modo: str = "lista", observacao: str = "") -> tuple[bool, str]:
    rem = buscar(id_remessa)
    if not rem or rem["status"] != "enviada":
        return False, "Este envio não está aguardando conferência."
    sentido = rem["sentido"]
    transito, destino = TRANSITO[sentido], DESTINO[sentido]
    devolucao = sentido == DEVOLUCAO
    doc = rem["nomes"]["documento"]
    nome = quem.get("nome") or quem["username"]
    agora = db.agora()
    ok_n = nao_n = 0
    with db.transacao() as conn:
        for i in rem["pendentes"]:
            if str(i["id_item"]) in recebidos:
                limpa = "farmacia = NULL," if devolucao else ""
                conn.execute(f"""UPDATE unidades SET status = ?, {limpa} atualizado_em = ?, atualizado_por = ?
                                 WHERE id_unidade = ? AND status = ?""",
                             (destino, agora, quem["username"], i["id_unidade"], transito))
                conn.execute("UPDATE remessa_itens SET situacao = 'recebido', resolvido_em = ?, resolvido_por = ? WHERE id_item = ?",
                             (agora, quem["username"], i["id_item"]))
                db.registrar_evento(conn, tipo=("receber_almoxarifado" if devolucao else
                                                "receber_transferencia" if sentido == TRANSFERENCIA else "receber_farmacia"),
                                    id_unidade=i["id_unidade"],
                                    status_anterior=transito, status_novo=destino,
                                    usuario=quem["username"], recebido_por=nome,
                                    observacao=(f"{doc} {rem['id_remessa']}: ciência de {nome}"
                                                + (" (conferido bipando)" if modo == "bipando" else " (conferido pela lista)")))
                ok_n += 1
            else:
                conn.execute("UPDATE remessa_itens SET situacao = 'nao_recebido', resolvido_em = ?, resolvido_por = ? WHERE id_item = ?",
                             (agora, quem["username"], i["id_item"]))
                db.registrar_evento(conn, tipo="devolucao_almox_nao_recebida" if devolucao else "envio_nao_recebido",
                                    id_unidade=i["id_unidade"],
                                    status_anterior=transito, status_novo=transito,
                                    usuario=quem["username"], recebido_por=nome,
                                    observacao=(f"{doc} {rem['id_remessa']}: não recebido pelo "
                                                f"{'almoxarifado' if devolucao else 'farmácia'} — pendência para tratativa"))
                nao_n += 1
        conn.execute("""UPDATE remessas SET status = 'conferida', conferida_em = ?, conferida_por = ?, conferida_nome = ?,
                        modo_conferencia = ?, observacao = TRIM(COALESCE(observacao,'') || ' ' || ?) WHERE id_remessa = ?""",
                     (agora, quem["username"], nome, modo, texto(observacao), rem["id_remessa"]))
    destino_txt = "do almoxarifado" if devolucao else f"da {rem['farmacia_rotulo']}"
    msg = f"Ciência registrada: {ok_n} item(ns) entraram no estoque {destino_txt}."
    if nao_n:
        msg += f" {nao_n} item(ns) não recebidos ficaram como pendência, para tratativa."
    limpar_conferencia(id_remessa)
    return True, msg


def tratar(id_item, acao: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    linha = db.consultar_um(
        """SELECT i.*, r.farmacia, r.farmacia_origem, r.sentido FROM remessa_itens i JOIN remessas r ON r.id_remessa = i.id_remessa
           WHERE i.id_item = ? AND i.situacao = 'nao_recebido' AND COALESCE(i.tratativa,'') = ''""",
        (inteiro(id_item, 0),))
    if not linha:
        return False, "Esta pendência já foi tratada."
    sentido = _sentido(linha["sentido"])
    tratativas = tratativas_de(sentido)
    if acao not in tratativas:
        return False, "Escolha a tratativa."
    motivo = texto(motivo)
    if acao == "divergencia" and len(motivo) < 5:
        return False, "Descreva o que aconteceu (divergência / extravio)."
    farmacia_nova = None  # None = não mexe; "" = limpa; texto = grava
    if sentido == TRANSFERENCIA:
        novo = {"recebido_depois": EM_ESTOQUE_FARMACIA, "voltou_origem": EM_ESTOQUE_FARMACIA,
                "divergencia": DIVERGENCIA}[acao]
        limpa = False
        if acao == "voltou_origem":
            farmacia_nova = linha["farmacia_origem"]
    elif sentido == ENVIO:
        novo = {"recebido_depois": EM_ESTOQUE_FARMACIA, "voltou_almoxarifado": EM_ESTOQUE_RECEBIMENTO,
                "divergencia": DIVERGENCIA}[acao]
        limpa = acao == "voltou_almoxarifado"
    else:
        novo = {"recebido_depois": EM_ESTOQUE_RECEBIMENTO, "voltou_farmacia": EM_ESTOQUE_FARMACIA,
                "divergencia": DIVERGENCIA}[acao]
        limpa = acao == "recebido_depois"
    with db.transacao() as conn:
        if farmacia_nova:
            conn.execute("""UPDATE unidades SET status = ?, farmacia = ?, atualizado_em = ?, atualizado_por = ?
                            WHERE id_unidade = ? AND status = ?""",
                         (novo, farmacia_nova, db.agora(), usuario, linha["id_unidade"], TRANSITO[sentido]))
        else:
            conn.execute(f"""UPDATE unidades SET status = ?, {'farmacia = NULL,' if limpa else ''}
                             atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ? AND status = ?""",
                         (novo, db.agora(), usuario, linha["id_unidade"], TRANSITO[sentido]))
        conn.execute("""UPDATE remessa_itens SET tratativa = ?, tratativa_motivo = ?, resolvido_em = ?, resolvido_por = ?,
                        situacao = CASE WHEN ? = 'recebido_depois' THEN 'recebido' ELSE situacao END
                        WHERE id_item = ?""", (acao, motivo, db.agora(), usuario, acao, linha["id_item"]))
        db.registrar_evento(conn, tipo="tratativa_envio", id_unidade=linha["id_unidade"],
                            status_anterior=TRANSITO[sentido], status_novo=novo, usuario=usuario, motivo=motivo,
                            observacao=(f"{_nomes(sentido, linha['farmacia'])['documento']} {linha['id_remessa']}: "
                                        f"{tratativas[acao]}"))
    log.info(f"tratativa de envio · item={linha['id_item']} · {acao}", usuario)
    return True, f"Pendência tratada: {tratativas[acao].lower()}."
