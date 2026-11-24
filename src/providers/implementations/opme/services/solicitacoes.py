"""Solicitação de OPME pela sala de procedimento (o papel "Requisição de material").

A sala preenche, no sistema, o formulário da especialidade (os mesmos papéis de
hoje, transcritos em `app/formularios_opme.py`) e pode acrescentar um item fora
do formulário pelo código AGHU. A farmácia vê a solicitação na tela de
dispensar e, a cada bip, a linha do mesmo código AGHU recebe o "check".

Regra (definida pela Camila):
- O bip de um material que não foi solicitado (ou além da quantidade pedida) é
  aceito e SINALIZADO como "não solicitado"; o item pedido continua "faltando".
  Um não é vinculado ao outro.
- Linha sem código AGHU ("CATETER DIAGNÓSTICO — TIPO: JR4 5F"): a farmácia marca
  à mão quando atende.
- "Finalizar dispensa" com item faltando exige um motivo (ex.: sem estoque), e a
  sala vê o que não veio.

O "dispensado" não é gravado: é calculado dos itens da dispensação deste
paciente. Tirar um item ou desfazer um bip já atualiza a lista sozinho.
"""

from __future__ import annotations

from .. import db
from ..formularios_opme import FORMULARIOS, codigos, linhas, normalizar_codigo_aghu, sugerido
from ..utils import data_br, data_hora_br, gerar_id, inteiro, texto

AVULSO = "avulso"


# ---------------------------------------------------------------- leitura

def buscar(id_atendimento: str) -> dict | None:
    sol = db.consultar_um("SELECT * FROM solicitacoes WHERE id_atendimento = ?", (texto(id_atendimento),))
    if not sol:
        return None
    sol = dict(sol)
    sol["itens"] = db.consultar(
        "SELECT * FROM solicitacao_itens WHERE id_solicitacao = ? ORDER BY id_item",
        (sol["id_solicitacao"],))
    return sol


def _dispensados(id_atendimento: str) -> list[dict]:
    """Unidades que a farmácia dispensou para o paciente (fora as tiradas)."""
    return db.consultar(
        """SELECT i.id_item, i.id_unidade, i.id_caixa, i.bipado_em, i.bipado_por,
                  u.codigo_aghu, u.descritivo_hospital, u.xProd, u.nLote, u.dVal
           FROM dispensacao_itens i
           JOIN dispensacoes d ON d.id_dispensacao = i.id_dispensacao
           LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
           WHERE d.id_atendimento = ? AND i.situacao NOT IN ('removido', 'cancelado')
           ORDER BY i.id_item""", (texto(id_atendimento),))


def situacao(id_atendimento: str) -> dict:
    """Solicitação × dispensado: o "check" de cada linha e o que veio sem pedido."""
    sol = buscar(id_atendimento)
    disp = _dispensados(id_atendimento)
    # Fila de unidades por código AGHU, na ordem em que foram bipadas.
    fila: dict[str, list[dict]] = {}
    for u in disp:
        fila.setdefault(normalizar_codigo_aghu(u["codigo_aghu"]), []).append(u)

    # Vínculos "atendido com outro código": a unidade sai da fila do código dela
    # e conta para a linha escolhida pela farmácia.
    por_id = {u["id_unidade"]: u for u in disp}
    vinculos: dict[int, list[dict]] = {}
    if sol and sol["itens"]:
        for v in db.consultar(
                f"""SELECT * FROM solicitacao_vinculos WHERE id_item IN
                    ({','.join('?' for _ in sol['itens'])}) ORDER BY id_vinculo""",
                tuple(i["id_item"] for i in sol["itens"])):
            u = por_id.get(v["id_unidade"])
            if not u:
                continue  # tirado da dispensação depois: o vínculo deixa de valer
            c = normalizar_codigo_aghu(u["codigo_aghu"])
            if u in fila.get(c, []):
                fila[c].remove(u)
            vinculos.setdefault(v["id_item"], []).append(dict(v) | {
                "aghu": u["codigo_aghu"] or "—", "descricao_bipada": u["descritivo_hospital"] or u["xProd"] or "",
                "lote": u["nLote"] or "—"})

    saida_linhas = []
    for item in (sol["itens"] if sol else []):
        cods = codigos(item["codigos"])
        qtd = int(item["quantidade"] or 0)
        vinc = vinculos.get(item["id_item"], [])
        if cods:
            usados: list[dict] = [None] * min(len(vinc), qtd)
            for c in cods:
                while len(usados) < qtd and fila.get(c):
                    usados.append(fila[c].pop(0))
            dispensado = len(usados)
            manual = False
        else:
            # v18.43: linha sem código AGHU também pode ser atendida por material
            # bipado (a farmácia associa). O "marcar atendido" continua valendo.
            manual = bool(texto(item["atendido_manual_em"]))
            dispensado = qtd if manual else min(len(vinc), qtd)
        falta = texto(item["falta_em"]) if "falta_em" in item.keys() else ""
        if dispensado >= qtd:
            status = "atendido"
        elif falta:
            status = "falta"          # v18.43: a farmácia marcou que não tem em estoque
        elif dispensado:
            status = "parcial"
        else:
            status = "faltando"
        saida_linhas.append({
            "id_item": item["id_item"], "formulario": item["formulario"],
            "formulario_titulo": (FORMULARIOS.get(item["formulario"], {}).get("titulo")
                                  or "Fora do formulário"),
            "codigos": item["codigos"], "descricao": item["descricao"],
            "especificacao": texto(item["especificacao"]), "quantidade": qtd,
            "dispensado": dispensado, "status": status, "sem_codigo": not cods,
            "manual": manual, "manual_por": texto(item["atendido_manual_por"]),
            "vinculos": vinc,
            "rodada": int(item["rodada"] or 1) if "rodada" in item.keys() else 1,
            "falta_em": data_hora_br(falta), "falta_motivo": texto(item["falta_motivo"]) if falta else "",
            "falta_por": texto(item["falta_por"]) if falta else "",
        })

    pedidos = {c for item in (sol["itens"] if sol else []) for c in codigos(item["codigos"])}
    sobras: dict[str, dict] = {}
    for c, resto in fila.items():
        for u in resto:
            chave = f"{c}|{u['nLote'] or ''}"
            g = sobras.setdefault(chave, {
                "aghu": u["codigo_aghu"] or "—",
                "descricao": u["descritivo_hospital"] or u["xProd"] or "",
                "lote": u["nLote"] or "—", "validade": data_br(u["dVal"]) or "—",
                "quantidade": 0, "ids": [],
                "motivo": "além da quantidade pedida" if c and c in pedidos else "não solicitado",
            })
            g["quantidade"] += 1
            g["ids"].append(u["id_unidade"])
    faltando = [l for l in saida_linhas if l["status"] != "atendido"]
    sem_estoque = [l for l in saida_linhas if l["status"] == "falta"]
    # v18.43: cada rodada de pedido num bloco próprio — a sala pode pedir de novo
    # depois de a farmácia finalizar, e os dois pedidos não podem se misturar.
    blocos: list[dict] = []
    for l in saida_linhas:
        bloco = next((b for b in blocos if b["rodada"] == l["rodada"]), None)
        if not bloco:
            bloco = {"rodada": l["rodada"], "linhas": [], "qtd_linhas": 0,
                     "qtd_atendidas": 0, "qtd_faltando": 0, "qtd_sem_estoque": 0}
            blocos.append(bloco)
        bloco["linhas"].append(l)
        bloco["qtd_linhas"] += 1
        bloco["qtd_atendidas"] += 1 if l["status"] == "atendido" else 0
        bloco["qtd_faltando"] += 1 if l["status"] not in ("atendido", "falta") else 0
        bloco["qtd_sem_estoque"] += 1 if l["status"] == "falta" else 0
    blocos.sort(key=lambda b: b["rodada"])
    for n, b in enumerate(blocos, 1):
        b["titulo"] = "Pedido" if len(blocos) == 1 else f"{n}º pedido"
    return {
        "pedidos": blocos,
        "existe": bool(sol and sol["itens"]),
        "id_solicitacao": sol["id_solicitacao"] if sol else "",
        "criado_por": (sol or {}).get("criado_por") or "",
        "atualizado_em": data_hora_br((sol or {}).get("atualizado_em") or (sol or {}).get("criado_em")),
        "observacao": texto((sol or {}).get("observacao")),
        "linhas": saida_linhas,
        "nao_solicitados": list(sobras.values()),
        "qtd_linhas": len(saida_linhas),
        "qtd_atendidas": len(saida_linhas) - len(faltando),
        "qtd_faltando": len(faltando),
        "qtd_sem_estoque": len(sem_estoque),
        "qtd_a_atender": len([l for l in faltando if l["status"] != "falta"]),
        "faltando": [{"descricao": l["descricao"] + (f" ({l['especificacao']})" if l["especificacao"] else ""),
                      "falta": l["quantidade"] - l["dispensado"], "codigos": l["codigos"]}
                     for l in faltando],
        "finalizada_em": data_hora_br((sol or {}).get("finalizada_em")),
        "finalizada_por": texto((sol or {}).get("finalizada_por")),
        "motivo_faltas": texto((sol or {}).get("motivo_faltas")),
        "cancelada_em": data_hora_br((sol or {}).get("cancelada_em")),
        "cancelada_por": texto((sol or {}).get("cancelada_por")),
        "motivo_cancelamento": texto((sol or {}).get("motivo_cancelamento")),
        # v18.7.3: a sala pode cancelar enquanto a solicitação está em aberto
        "pode_cancelar": bool(sol and sol["itens"]) and not texto((sol or {}).get("cancelada_em"))
                         and not texto((sol or {}).get("finalizada_em")),
    }


def unidade_nao_solicitada(id_atendimento: str, id_unidade: str) -> str:
    """Depois do bip: "" se a unidade atende a solicitação; senão, o aviso."""
    s = situacao(id_atendimento)
    # v18.12.2: solicitação cancelada não tem mais o que atender — não alerta "não solicitado".
    if not s["existe"] or s["cancelada_em"]:
        return ""
    for g in s["nao_solicitados"]:
        if id_unidade in g["ids"]:
            return ("ATENÇÃO: material NÃO SOLICITADO pela sala" if g["motivo"] == "não solicitado"
                    else "ATENÇÃO: além da quantidade solicitada pela sala")
    return ""


def resumo_lista(ids_atendimento: list[str]) -> dict[str, dict]:
    """Para as listas: {id_atendimento: {linhas, atendidas…}} de quem tem solicitação."""
    if not ids_atendimento:
        return {}
    marcas = ",".join("?" for _ in ids_atendimento)
    com = db.consultar(
        f"""SELECT s.id_atendimento,
                   COALESCE(s.cancelada_em, '') AS cancelada_em,
                   COALESCE(s.finalizada_em, '') AS finalizada_em
            FROM solicitacoes s WHERE s.id_atendimento IN ({marcas})
             AND EXISTS (SELECT 1 FROM solicitacao_itens i WHERE i.id_solicitacao = s.id_solicitacao)""",
        tuple(ids_atendimento))
    saida = {}
    for linha in com:
        a = linha["id_atendimento"]
        s = situacao(a)
        # v18.31: cancelada ou finalizada não é pedido pendente — a farmácia não
        # tem mais o que atender. O histórico (linhas, atendidas, faltando)
        # continua aqui para as telas mostrarem o que foi pedido.
        cancelada = bool(texto(linha["cancelada_em"]))
        finalizada = bool(texto(linha["finalizada_em"]))
        saida[a] = {"linhas": s["qtd_linhas"], "atendidas": s["qtd_atendidas"],
                    "faltando": s["qtd_faltando"],
                    "nao_solicitados": sum(g["quantidade"] for g in s["nao_solicitados"]),
                    "cancelada": cancelada, "finalizada": finalizada,
                    "pendente": bool(s["qtd_faltando"]) and not cancelada and not finalizada}
    return saida


def em_aberto(unidade: str = "") -> list[dict]:
    """Solicitações que a farmácia ainda precisa atender: atendimento aberto,
    solicitação não cancelada, dispensa não finalizada e com item faltando."""
    filtro, params = "", []
    if texto(unidade):
        filtro, params = "AND a.unidade = ?", [texto(unidade)]
    linhas_ = db.consultar(
        f"""SELECT s.id_atendimento, s.criado_em, s.criado_por, s.atualizado_em, a.prontuario, a.paciente,
                   a.unidade, a.sala, a.especialidade, a.data_procedimento, a.hora_inicio
            FROM solicitacoes s JOIN atendimentos a ON a.id_atendimento = s.id_atendimento
            WHERE a.status = 'aberto' AND COALESCE(s.cancelada_em,'') = '' AND COALESCE(s.finalizada_em,'') = ''
              AND COALESCE(a.uso_finalizado_em,'') = '' {filtro}
              AND EXISTS (SELECT 1 FROM solicitacao_itens i WHERE i.id_solicitacao = s.id_solicitacao)
            ORDER BY a.data_procedimento, a.hora_inicio, s.criado_em""", tuple(params))
    saida = []
    for l in linhas_:
        st = situacao(l["id_atendimento"])
        if st["qtd_faltando"]:
            saida.append(dict(l) | {"linhas": st["qtd_linhas"], "atendidas": st["qtd_atendidas"],
                                    "faltando": st["qtd_faltando"]})
    return saida


def contar_em_aberto(unidade: str = "") -> int:
    """Com `unidade`, só os pedidos das salas daquela unidade: cada farmácia
    (Bloco, Hemodinâmica) vê o alerta só do que ela atende."""
    return len(em_aberto(unidade))


def formulario_da_tela(id_atendimento: str, chave: str) -> list[dict]:
    """Linhas do formulário com o que a sala já pediu nele (para editar)."""
    sol = buscar(id_atendimento)
    ja = {i["linha"]: i for i in (sol["itens"] if sol else []) if i["formulario"] == chave}
    saida = []
    for l in linhas(chave):
        atual = ja.get(l["linha"])
        saida.append(l | {"quantidade": int(atual["quantidade"]) if atual else 0,
                          "especificacao": texto(atual["especificacao"]) if atual else ""})
    return saida


def formulario_sugerido(atendimento: dict | None) -> str:
    if not atendimento:
        return ""
    return sugerido(atendimento.get("especialidade", ""), atendimento.get("unidade", ""))


def buscar_materiais(termo: str, formulario_atual: str = "", limite: int = 40) -> list[dict]:
    """Busca para a solicitação: nos OUTROS formulários e no cadastro de materiais
    (catálogo do hospital e o que já foi cadastrado no estoque). O formulário
    aberto já é filtrado na própria tela."""
    from ..utils import sem_acento
    palavras = [p for p in sem_acento(texto(termo)).upper().replace(",", " ").split() if p]
    if not palavras:
        return []
    def casa(txt: str) -> bool:
        alvo = sem_acento(txt).upper()
        return all(p in alvo for p in palavras)
    saida, vistos = [], set()
    no_atual = {c for l in linhas(formulario_atual) for c in l["codigos"].split()} if formulario_atual else set()
    for chave, form in FORMULARIOS.items():
        if chave == formulario_atual:
            continue
        for l in linhas(chave):
            if casa(f"{l['codigos']} {l['descricao']}"):
                k = (l["codigos"], l["descricao"])
                if k in vistos:
                    continue
                vistos.add(k)
                saida.append({"codigos": l["codigos"], "descricao": l["descricao"],
                              "origem": f"formulário {form['titulo']}",
                              "pede_especificacao": l["pede_especificacao"] and not l["codigos"]})
    cond = " AND ".join("(UPPER(descritivo_hospital) LIKE ? OR codigo_aghu LIKE ?)" for _ in palavras)
    params = [x for p in palavras for x in (f"%{p}%", f"%{p}%")]
    cat = db.consultar(f"SELECT codigo_aghu, descritivo_hospital FROM materiais_mestre WHERE {cond} "
                       f"ORDER BY descritivo_hospital LIMIT {int(limite)}", tuple(params))
    cond_u = " AND ".join("(UPPER(COALESCE(NULLIF(descritivo_hospital,''), xProd)) LIKE ? OR codigo_aghu LIKE ?)" for _ in palavras)
    est = db.consultar(
        f"""SELECT codigo_aghu, MAX(COALESCE(NULLIF(descritivo_hospital,''), xProd)) AS descritivo_hospital
            FROM unidades WHERE COALESCE(codigo_aghu,'') <> '' AND {cond_u}
            GROUP BY codigo_aghu ORDER BY 2 LIMIT {int(limite)}""", tuple(params))
    ja_codigos = {c for i in saida for c in i["codigos"].split()} | no_atual
    for r in list(cat) + list(est):
        cod = normalizar_codigo_aghu(r["codigo_aghu"])
        if not cod or cod in ja_codigos:
            continue
        ja_codigos.add(cod)
        saida.append({"codigos": cod, "descricao": texto(r["descritivo_hospital"]),
                      "origem": "cadastro de materiais", "pede_especificacao": False})
    for i in saida:
        cods = i["codigos"].split()
        i["em_estoque"] = int(db.escalar(
            f"""SELECT COUNT(*) FROM unidades WHERE status = 'em_estoque_recebimento'
                AND codigo_aghu IN ({','.join('?' for _ in cods)})""", tuple(cods)) or 0) if cods else 0
    return saida[:limite]


def incluir_da_busca(id_atendimento: str, codigos_txt: str, descricao: str, quantidade,
                     especificacao: str, usuario: str) -> tuple[bool, str]:
    """Material achado em outro formulário ou no cadastro: entra como item fora
    do formulário (com todos os códigos AGHU da linha)."""
    ok, msg = _pode_editar(id_atendimento)
    if not ok:
        return False, msg
    cods = codigos(codigos_txt)
    qtd = inteiro(quantidade, 0)
    if qtd <= 0 or qtd > 999:
        return False, "Informe a quantidade."
    descricao = texto(descricao).upper()
    espec = texto(especificacao)
    if not cods and not espec and descricao.endswith(":"):
        return False, "Escreva o tipo/tamanho."
    if not descricao and not cods:
        return False, "Material sem descrição."
    with db.transacao() as conn:
        id_sol = _abrir_ou_pegar(conn, id_atendimento, usuario)
        conn.execute(
            """INSERT INTO solicitacao_itens (id_solicitacao, formulario, linha, codigos, descricao,
                                              especificacao, quantidade)
               VALUES (?,?,0,?,?,?,?)""", (id_sol, AVULSO, " ".join(cods), descricao or f"AGHU {cods[0]}",
                                           espec or None, qtd))
        db.registrar_evento(conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
                            observacao=f"Solicitação (busca): {qtd}x {descricao}"
                                       + (f" ({espec})" if espec else "") + (f" — AGHU {' / '.join(cods)}" if cods else ""))
    return True, f"Incluído: {qtd}x."


# ---------------------------------------------------------------- escrita (sala)

def _pode_editar(id_atendimento: str) -> tuple[bool, str]:
    at = db.consultar_um("SELECT status, uso_finalizado_em FROM atendimentos WHERE id_atendimento = ?",
                         (texto(id_atendimento),))
    if not at:
        return False, "Atendimento não encontrado."
    if at["status"] != "aberto" or texto(at["uso_finalizado_em"]):
        return False, "A solicitação só pode ser alterada com o atendimento aberto."
    return True, ""


def _abrir_ou_pegar(conn, id_atendimento: str, usuario: str) -> str:
    linha = conn.execute("""SELECT id_solicitacao, cancelada_em, finalizada_em, motivo_faltas
                            FROM solicitacoes WHERE id_atendimento = ?""",
                         (id_atendimento,)).fetchone()
    if linha:
        # v18.7.3: se a sala tinha cancelado e voltou a pedir, a solicitação reabre.
        # v18.8.2: ...mas SÓ com o que for pedido agora — os itens cancelados não voltam
        # (eles ficaram registrados no evento do cancelamento).
        if texto(linha[1]):
            # v18.38: o vínculo aponta para o item — sai primeiro, senão o
            # banco recusa o DELETE.
            conn.execute("""DELETE FROM solicitacao_vinculos WHERE id_item IN
                            (SELECT id_item FROM solicitacao_itens WHERE id_solicitacao = ?)""",
                         (linha[0],))
            conn.execute("DELETE FROM solicitacao_itens WHERE id_solicitacao = ?", (linha[0],))
        # v18.32: a farmácia tinha finalizado a dispensa (ex.: "sem estoque") e a
        # sala pediu outro material. A finalização era mantida e `em_aberto()`
        # descartava a solicitação: o pedido novo não chegava à farmácia. Pedir
        # de novo reabre — os itens já pedidos continuam, e a finalização anterior
        # fica registrada no evento.
        if texto(linha[2]):
            # v18.43: o que vier agora é uma RODADA nova. Sem isso, o pedido
            # novo se misturava com o anterior na tela de quem dispensa.
            conn.execute("UPDATE solicitacoes SET rodada = COALESCE(rodada, 1) + 1 WHERE id_solicitacao = ?",
                         (linha[0],))
            db.registrar_evento(
                conn, tipo="solicitacao_reaberta", id_atendimento=id_atendimento, usuario=usuario,
                observacao=("Solicitação reaberta por novo pedido da sala. A dispensa tinha sido "
                            f"finalizada em {data_hora_br(linha[2])}"
                            + (f" — motivo: {texto(linha[3])}" if texto(linha[3]) else "") + "."))
        conn.execute("""UPDATE solicitacoes SET atualizado_em = ?, atualizado_por = ?, cancelada_em = NULL,
                        cancelada_por = NULL, motivo_cancelamento = NULL,
                        finalizada_em = NULL, finalizada_por = NULL, motivo_faltas = NULL
                        WHERE id_solicitacao = ?""",
                     (db.agora(), usuario, linha[0]))
        return linha[0]
    novo = gerar_id("SOL")
    conn.execute("""INSERT INTO solicitacoes (id_solicitacao, id_atendimento, criado_por, criado_em,
                                              atualizado_por, atualizado_em)
                    VALUES (?,?,?,?,?,?)""", (novo, id_atendimento, usuario, db.agora(), usuario, db.agora()))
    return novo


def _rodada(conn, id_sol: str) -> int:
    """Rodada em que entram os itens pedidos agora (v18.43)."""
    linha = conn.execute("SELECT COALESCE(rodada, 1) FROM solicitacoes WHERE id_solicitacao = ?",
                         (id_sol,)).fetchone()
    return int(linha[0]) if linha else 1


def salvar_formulario(id_atendimento: str, chave: str, quantidades: dict, especificacoes: dict,
                      usuario: str, observacao: str | None = None) -> tuple[bool, str]:
    """Grava o que a sala pediu NESTE formulário (os outros ficam como estão)."""
    ok, msg = _pode_editar(id_atendimento)
    if not ok:
        return False, msg
    if chave not in FORMULARIOS:
        return False, "Escolha o formulário."
    pedidos = []
    for l in linhas(chave):
        qtd = inteiro(quantidades.get(str(l["linha"])), 0)
        if qtd < 0 or qtd > 999:
            return False, f"Quantidade inválida em “{l['descricao']}”."
        espec = texto(especificacoes.get(str(l["linha"])))
        if qtd and l["pede_especificacao"] and not l["codigos"] and not espec:
            return False, f"Escreva o tipo/tamanho em “{l['descricao']}”."
        if qtd:
            pedidos.append((l, qtd, espec))
    with db.transacao() as conn:
        id_sol = _abrir_ou_pegar(conn, id_atendimento, usuario)
        antes = {r["linha"]: dict(r) for r in conn.execute(
            "SELECT * FROM solicitacao_itens WHERE id_solicitacao = ? AND formulario = ?",
            (id_sol, chave)).fetchall()}
        # v18.38: a linha que CONTINUA no pedido é atualizada, não apagada e
        # recriada. Recriar trocava o id_item e derrubava o vínculo que a
        # farmácia tinha feito ao atender com material de outro código — o que
        # fazia o próprio DELETE falhar ("FOREIGN KEY constraint failed")
        # quando a sala mexia no pedido depois de a farmácia já ter atendido.
        mantidas = {l["linha"] for l, _, _ in pedidos}
        for linha_antiga, ant in antes.items():
            if linha_antiga not in mantidas:
                conn.execute("DELETE FROM solicitacao_vinculos WHERE id_item = ?", (ant["id_item"],))
                conn.execute("DELETE FROM solicitacao_itens WHERE id_item = ?", (ant["id_item"],))
        for l, qtd, espec in pedidos:
            anterior = antes.get(l["linha"]) or {}
            manter_manual = bool(anterior) and texto(anterior.get("especificacao")) == espec
            manual_em = anterior.get("atendido_manual_em") if manter_manual else None
            manual_por = anterior.get("atendido_manual_por") if manter_manual else None
            if anterior:
                conn.execute(
                    """UPDATE solicitacao_itens SET codigos = ?, descricao = ?, especificacao = ?,
                              quantidade = ?, atendido_manual_em = ?, atendido_manual_por = ?
                       WHERE id_item = ?""",
                    (l["codigos"], l["descricao"], espec or None, qtd, manual_em, manual_por,
                     anterior["id_item"]))
            else:
                conn.execute(
                    """INSERT INTO solicitacao_itens (id_solicitacao, formulario, linha, codigos,
                                                      descricao, especificacao, quantidade,
                                                      atendido_manual_em, atendido_manual_por, rodada)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (id_sol, chave, l["linha"], l["codigos"], l["descricao"], espec or None, qtd,
                     manual_em, manual_por, _rodada(conn, id_sol)))
        if observacao is not None:
            conn.execute("UPDATE solicitacoes SET observacao = ? WHERE id_solicitacao = ?",
                         (texto(observacao), id_sol))
        db.registrar_evento(
            conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
            observacao=(f"Solicitação ({FORMULARIOS[chave]['titulo']}): "
                        + ("; ".join(f"{q}x {l['descricao']}" + (f" ({e})" if e else "") for l, q, e in pedidos)
                           or "nenhum item")))
    total = sum(q for _, q, _ in pedidos)
    return True, (f"Solicitação gravada: {len(pedidos)} item(ns), {total} unidade(s) neste formulário. "
                  "A farmácia já vê na tela de dispensar.")


def adicionar_avulso(id_atendimento: str, codigo_aghu: str, quantidade, descricao: str,
                     usuario: str) -> tuple[bool, str]:
    ok, msg = _pode_editar(id_atendimento)
    if not ok:
        return False, msg
    cod = normalizar_codigo_aghu(codigo_aghu)
    qtd = inteiro(quantidade, 0)
    if not cod and not texto(descricao):
        return False, "Informe o código AGHU (ou, sem código, a descrição) do material."
    if qtd <= 0 or qtd > 999:
        return False, "Informe a quantidade."
    if cod and not texto(descricao):
        from . import materiais
        descricao = materiais.descritivo_hospital(cod) or materiais.descritivo_hospital(codigo_aghu)
    descricao = texto(descricao).upper() or f"AGHU {cod}"
    with db.transacao() as conn:
        id_sol = _abrir_ou_pegar(conn, id_atendimento, usuario)
        conn.execute(
            """INSERT INTO solicitacao_itens (id_solicitacao, formulario, linha, codigos,
                                              descricao, quantidade, rodada)
               VALUES (?,?,0,?,?,?,?)""",
            (id_sol, AVULSO, cod, descricao, qtd, _rodada(conn, id_sol)))
        db.registrar_evento(conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
                            observacao=f"Solicitação (fora do formulário): {qtd}x {descricao}"
                                       + (f" — AGHU {cod}" if cod else ""))
    return True, f"Incluído na solicitação: {qtd}x {descricao}."


def remover_item(id_atendimento: str, id_item, usuario: str) -> tuple[bool, str]:
    ok, msg = _pode_editar(id_atendimento)
    if not ok:
        return False, msg
    linha = db.consultar_um(
        """SELECT i.* FROM solicitacao_itens i JOIN solicitacoes s ON s.id_solicitacao = i.id_solicitacao
           WHERE i.id_item = ? AND s.id_atendimento = ?""", (inteiro(id_item, 0), texto(id_atendimento)))
    if not linha:
        return False, "Item não encontrado nesta solicitação."
    with db.transacao() as conn:
        conn.execute("DELETE FROM solicitacao_vinculos WHERE id_item = ?", (linha["id_item"],))
        conn.execute("DELETE FROM solicitacao_itens WHERE id_item = ?", (linha["id_item"],))
        db.registrar_evento(conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
                            observacao=f"Tirado da solicitação: {linha['quantidade']}x {linha['descricao']}")
    return True, "Item tirado da solicitação."


# ---------------------------------------------------------------- farmácia

MOTIVOS_OUTRO_CODIGO = (
    "Código AGHU do material mudou",
    "Material cadastrado com outro código AGHU",
    "Material equivalente, combinado com a sala",
    # v18.43: a linha pedida pelo nome (sem AGHU) passa a poder ser associada
    # ao material que foi bipado.
    "Material que a sala pediu pelo nome",
)

# v18.43: motivos de falta, para a farmácia não ter de escrever do zero.
MOTIVOS_FALTA = (
    "Sem estoque na farmácia",
    "Sem estoque no almoxarifado",
    "Material em falta no fornecedor",
    "Combinado com a sala: será usado outro material",
)


def vincular_outro_codigo(id_atendimento: str, id_item, ids_unidades: list[str], motivo: str,
                          usuario: str) -> tuple[bool, str]:
    """Linha atendida por material bipado que não casa com ela pelo código.

    v18.43: vale também para a linha SEM código AGHU (o formulário pede pelo
    nome, ex.: "CATETER DIAGNÓSTICO — TIPO: Cobra 05 F"). Antes essas linhas
    só tinham o "marcar atendido", que não dizia qual material foi dado.
    """
    motivo = texto(motivo)
    if len(motivo) < 5:
        return False, "Informe o motivo (ex.: o código AGHU do material mudou)."
    s = situacao(id_atendimento)
    linha = next((l for l in s["linhas"] if l["id_item"] == inteiro(id_item, 0)), None)
    if not linha:
        return False, "Item não encontrado nesta solicitação."
    falta = linha["quantidade"] - linha["dispensado"]
    if falta <= 0:
        return False, "Este item já está atendido."
    livres = {i for g in s["nao_solicitados"] for i in g["ids"]}
    escolhidos = [i for i in ids_unidades if i in livres][:falta]
    if not escolhidos:
        return False, "Escolha um material bipado que não esteja em outra linha da solicitação."
    with db.transacao() as conn:
        for id_u in escolhidos:
            conn.execute("""INSERT INTO solicitacao_vinculos (id_item, id_unidade, motivo, vinculado_por, vinculado_em)
                            VALUES (?,?,?,?,?)""", (linha["id_item"], id_u, motivo, usuario, db.agora()))
        if linha["sem_codigo"]:
            # a linha passa a ter material de verdade: o check à mão sai de cena
            conn.execute("""UPDATE solicitacao_itens SET atendido_manual_em = NULL,
                            atendido_manual_por = NULL WHERE id_item = ?""", (linha["id_item"],))
        db.registrar_evento(
            conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario, motivo=motivo,
            observacao=(f"Atendido com outro código: {len(escolhidos)}x {linha['descricao']} "
                        f"(pedido AGHU {linha['codigos'] or '—'}) ← unidade(s) {', '.join(escolhidos)}"))
    rotulo = "associado ao material bipado" if linha["sem_codigo"] else "atendido com outro código"
    return True, f"{linha['descricao']}: {rotulo} ({len(escolhidos)} unid.)."


def desfazer_vinculos(id_atendimento: str, id_item, usuario: str) -> tuple[bool, str]:
    linha = db.consultar_um(
        """SELECT i.* FROM solicitacao_itens i JOIN solicitacoes s ON s.id_solicitacao = i.id_solicitacao
           WHERE i.id_item = ? AND s.id_atendimento = ?""", (inteiro(id_item, 0), texto(id_atendimento)))
    if not linha:
        return False, "Item não encontrado nesta solicitação."
    with db.transacao() as conn:
        n = conn.execute("DELETE FROM solicitacao_vinculos WHERE id_item = ?", (linha["id_item"],)).rowcount
        db.registrar_evento(conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
                            observacao=f"Desfeito o atendimento com outro código: {linha['descricao']}")
    return True, f"Vínculo desfeito ({n} unid.). O material volta a aparecer como não solicitado."


def marcar_manual(id_atendimento: str, id_item, usuario: str, atendido: bool = True) -> tuple[bool, str]:
    """Linha sem código AGHU: a farmácia marca (ou desmarca) que atendeu."""
    linha = db.consultar_um(
        """SELECT i.* FROM solicitacao_itens i JOIN solicitacoes s ON s.id_solicitacao = i.id_solicitacao
           WHERE i.id_item = ? AND s.id_atendimento = ?""", (inteiro(id_item, 0), texto(id_atendimento)))
    if not linha:
        return False, "Item não encontrado nesta solicitação."
    if codigos(linha["codigos"]):
        return False, "Este item tem código AGHU: o check é dado pelo bip."
    with db.transacao() as conn:
        conn.execute("UPDATE solicitacao_itens SET atendido_manual_em = ?, atendido_manual_por = ? WHERE id_item = ?",
                     (db.agora() if atendido else None, usuario if atendido else None, linha["id_item"]))
        db.registrar_evento(conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
                            observacao=("Marcado como atendido: " if atendido else "Desmarcado: ")
                                       + linha["descricao"]
                                       + (f" ({linha['especificacao']})" if linha["especificacao"] else ""))
    return True, "Marcado como atendido." if atendido else "Check retirado."


def marcar_falta(id_atendimento: str, id_item, motivo: str, usuario: str,
                 falta: bool = True) -> tuple[bool, str]:
    """v18.43: a farmácia marca a linha que não tem como atender (falta no estoque).

    A linha sai da conta do que ainda está "aguardando farmácia" e aparece como
    falta, com o motivo e quem marcou — para a sala ver e se organizar sem ter
    de perguntar. Desmarcar devolve a linha para a fila.
    """
    linha = db.consultar_um(
        """SELECT i.* FROM solicitacao_itens i JOIN solicitacoes s ON s.id_solicitacao = i.id_solicitacao
           WHERE i.id_item = ? AND s.id_atendimento = ?""", (inteiro(id_item, 0), texto(id_atendimento)))
    if not linha:
        return False, "Item não encontrado nesta solicitação."
    motivo = texto(motivo)
    if falta and len(motivo) < 3:
        return False, "Escreva o motivo (ex.: sem estoque na farmácia)."
    atual = next((l for l in situacao(id_atendimento)["linhas"] if l["id_item"] == linha["id_item"]), None)
    if falta and atual and atual["status"] == "atendido":
        return False, "Este item já está atendido."
    with db.transacao() as conn:
        conn.execute("""UPDATE solicitacao_itens SET falta_em = ?, falta_por = ?, falta_motivo = ?
                        WHERE id_item = ?""",
                     (db.agora() if falta else None, usuario if falta else None,
                      motivo if falta else None, linha["id_item"]))
        db.registrar_evento(
            conn, tipo="solicitacao_opme", id_atendimento=id_atendimento, usuario=usuario,
            motivo=motivo if falta else "",
            observacao=(("Marcado como falta de estoque: " if falta else "Falta de estoque desfeita: ")
                        + linha["descricao"]
                        + (f" ({linha['especificacao']})" if linha["especificacao"] else "")))
    return True, ("Marcado como falta de estoque. A sala vê o motivo no pedido."
                  if falta else "A linha voltou para a fila da farmácia.")


def cancelar(id_atendimento: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    """v18.7.3: a SALA cancela a solicitação de OPME (o pedido some da farmácia).

    O que a farmácia já dispensou continua com o paciente e segue o fluxo normal
    (usar ou devolver). Se a sala voltar a pedir, a solicitação reabre."""
    ok, msg = _pode_editar(id_atendimento)
    if not ok:
        return False, msg
    motivo = texto(motivo)
    if len(motivo) < 3:
        return False, "Informe o motivo do cancelamento da solicitação."
    with db.transacao() as conn:
        sol = conn.execute("""SELECT id_solicitacao, cancelada_em, finalizada_em FROM solicitacoes
                              WHERE id_atendimento = ?""", (texto(id_atendimento),)).fetchone()
        if not sol:
            return False, "Não há solicitação de OPME para este paciente."
        if texto(sol[1]):
            return False, "Esta solicitação já foi cancelada."
        if texto(sol[2]):
            return False, "A farmácia já finalizou a dispensa desta solicitação; não há o que cancelar."
        conn.execute("""UPDATE solicitacoes SET cancelada_em = ?, cancelada_por = ?, motivo_cancelamento = ?
                        WHERE id_solicitacao = ? AND COALESCE(cancelada_em, '') = ''""",
                     (db.agora(), usuario, motivo, sol[0]))
        itens_cancelados = "; ".join(f"{r[0]} x{r[1]}" for r in conn.execute(
            "SELECT descricao, quantidade FROM solicitacao_itens WHERE id_solicitacao = ? ORDER BY id_item", (sol[0],)))
        db.registrar_evento(conn, tipo="solicitacao_cancelada", id_atendimento=texto(id_atendimento),
                            usuario=usuario, motivo=motivo,
                            observacao=f"Solicitação de OPME cancelada pela sala. Itens: {itens_cancelados}"[:900])
    ja = sum(l["dispensado"] for l in situacao(id_atendimento).get("linhas", []))
    extra = (f" {ja} item(ns) já tinham sido dispensados e continuam com o paciente "
             "(registre o uso ou devolva como não utilizado).") if ja else ""
    return True, "Solicitação de OPME cancelada. A farmácia não vê mais este pedido." + extra


def finalizar(id_atendimento: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    """"Finalizar dispensa": com item faltando, o motivo é obrigatório.

    v18.33: valida o estado antes de concluir. Sem isso dava para finalizar uma
    solicitação CANCELADA (ficava com as duas datas preenchidas) e para
    finalizar de novo, trocando a justificativa já registrada.
    """
    s = situacao(id_atendimento)
    if not s["existe"]:
        return True, ""
    atual = db.consultar_um("""SELECT COALESCE(cancelada_em,'') AS cancelada_em,
                                      COALESCE(finalizada_em,'') AS finalizada_em,
                                      COALESCE(cancelada_por,'') AS cancelada_por,
                                      COALESCE(finalizada_por,'') AS finalizada_por
                               FROM solicitacoes WHERE id_atendimento = ?""", (texto(id_atendimento),))
    if atual and texto(atual["cancelada_em"]):
        return False, ("Esta solicitação foi cancelada pela sala em "
                       f"{data_hora_br(atual['cancelada_em'])}"
                       + (f" por {atual['cancelada_por']}" if atual["cancelada_por"] else "")
                       + " — não há dispensa a finalizar.")
    if atual and texto(atual["finalizada_em"]):
        return False, ("A dispensa desta solicitação já foi finalizada em "
                       f"{data_hora_br(atual['finalizada_em'])}"
                       + (f" por {atual['finalizada_por']}" if atual["finalizada_por"] else "")
                       + ". Para mexer de novo, a sala precisa fazer um novo pedido.")
    motivo = texto(motivo)
    if s["qtd_faltando"] and len(motivo) < 3:
        return False, (f"Há {s['qtd_faltando']} item(ns) da solicitação sem atender. "
                       "Informe o motivo para finalizar a dispensa.")
    with db.transacao() as conn:
        conn.execute("""UPDATE solicitacoes SET finalizada_em = ?, finalizada_por = ?, motivo_faltas = ?
                        WHERE id_atendimento = ?""",
                     (db.agora(), usuario, motivo if s["qtd_faltando"] else None, texto(id_atendimento)))
        if s["qtd_faltando"] or s["nao_solicitados"]:
            db.registrar_evento(
                conn, tipo="solicitacao_divergente", id_atendimento=id_atendimento, usuario=usuario,
                motivo=motivo,
                observacao=("Dispensa finalizada com divergência da solicitação. Faltando: "
                            + ("; ".join(f"{f['falta']}x {f['descricao']}" for f in s["faltando"]) or "nada")
                            + ". Não solicitado: "
                            + ("; ".join(f"{g['quantidade']}x {g['descricao']}" for g in s["nao_solicitados"])
                               or "nada")
                            + "."))
    return True, ""
