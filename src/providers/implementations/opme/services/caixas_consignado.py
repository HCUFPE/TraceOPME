"""v17 — caixas de consignado.

A farmácia monta a caixa (bipa cada item para dentro). Na sala, cada item
usado é bipado normalmente e sai da caixa no uso. Na volta, em vez de bipar item
a item, a sala bipa a CAIXA na tela de devolução e digita quantos itens estão
voltando; o farmacêutico confirma com a senha, como em qualquer devolução.

A contagem tem que bater com o que o sistema espera (itens ainda na caixa). Se
não bater, a devolução é recusada, gera alerta e a caixa fica BLOQUEADA com os
itens — ninguém usa material dela em outro procedimento até alguém do
farmácia conferir. No mesmo atendimento a sala ainda pode bipar o uso que
esqueceu e devolver de novo; a caixa só é liberada na conferência.
"""

from .. import busca, db, log
from ..domain import (DIVERGENCIA, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, EM_SALA, TRANSITO_SALA,
                      estoque_de_volta)

# v17: na caixa = no estoque ou dispensado para a sala (ainda não usado).
NA_CAIXA = (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA, TRANSITO_SALA, EM_SALA)
from ..utils import inteiro, texto
from . import alertas, caixas


def _caixa(id_caixa: str) -> dict | None:
    return db.consultar_um("SELECT * FROM caixas WHERE UPPER(id_caixa) = UPPER(?)",
                           (texto(id_caixa),))


def criar(dados: dict, usuario: str) -> tuple[bool, str, str]:
    """v18.11.2: a caixa tem só NOME — não é de um fornecedor; os itens dentro dela
    podem ser de vários. O código sai do nome (ex.: "CARDIOLOGIA - NID" → CX-CARD-01)."""
    fornecedor = texto(dados.get("fornecedor"))   # opcional (telas antigas)
    dados = dict(dados)
    if not texto(dados.get("nome")):
        return False, "Dê um nome à caixa (ex.: “CARDIOLOGIA - NID”).", ""
    dados["especialidade"] = texto(dados.get("especialidade")) or texto(dados.get("nome"))
    ok, mensagem, id_caixa = caixas.criar(dados, usuario)
    if ok:
        if fornecedor:
            db.executar("UPDATE caixas SET fornecedor = ? WHERE id_caixa = ?", (fornecedor, id_caixa))
        mensagem = f"Caixa {id_caixa} criada. Agora bipe os itens para dentro dela."
    return ok, mensagem, id_caixa


def esperado(id_caixa: str) -> int:
    """Quantos itens o sistema espera encontrar na caixa agora."""
    return db.escalar(
        f"SELECT COUNT(*) FROM unidades WHERE UPPER(id_caixa) = UPPER(?) AND status IN ({','.join('?' for _ in NA_CAIXA)})",
        (texto(id_caixa), *NA_CAIXA))


def listar(incluir_almoxarifado: bool = False) -> list[dict]:
    """Caixas da farmácia. nov/2026: as do almoxarifado (montando ou a caminho) ficam
    de fora, a não ser que se peça (`incluir_almoxarifado`)."""
    filtro = "" if incluir_almoxarifado else \
        " AND COALESCE(NULLIF(c.local, ''), 'farmacia') NOT IN ('almoxarifado', 'transito')"
    linhas = db.consultar(
        f"""SELECT c.*, (SELECT COUNT(*) FROM unidades u WHERE u.id_caixa = c.id_caixa) AS total,
                  (SELECT GROUP_CONCAT(f, ', ') FROM (SELECT DISTINCT TRIM(u2.fornecedor) AS f FROM unidades u2
                    WHERE u2.id_caixa = c.id_caixa AND TRIM(COALESCE(u2.fornecedor,'')) <> '' ORDER BY 1)) AS fornecedores,
                  a.prontuario AS bloqueio_prontuario, a.sala AS bloqueio_sala
           FROM caixas c LEFT JOIN atendimentos a ON a.id_atendimento = c.bloqueio_atendimento
           WHERE c.encerrada_em IS NULL{filtro}
           ORDER BY c.bloqueada DESC, c.id_caixa""")
    return linhas


def buscar(id_caixa: str) -> dict | None:
    caixa = _caixa(id_caixa)
    if not caixa:
        return None
    caixa = dict(caixa)
    caixa["total"] = esperado(caixa["id_caixa"])
    if caixa.get("bloqueio_atendimento"):
        at = db.consultar_um("SELECT prontuario, sala, unidade FROM atendimentos WHERE id_atendimento = ?",
                             (caixa["bloqueio_atendimento"],))
        caixa["bloqueio_prontuario"] = at["prontuario"] if at else ""
        caixa["bloqueio_sala"] = at["sala"] if at else ""
    return caixa


def bloqueada_para(id_caixa: str, id_atendimento: str) -> dict | None:
    """A caixa está bloqueada para ESTE atendimento? (no próprio atendimento, não)."""
    caixa = _caixa(id_caixa)
    if not caixa or not caixa["bloqueada"]:
        return None
    if texto(caixa["bloqueio_atendimento"]) == texto(id_atendimento):
        return None
    # Caixa do dia que voltou faltando itens: a sala daquela sala ainda pode bipar
    # o uso que esqueceu (é assim que a pendência se resolve).
    from . import caixas_sala
    if caixas_sala.permite_uso(caixa["id_caixa"], id_atendimento)[1] == "pendencia":
        return None
    return dict(caixa)


def abrir_para_uso(id_caixa: str, id_atendimento: str) -> dict:
    """Registro de uso: a sala bipa a CAIXA antes dos itens que tirou dela.

    Não grava nada — só confirma que a caixa existe, pode ser usada neste
    atendimento e tem material; a tela guarda a caixa como "ativa" e manda o
    código dela junto com cada item bipado em seguida.
    """
    caixa = _caixa(id_caixa)
    if not caixa:
        return {"ok": False, "mensagem": f"Caixa {texto(id_caixa)} não encontrada."}
    if caixa["encerrada_em"]:
        return {"ok": False, "mensagem": f"A caixa {caixa['id_caixa']} foi encerrada e não pode ser usada."}
    from . import caixas_sala
    pode, motivo_turno, restam = caixas_sala.permite_uso(caixa["id_caixa"], id_atendimento)
    if pode is False:
        return {"ok": False, "mensagem": motivo_turno}
    if pode and motivo_turno == "pendencia":
        return {"ok": True, "caixa_ativa": {
                    "id_caixa": caixa["id_caixa"], "nome": caixa["nome"],
                    "fornecedor": texto(caixa.get("fornecedor")), "total": restam},
                "mensagem": (f"Caixa {caixa['id_caixa']} com pendência: {restam} item(ns) não voltaram. "
                             f"Bipe o item que foi usado neste paciente.")}
    bloqueio = bloqueada_para(caixa["id_caixa"], id_atendimento)
    if bloqueio:
        return {"ok": False, "mensagem": (
            f"A caixa {caixa['id_caixa']} está BLOQUEADA para conferência "
            f"({texto(bloqueio['bloqueio_motivo'])}). Use material de outra caixa ou "
            f"peça à farmácia para conferir e liberar.")}
    pendente = _ja_devolvida_ou_pendente(caixa["id_caixa"], "")
    if pendente and "aguardando" in pendente:
        return {"ok": False, "mensagem": (
            f"A caixa {caixa['id_caixa']} foi bipada como devolvida e está aguardando a "
            f"confirmação da farmácia. Se ela não foi devolvida, tire-a da devolução primeiro.")}
    total = esperado(caixa["id_caixa"])
    if not total:
        return {"ok": False, "mensagem": f"A caixa {caixa['id_caixa']} está vazia no sistema."}
    return {"ok": True, "caixa_ativa": {
                "id_caixa": caixa["id_caixa"], "nome": caixa["nome"],
                "fornecedor": texto(caixa.get("fornecedor")), "total": total},
            "mensagem": (f"Caixa {caixa['id_caixa']} selecionada ({total} item(ns)). "
                         f"Agora bipe o item usado.")}


def _ja_devolvida_ou_pendente(id_caixa: str, id_atendimento: str) -> str:
    if db.escalar(
            """SELECT COUNT(*) FROM eventos WHERE tipo = 'devolver_caixa' AND id_atendimento = ?
               AND observacao LIKE ?""", (id_atendimento, f"%[{id_caixa}]%")):
        return "Esta caixa já foi devolvida neste atendimento."
    if db.escalar(
            """SELECT COUNT(*) FROM devolucao_itens i JOIN devolucoes d ON d.id_devolucao = i.id_devolucao
               WHERE i.tipo = 'caixa' AND UPPER(i.id_caixa) = UPPER(?) AND i.situacao = 'pendente'
                 AND d.status = 'pendente'""", (id_caixa,)):
        return ("Esta caixa já foi bipada numa devolução e está aguardando a confirmação "
                "da farmácia.")
    return ""


def bloquear(conn, *, caixa: dict, id_atendimento: str, motivo: str, usuario: str) -> None:
    conn.execute(
        """UPDATE caixas SET bloqueada = 1, bloqueio_motivo = ?, bloqueio_atendimento = ?,
                             bloqueada_em = ?, bloqueada_por = ?
           WHERE id_caixa = ?""",
        (motivo, id_atendimento, db.agora(), usuario, caixa["id_caixa"]))


def alertar_bloqueio(caixa: dict, id_atendimento: str, motivo: str, usuario: str, detalhe: str) -> None:
    at = db.consultar_um("SELECT prontuario, sala FROM atendimentos WHERE id_atendimento = ?",
                         (id_atendimento,)) or {}
    alertas.criar(
        modulo_destino="farmacia",
        titulo=f"Caixa {caixa['id_caixa']} bloqueada — contagem não bate",
        mensagem=(f"{caixa['nome']} ({texto(caixa.get('fornecedor'))}): {motivo}\n"
                  f"Prontuário {at.get('prontuario') or '—'}, sala {at.get('sala') or '—'}. {detalhe}\n"
                  f"Se foi uso não bipado, a sala pode bipar o uso neste atendimento e "
                  f"devolver de novo. A caixa só volta a ser usada depois da conferência."),
        usuario=usuario, id_atendimento=id_atendimento,
        link=f"/farmacia/caixas-consignado/{caixa['id_caixa']}")
    log.aviso(f"caixa bloqueada · {caixa['id_caixa']} · {motivo}", usuario)


def devolver(*, id_caixa: str, id_atendimento: str, quantidade, usuario: str,
             devolvido_por: str = "") -> dict:
    """1ª etapa da devolução da caixa: a sala bipa a caixa e digita a contagem.

    Se a contagem não bate com o sistema, recusa na hora, bloqueia a caixa e
    alerta a farmácia. Se bate, devolve ok — quem chamou (`devolucoes.bipar`)
    coloca a caixa na devolução pendente; o recebimento só vale quando a
    farmácia confirmar com a senha (`receber`).
    """
    caixa = _caixa(id_caixa)
    if not caixa:
        return {"ok": False, "mensagem": f"Caixa {texto(id_caixa)} não encontrada."}
    if caixa["encerrada_em"]:
        return {"ok": False, "mensagem": "Esta caixa foi encerrada."}
    if not texto(id_atendimento):
        return {"ok": False, "mensagem": "Selecione o atendimento antes de devolver a caixa."}
    from . import caixas_sala
    if caixas_sala.ativo_da_caixa(caixa["id_caixa"]):
        return {"ok": False, "mensagem": (
            f"A caixa {caixa['id_caixa']} está na sala pelo dia. Ela é devolvida inteira em "
            f"Sala de procedimento → Caixas na sala, não pelo paciente.")}
    if caixa["bloqueada"] and texto(caixa["bloqueio_atendimento"]) != texto(id_atendimento):
        return {"ok": False, "mensagem": (
            f"A caixa {caixa['id_caixa']} está BLOQUEADA para conferência "
            f"({texto(caixa['bloqueio_motivo'])}). Só a farmácia libera, na conferência.")}
    qtd_txt = texto(quantidade)
    if not qtd_txt.isdigit():
        return {"ok": False, "pede_quantidade": True,
                "caixa": {"id_caixa": caixa["id_caixa"], "nome": caixa["nome"],
                          "fornecedor": texto(caixa.get("fornecedor"))},
                "mensagem": "Digite quantos itens estão voltando nesta caixa."}
    informado = inteiro(qtd_txt, -1)
    ja = _ja_devolvida_ou_pendente(caixa["id_caixa"], id_atendimento)
    if ja:
        return {"ok": False, "mensagem": ja}

    previsto = esperado(caixa["id_caixa"])
    marcador = f"[{caixa['id_caixa']}]"
    if informado != previsto:
        diferenca = previsto - informado
        texto_dif = (f"faltam {diferenca}" if diferenca > 0 else f"sobram {-diferenca}")
        motivo = (f"Devolução com contagem diferente: informado {informado}, "
                  f"esperado {previsto} ({texto_dif}).")
        with db.transacao() as conn:
            bloquear(conn, caixa=caixa, id_atendimento=id_atendimento, motivo=motivo, usuario=usuario)
            db.registrar_evento(
                conn, tipo="devolucao_caixa_divergente", id_atendimento=id_atendimento,
                usuario=usuario, motivo=motivo, devolvido_por=devolvido_por,
                observacao=f"{marcador} contagem feita por {devolvido_por or usuario} na devolução")
        alertar_bloqueio(caixa, id_atendimento, motivo, usuario,
                         f"Devolução recusada; devolvida por {devolvido_por or usuario} (login {usuario}).")
        return {"ok": False, "divergencia": True, "mensagem": (
            f"CONTAGEM NÃO BATE — {texto_dif.upper()} item(ns). A devolução NÃO foi registrada "
            f"e a caixa {caixa['id_caixa']} foi BLOQUEADA para conferência. Reconte; se algum "
            f"item foi usado e não bipado, bipe o uso neste paciente e devolva a caixa de novo.")}

    return {"ok": True, "caixa": {"id_caixa": caixa["id_caixa"], "nome": caixa["nome"],
                                  "total": informado}, "informado": informado}


def receber(conn, *, id_caixa: str, id_atendimento: str, informado: int, bipado_por: str,
            devolvido_por: str, responsavel: dict, nao_recebida: bool = False) -> tuple[bool, str]:
    """2ª etapa: a farmácia confirmou com a senha. Grava o recebimento da caixa.

    Devolve (True, "") quando recebida. Se a farmácia marcou que a caixa não
    chegou, ou se a contagem mudou desde a bipagem, a caixa é bloqueada para
    conferência e devolve (False, motivo) — o alerta é criado por quem chamou,
    depois do commit.
    """
    caixa = dict(_caixa(id_caixa))
    marcador = f"[{caixa['id_caixa']}]"
    itens = [dict(r) for r in conn.execute(
        f"SELECT id_unidade, xProd, status FROM unidades WHERE id_caixa = ? AND status IN ({','.join('?' for _ in NA_CAIXA)})",
        (caixa["id_caixa"], *NA_CAIXA)).fetchall()]
    motivo = ""
    if nao_recebida:
        motivo = "Caixa bipada como devolvida pela sala, mas não recebida pela farmácia."
    elif len(itens) != informado:
        motivo = (f"Contagem mudou entre a bipagem e a confirmação: informado {informado}, "
                  f"no sistema {len(itens)}.")
    if motivo:
        bloquear(conn, caixa=caixa, id_atendimento=id_atendimento, motivo=motivo,
                 usuario=responsavel["username"])
        db.registrar_evento(
            conn, tipo="devolucao_caixa_divergente", id_atendimento=id_atendimento,
            usuario=responsavel["username"], motivo=motivo,
            devolvido_por=devolvido_por, recebido_por=responsavel["nome"],
            observacao=f"{marcador} conferida por {responsavel['nome']}; bipada por {bipado_por}")
        return False, motivo

    for item in itens:
        farm = conn.execute("SELECT farmacia FROM unidades WHERE id_unidade = ?", (item["id_unidade"],)).fetchone()
        volta = estoque_de_volta(farm[0] if farm else "")
        if item["status"] not in (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA):
            # Caixa tinha sido dispensada para a sala: volta ao estoque (da farmácia).
            conn.execute("""UPDATE unidades SET status = ?, id_atendimento = NULL, atualizado_em = ?,
                            atualizado_por = ? WHERE id_unidade = ?""",
                         (volta, db.agora(), responsavel["username"], item["id_unidade"]))
        db.registrar_evento(
            conn, tipo="devolver_nao_utilizado", id_unidade=item["id_unidade"],
            id_atendimento=id_atendimento, status_anterior=item["status"],
            status_novo=volta, usuario=bipado_por,
            devolvido_por=devolvido_por, recebido_por=responsavel["nome"],
            observacao=f"{marcador} devolvido na caixa, pela contagem")
        db.registrar_evento(
            conn, tipo="confirmar_devolver_nao_utilizado", id_unidade=item["id_unidade"],
            id_atendimento=id_atendimento, usuario=responsavel["username"],
            devolvido_por=devolvido_por, recebido_por=responsavel["nome"],
            observacao=f"{marcador} recebimento confirmado com a senha de {responsavel['nome']}")
    db.registrar_evento(
        conn, tipo="devolver_caixa", id_atendimento=id_atendimento, usuario=bipado_por,
        devolvido_por=devolvido_por, recebido_por=responsavel["nome"],
        motivo=f"{informado} item(ns) na caixa, contagem confere",
        observacao=f"{marcador} recebida por {responsavel['nome']}")
    return True, ""


def conferir(id_caixa: str, usuario: str, motivo: str, faltantes: list[str]) -> tuple[bool, str]:
    """A farmácia confere a caixa e libera. Itens marcados como faltantes saem da
    caixa e vão para divergência (com o motivo)."""
    caixa = _caixa(id_caixa)
    if not caixa:
        return False, "Caixa não encontrada."
    motivo = texto(motivo)
    if len(motivo) < 5:
        return False, "Descreva o que foi conferido — fica registrado."
    faltantes = [texto(f) for f in faltantes if texto(f)]
    with db.transacao() as conn:
        for id_unidade in faltantes:
            linha = conn.execute("SELECT status, id_caixa FROM unidades WHERE id_unidade = ?",
                                 (id_unidade,)).fetchone()
            if not linha or texto(linha["id_caixa"]).upper() != caixa["id_caixa"].upper():
                continue
            caixas._registrar_saida(conn, id_unidade, usuario, caixas.SAIDA_RETIRADA,
                                    "não encontrado na conferência")
            conn.execute("UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ? "
                         "WHERE id_unidade = ?", (DIVERGENCIA, db.agora(), usuario, id_unidade))
            db.registrar_evento(conn, tipo="marcar_divergencia", id_unidade=id_unidade,
                                status_anterior=linha["status"], status_novo=DIVERGENCIA,
                                usuario=usuario, motivo=f"Não encontrado na conferência da caixa: {motivo}",
                                observacao=f"[{caixa['id_caixa']}]")
        conn.execute(
            """UPDATE caixas SET bloqueada = 0, bloqueio_motivo = NULL, bloqueio_atendimento = NULL,
                                 bloqueada_em = NULL, bloqueada_por = NULL, atualizado_em = ?,
                                 atualizado_por = ? WHERE id_caixa = ?""",
            (db.agora(), usuario, caixa["id_caixa"]))
        from . import caixas_sala
        caixas_sala.liberar_pendencias_da_caixa(conn, caixa["id_caixa"])
        db.registrar_evento(conn, tipo="conferir_caixa", usuario=usuario, motivo=motivo,
                            id_atendimento=caixa["bloqueio_atendimento"],
                            observacao=f"[{caixa['id_caixa']}] liberada; {len(faltantes)} item(ns) em divergência")
    return True, (f"Caixa {caixa['id_caixa']} conferida e liberada."
                  + (f" {len(faltantes)} item(ns) foram para divergência." if faltantes else ""))


def recolocar_apos_correcao(conn, id_unidade: str, usuario: str) -> None:
    """Bip de uso excluído/desfeito: o item volta para a caixa de onde saiu no uso."""
    ultima = conn.execute(
        """SELECT ci.id_caixa, ci.motivo_saida, c.encerrada_em FROM caixa_itens ci
           JOIN caixas c ON c.id_caixa = ci.id_caixa
           WHERE ci.id_unidade = ? ORDER BY ci.rowid DESC LIMIT 1""", (id_unidade,)).fetchone()
    if not ultima or texto(ultima["motivo_saida"]) != caixas.SAIDA_USO or ultima["encerrada_em"]:
        return
    from . import caixas_sala
    caixas_sala.desmarcar_uso(conn, id_unidade)
    conn.execute("UPDATE unidades SET id_caixa = ? WHERE id_unidade = ?", (ultima["id_caixa"], id_unidade))
    agora = db.agora()
    inseriu = conn.execute(
        "INSERT OR IGNORE INTO caixa_itens (id_caixa, id_unidade, entrou_em, entrou_por) VALUES (?,?,?,?)",
        (ultima["id_caixa"], id_unidade, agora, usuario)).rowcount
    if not inseriu:
        # Entrou e saiu no mesmo segundo: reabre a mesma linha em vez de duplicar.
        conn.execute(
            """UPDATE caixa_itens SET saiu_em = NULL, saiu_por = NULL, motivo_saida = NULL
               WHERE id_caixa = ? AND id_unidade = ? AND entrou_em = ?""",
            (ultima["id_caixa"], id_unidade, agora))
    db.registrar_evento(conn, tipo="entrar_caixa", id_unidade=id_unidade, usuario=usuario,
                        motivo=f"Voltou para a caixa {ultima['id_caixa']} (bip de uso corrigido)",
                        observacao=f"[{ultima['id_caixa']}]")


def iguais_livres(id_unidade: str, limite: int) -> list[str]:
    """v18.12 ("Unidades por bip" na caixa): outras unidades do MESMO material, lote,
    validade e estoque da unidade dada, fora de caixa e dentro da validade."""
    from .. import gs1
    u = db.consultar_um("SELECT * FROM unidades WHERE id_unidade = ?", (texto(id_unidade),))
    if not u or limite <= 0:
        return []
    linhas = db.consultar(
        """SELECT id_unidade, nLote FROM unidades
           WHERE id_unidade <> ? AND status = ? AND COALESCE(farmacia, '') = ?
             AND COALESCE(id_caixa, '') = '' AND COALESCE(codigo_aghu, '') = ?
             AND gtin(codigo_barras) = gtin(?) AND substr(COALESCE(dVal, ''), 1, 10) = ?
             AND (dVal IS NULL OR dVal = '' OR substr(dVal, 1, 10) >= date('now'))
           ORDER BY criado_em""",
        (u["id_unidade"], u["status"], texto(u.get("farmacia")), texto(u.get("codigo_aghu")),
         texto(u.get("codigo_barras")), texto(u.get("dVal"))[:10]))
    lote = gs1.lote_normalizado(u.get("nLote"))
    return [l["id_unidade"] for l in linhas if gs1.lote_normalizado(l["nLote"]) == lote][:limite]


def _st(so_almoxarifado: bool) -> str:
    """v18.11.4: caixa no almoxarifado ← estoque do almoxarifado; caixa na farmácia ←
    SÓ o estoque daquela farmácia (o material unitário chega antes, depois monta/repõe)."""
    return EM_ESTOQUE_RECEBIMENTO if so_almoxarifado else EM_ESTOQUE_FARMACIA


def candidatos_para_caixa(codigo: str, so_almoxarifado: bool = False, farmacia: str = "") -> list[dict]:
    """Material solto em estoque que pode entrar na caixa, pelo código bipado.

    Aceita código de barras, nº de série, ID da unidade ou o CÓDIGO AGHU digitado.
    Devolve um grupo por material/lote/validade (com a quantidade disponível e a
    unidade de validade mais curta), para a tela pedir a escolha quando há mais
    de um lote — em vez de o sistema escolher sozinho.
    """
    from .. import gs1
    from ..utils import normalizar_codigo
    etiqueta = busca.interpretar(codigo)
    bipado = texto(codigo)          # v18.43.2: o texto como veio do leitor
    codigo = normalizar_codigo(codigo)
    if not codigo:
        return []
    linhas = db.consultar(
        """SELECT id_unidade, codigo_aghu, xProd, descritivo_hospital, nLote, dVal,
                  marca_fabricante, fornecedor, farmacia
           FROM unidades
           WHERE status IN (?, ?) AND (id_caixa IS NULL OR id_caixa = '')
             AND (UPPER(id_unidade) = UPPER(?) OR gtin(codigo_barras) = gtin(?)
                  OR (numero_serie IS NOT NULL AND numero_serie <> ''
                      AND REPLACE(numero_serie, ' ', '') = ?)
                  OR UPPER(codigo_aghu) = UPPER(?))
           ORDER BY CASE WHEN dVal IS NULL OR dVal = '' THEN 1 ELSE 0 END, dVal, criado_em""",
        (_st(so_almoxarifado), _st(so_almoxarifado), codigo, codigo, codigo, codigo))
    if not linhas:
        # v17: etiqueta secundária (só validade/lote, sem GTIN): acha pelo lote.
        cond, extra = gs1.sql_por_lote(etiqueta)
        if cond:
            linhas = db.consultar(
                f"""SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.descritivo_hospital, u.nLote,
                           u.dVal, u.marca_fabricante, u.fornecedor, u.farmacia
                    FROM unidades u
                    WHERE u.status IN (?, ?) AND (u.id_caixa IS NULL OR u.id_caixa = '') AND {cond}
                    ORDER BY CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END, u.dVal,
                             u.criado_em""", (_st(so_almoxarifado), _st(so_almoxarifado), *extra))
    linhas = [dict(l) for l in linhas]
    if not so_almoxarifado and texto(farmacia):
        linhas = [l for l in linhas if texto(l.get("farmacia")) == texto(farmacia)]
    # v18.43.2: o texto bipado inteiro é o código (ver remessas).
    linhas = busca.preferir_exatos(linhas, bipado)
    linhas, aviso_lote = gs1.filtrar(linhas, etiqueta)
    # v18.11.3: lote da etiqueta que não existe no estoque — a tela mostra os outros
    # lotes em vermelho e a pessoa escolhe; o sistema NUNCA coloca outro lote sozinho.
    lote_lido = texto((etiqueta or {}).get("lote")) if aviso_lote else ""
    grupos: dict[tuple, dict] = {}
    for l in linhas:
        chave = (texto(l["codigo_aghu"]).upper(), texto(l["xProd"]).upper(),
                 gs1.lote_normalizado(l["nLote"]), texto(l["dVal"])[:10])
        if chave not in grupos:
            grupos[chave] = dict(l) | {"quantidade": 0, "lote_nao_encontrado": lote_lido}
        grupos[chave]["quantidade"] += 1
    return list(grupos.values())


def resumo_conteudo(id_caixa: str) -> list[dict]:
    """Conteúdo agrupado por material e lote — é o que se confere de olho."""
    return db.consultar(
        """SELECT codigo_aghu, COALESCE(NULLIF(descritivo_hospital,''), xProd) AS produto,
                  nLote, dVal, COUNT(*) AS quantidade
           FROM unidades WHERE UPPER(id_caixa) = UPPER(?) AND status IN (?, ?)
           GROUP BY codigo_aghu, produto, nLote, dVal ORDER BY produto, nLote""",
        (texto(id_caixa), EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA))


def situacao_no_momento(id_caixa: str, id_evento: int = 0) -> dict | None:
    """Conteúdo da caixa no instante de um evento (ex.: uma devolução) e agora.

    "No momento" = itens que tinham entrado e ainda não tinham saído da caixa na
    hora do evento. Para uma devolução, lista também o que foi devolvido nela.
    """
    caixa = buscar(id_caixa)
    if not caixa:
        return None
    evento = db.consultar_um(
        """SELECT e.*, a.prontuario, a.paciente, a.sala, a.unidade FROM eventos e
           LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
           WHERE e.id_evento = ?""", (int(id_evento or 0),)) if id_evento else None
    momento = evento["data_evento"] if evento else None
    naquele = []
    devolvidos = []
    if momento:
        naquele = db.consultar(
            """SELECT u.id_unidade, u.codigo_aghu, COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS produto,
                      u.nLote, u.dVal, u.status, ci.entrou_em, ci.saiu_em, ci.motivo_saida
               FROM caixa_itens ci JOIN unidades u ON u.id_unidade = ci.id_unidade
               WHERE ci.id_caixa = ? AND ci.entrou_em <= ?
                 AND (ci.saiu_em IS NULL OR ci.saiu_em > ?)
               ORDER BY produto, u.nLote""", (caixa["id_caixa"], momento, momento))
        if evento["tipo"] in ("devolver_caixa", "devolucao_caixa_divergente") and evento["id_atendimento"]:
            devolvidos = db.consultar(
                """SELECT u.id_unidade, u.codigo_aghu, COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS produto,
                          u.nLote, u.dVal
                   FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
                   WHERE e.tipo = 'devolver_nao_utilizado' AND e.id_atendimento = ?
                     AND e.observacao LIKE ? ORDER BY produto""",
                (evento["id_atendimento"], f"%[{caixa['id_caixa']}]%"))
    usados = db.consultar(
        """SELECT u.id_unidade, u.codigo_aghu, COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS produto,
                  u.nLote, ci.saiu_em, a.prontuario, a.sala
           FROM caixa_itens ci JOIN unidades u ON u.id_unidade = ci.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE ci.id_caixa = ? AND ci.motivo_saida = 'uso'
             AND (? IS NULL OR u.id_atendimento = ?)
           ORDER BY ci.saiu_em""",
        (caixa["id_caixa"], evento["id_atendimento"] if evento else None,
         evento["id_atendimento"] if evento else None)) if evento and evento["id_atendimento"] else []
    from . import caixas as _c
    return {
        "caixa": caixa, "evento": evento,
        "naquele": naquele, "devolvidos": devolvidos, "usados_no_atendimento": usados,
        "agora": resumo_conteudo(caixa["id_caixa"]),
        "historico": db.consultar(
            """SELECT e.id_evento, e.tipo, e.data_evento, e.usuario, e.motivo, e.observacao,
                      a.prontuario, a.sala
               FROM eventos e LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
               WHERE e.id_unidade IS NULL AND e.observacao LIKE ?
               ORDER BY e.id_evento DESC LIMIT 50""", (f"%[{caixa['id_caixa']}]%",)),
    }
