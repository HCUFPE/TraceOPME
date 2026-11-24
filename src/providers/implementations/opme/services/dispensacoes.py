"""v17 — dispensação do OPME da farmácia para a sala, por paciente.

1. A FARMÁCIA abre o atendimento do paciente e bipa o que separou (item a item,
   ou o código da caixa de consignado). Cada bip é a SAÍDA da farmácia: o item
   fica "Dispensado — aguardando a sala", reservado para aquele paciente.
2. A SALA confere e confirma o recebimento com o próprio usuário (logado) — não
   precisa bipar o material de novo. Os itens passam para "Na sala".

Na sala, o uso dá preferência ao que foi dispensado para o paciente. O que
sobrar volta pela devolução de sempre (a sala bipa, a farmácia confirma).
Se a sala usar algo que não foi dispensado, o próprio registro de uso grava a
saída (`saida_sem_dispensacao`) e a farmácia vê isso no painel.
"""

from .. import busca, db, gs1, log
from ..config import rotulo_farmacia
from ..erros import ErroDeNegocio
from ..domain import (DIVERGENCIA, NAO_RECEBIDO, estoque_de_volta, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, EM_SALA, ESTOQUE_LIVRE, OPERACOES,
                      SQL_ESTOQUE_DE_VOLTA, TRANSITO_SALA, UTILIZADO)
from ..utils import data_br, gerar_id, hoje_iso, inteiro, normalizar_codigo, texto
from . import caixas, caixas_consignado, usuarios

OPERACAO = "dispensar_sala"
PAPEIS_QUE_RECEBEM = ("sala-procedimento", "supervisao", "admin")


# ---------------------------------------------------------------- consultas

def pendente_do_atendimento(id_atendimento: str) -> dict | None:
    return db.consultar_um(
        "SELECT * FROM dispensacoes WHERE id_atendimento = ? AND status = 'pendente' "
        "ORDER BY criado_em DESC LIMIT 1", (texto(id_atendimento),))


def ultima_do_atendimento(id_atendimento: str) -> dict | None:
    """A dispensação em andamento; sem ela, a mais recente que tenha material."""
    return pendente_do_atendimento(id_atendimento) or db.consultar_um(
        """SELECT d.* FROM dispensacoes d WHERE d.id_atendimento = ?
             AND EXISTS (SELECT 1 FROM dispensacao_itens i WHERE i.id_dispensacao = d.id_dispensacao
                           AND i.situacao <> 'removido')
           ORDER BY d.criado_em DESC LIMIT 1""", (texto(id_atendimento),))


def itens(id_dispensacao: str, so_pendentes: bool = False) -> list[dict]:
    filtro = "AND i.situacao = 'pendente'" if so_pendentes else "AND i.situacao <> 'removido'"
    return db.consultar(
        f"""SELECT i.*, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                   u.status AS status_unidade
            FROM dispensacao_itens i LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
            WHERE i.id_dispensacao = ? {filtro} ORDER BY i.id_item""", (texto(id_dispensacao),))


def pendentes_do_atendimento(id_atendimento: str) -> list[dict]:
    disp = pendente_do_atendimento(id_atendimento)
    return itens(disp["id_dispensacao"], so_pendentes=True) if disp else []


def buscar(id_dispensacao: str) -> dict | None:
    disp = db.consultar_um(
        """SELECT d.*, a.prontuario, a.paciente, a.sala, a.unidade, a.status AS status_atendimento
           FROM dispensacoes d LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.id_dispensacao = ?""", (texto(id_dispensacao),))
    if not disp:
        return None
    disp = dict(disp)
    disp["itens"] = itens(disp["id_dispensacao"])
    disp["pendentes"] = [i for i in disp["itens"] if i["situacao"] == "pendente"]
    return disp


def do_atendimento(id_atendimento: str) -> list[dict]:
    """Tudo que a farmácia dispensou para este paciente, com a situação atual."""
    return db.consultar(
        """SELECT i.*, d.status AS status_dispensacao, d.recebido_por, d.confirmada_em,
                  u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                  u.status AS status_unidade, u.id_atendimento AS atendimento_atual
           FROM dispensacao_itens i
           JOIN dispensacoes d ON d.id_dispensacao = i.id_dispensacao
           LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
           WHERE d.id_atendimento = ? AND i.situacao <> 'removido'
           ORDER BY i.id_item""", (texto(id_atendimento),))


def listar_pendentes() -> list[dict]:
    return db.consultar(
        """SELECT d.*, a.prontuario, a.paciente, a.sala, a.unidade, a.data_procedimento,
                  (SELECT COUNT(*) FROM dispensacao_itens i WHERE i.id_dispensacao = d.id_dispensacao
                     AND i.situacao = 'pendente') AS qtd
           FROM dispensacoes d LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.status = 'pendente' AND EXISTS (SELECT 1 FROM dispensacao_itens i
                 WHERE i.id_dispensacao = d.id_dispensacao AND i.situacao = 'pendente')
           ORDER BY d.criado_em""")


def recentes_confirmadas(limite: int = 20) -> list[dict]:
    return db.consultar(
        """SELECT d.*, a.prontuario, a.sala, a.unidade,
                  (SELECT COUNT(*) FROM dispensacao_itens i WHERE i.id_dispensacao = d.id_dispensacao
                     AND i.situacao = 'recebido') AS qtd
           FROM dispensacoes d LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.status = 'confirmada' ORDER BY d.confirmada_em DESC LIMIT ?""", (limite,))


def _resumo(id_dispensacao: str) -> dict:
    from ..utils import data_hora_br
    pend = itens(id_dispensacao, so_pendentes=True)
    lista = [{"id_item": i["id_item"], "tipo": "item", "id_caixa": i["id_caixa"] or "",
              "descricao": i["descritivo_hospital"] or i["xProd"] or "", "lote": i["nLote"] or "",
              "aghu": i["codigo_aghu"] or "", "validade": data_br(i["dVal"]) or "",
              "quando": data_hora_br(i["bipado_em"]), "por": i["bipado_por"] or "",
              "remover": f"/dispensacoes/item/{i['id_item']}/remover"} for i in pend]
    return {"id": id_dispensacao, "itens": len(pend),
            "caixas": len({i["id_caixa"] for i in pend if i["id_caixa"]}), "lista": lista}


# ---------------------------------------------------------------- 1ª etapa: farmácia bipa

def _abrir_ou_pegar(conn, id_atendimento: str, usuario: str) -> str:
    linha = conn.execute(
        "SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento = ? AND status = 'pendente' "
        "ORDER BY criado_em DESC LIMIT 1", (id_atendimento,)).fetchone()
    if linha:
        return linha[0]
    novo = gerar_id("DS")
    conn.execute("""INSERT INTO dispensacoes (id_dispensacao, id_atendimento, status, criado_por, criado_em)
                    VALUES (?,?,'pendente',?,?)""", (novo, id_atendimento, usuario, db.agora()))
    return novo


def _registrar(conn, id_dispensacao, unidade_id, id_atendimento, usuario, id_caixa="", obs=""):
    antes = conn.execute("SELECT status FROM unidades WHERE id_unidade = ?", (unidade_id,)).fetchone()
    conn.execute(
        """UPDATE unidades SET status = ?, id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
           WHERE id_unidade = ?""", (TRANSITO_SALA, id_atendimento, db.agora(), usuario, unidade_id))
    conn.execute(
        """INSERT INTO dispensacao_itens (id_dispensacao, id_unidade, id_caixa, bipado_por, bipado_em)
           VALUES (?,?,?,?,?)""", (id_dispensacao, unidade_id, id_caixa or None, usuario, db.agora()))
    db.registrar_evento(
        conn, tipo=OPERACAO, id_unidade=unidade_id, id_atendimento=id_atendimento,
        status_anterior=antes[0] if antes else EM_ESTOQUE_FARMACIA, status_novo=TRANSITO_SALA, usuario=usuario,
        observacao=(f"[{id_caixa}] " if id_caixa else "") + (obs or "Saída da farmácia para a sala; "
                                                             "aguardando a ciência da sala"))


class _PedeCienciaValidade(ErroDeNegocio):
    """Interrompe a transação da dispensa (nada gravado) para pedir a ciência.

    É um `ErroDeNegocio` para a transação desfazer sem registrar erro técnico."""

    def __init__(self, resposta: dict):
        super().__init__(resposta.get("mensagem", ""))
        self.resposta = resposta


def bipar(*, codigo: str, id_atendimento: str, usuario: str, id_unidade: str = "", farmacia: str = "",
          ciencia_validade: bool = False) -> dict:
    """A farmácia bipa um item (ou uma caixa) para o paciente. Formato de `fluxo.bipar`."""
    from .fluxo import (CAMPOS_ITEM, ErroDeFluxo, EscolhaNecessaria, _selecionar, alertas_do_item,
                        formatar_item)

    op = OPERACOES[OPERACAO]
    codigo_lido = codigo
    etiqueta = busca.interpretar(codigo)
    bipado = texto(codigo)          # v18.43.2: o texto como veio do leitor
    codigo = normalizar_codigo(codigo)
    id_atendimento = texto(id_atendimento)
    if not codigo:
        return {"ok": False, "mensagem": "Bipe ou digite um código."}
    atendimento = db.consultar_um("SELECT status, prontuario FROM atendimentos WHERE id_atendimento = ?",
                                  (id_atendimento,))
    if not atendimento:
        return {"ok": False, "mensagem": "Selecione o atendimento (paciente) antes de bipar."}
    if texto(atendimento["status"]) != "aberto":
        return {"ok": False, "mensagem": "Este atendimento está encerrado ou cancelado — não recebe dispensação."}
    aviso = "Aguardando a sala dar ciência do recebimento."

    # Caixa de consignado: vai inteira, com tudo que está dentro.
    if caixas.e_codigo_caixa(codigo):
        caixa = caixas_consignado.buscar(codigo)
        if not caixa:
            return {"ok": False, "mensagem": f"Caixa {codigo} não encontrada."}
        if caixa.get("encerrada_em"):
            return {"ok": False, "mensagem": "Esta caixa foi encerrada."}
        from . import caixas_sala
        turno = caixas_sala.ativo_da_caixa(caixa["id_caixa"])
        if turno:
            return {"ok": False, "mensagem": (f"A caixa {caixa['id_caixa']} está na {turno['local']} pelo dia "
                                              f"({turno['status_rotulo']}). Não precisa dispensar para o paciente: "
                                              f"a sala bipa a caixa e o item no Registrar uso.")}
        if caixas_consignado.bloqueada_para(caixa["id_caixa"], id_atendimento):
            return {"ok": False, "mensagem": (f"A caixa {caixa['id_caixa']} está BLOQUEADA para "
                                              f"conferência. Confira e libere antes de dispensar.")}
        # v18.4.1: lido e gravado na MESMA transação (duas dispensações ao mesmo
        # tempo não levam a mesma caixa), e caixa com lote em recall não sai.
        from . import recall
        with db.transacao() as conn:
            dentro = [dict(r) for r in conn.execute(
                "SELECT id_unidade, xProd, status, nLote, codigo_aghu FROM unidades WHERE id_caixa = ?",
                (caixa["id_caixa"],)).fetchall()]
            livres = [u for u in dentro if u["status"] in ESTOQUE_LIVRE]
            if not livres:
                ja = [u for u in dentro if u["status"] in (TRANSITO_SALA, EM_SALA)]
                return {"ok": False, "mensagem": ("Esta caixa já foi dispensada para a sala." if ja
                                                  else "A caixa está vazia no sistema.")}
            dados = [dict(r) for r in conn.execute(
                "SELECT id_unidade, nLote, codigo_aghu, dVal FROM unidades WHERE id_caixa = ?", (caixa["id_caixa"],))]
            vencidos = [d for d in dados if d["id_unidade"] in {u["id_unidade"] for u in livres}
                        and texto(d.get("dVal")) and texto(d["dVal"])[:10] < hoje_iso()]
            if vencidos:
                return {"ok": False, "mensagem": (f"A caixa {caixa['id_caixa']} tem {len(vencidos)} item(ns) VENCIDO(S) "
                                                  f"(lote {vencidos[0]['nLote'] or '—'}). Tire da caixa antes de dispensar.")}
            travadas = recall.bloqueadas(livres, conn)
            if travadas:
                u, b = travadas[0]
                return {"ok": False, "mensagem": (f"A caixa {caixa['id_caixa']} tem material de lote em RECALL. "
                                                  + recall.mensagem_bloqueio(u, b)
                                                  + " Tire o item da caixa antes de dispensar.")}
            id_disp = _abrir_ou_pegar(conn, id_atendimento, usuario)
            for u in livres:
                _registrar(conn, id_disp, u["id_unidade"], id_atendimento, usuario, caixa["id_caixa"],
                           "Saída da farmácia na caixa; aguardando a ciência da sala")
        return {"ok": True, "pendente": True, "itens": [dict(u) for u in livres],
                "caixa": {"id_caixa": caixa["id_caixa"], "nome": caixa["nome"], "total": len(livres)},
                "devolucao": _resumo(id_disp),
                "mensagem": f"Caixa {caixa['id_caixa']} dispensada ({len(livres)} item(ns)). {aviso}",
                "alertas": []}

    try:
        with db.transacao() as conn:
            candidatas = [dict(r) for r in conn.execute(
                f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
                    FROM unidades u LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                    WHERE UPPER(u.id_unidade) = UPPER(?) OR gtin(u.codigo_barras) = gtin(?)
                       OR (u.numero_serie IS NOT NULL AND u.numero_serie <> ''
                           AND REPLACE(u.numero_serie, ' ', '') = ?)
                    ORDER BY CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                             u.dVal, u.criado_em""", (codigo, codigo, codigo)).fetchall()]
            if not candidatas:
                cond, extra = gs1.sql_por_lote(etiqueta)
                if cond:
                    candidatas = [dict(r) for r in conn.execute(
                        f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
                            FROM unidades u LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                            WHERE {cond}
                            ORDER BY CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                                     u.dVal, u.criado_em""", extra).fetchall()]
            # v18.43.2: o texto bipado inteiro é o código — se alguma unidade tem
            # exatamente ele, a busca é essa e não abre a lista de lotes do produto.
            candidatas = busca.preferir_exatos(candidatas, bipado)
            candidatas, aviso_etiqueta = gs1.filtrar(candidatas, etiqueta)
            if aviso_etiqueta and not texto(id_unidade):   # v18.12: não troca o lote sozinho
                from .fluxo import resposta_lote_nao_encontrado
                pede = resposta_lote_nao_encontrado(candidatas, etiqueta, op)
                if pede:
                    return pede
            if candidatas:
                ids = [c["id_unidade"] for c in candidatas]
                aguardando = {r[0] for r in conn.execute(
                    f"""SELECT i.id_unidade FROM devolucao_itens i JOIN devolucoes d
                        ON d.id_devolucao = i.id_devolucao WHERE i.situacao = 'pendente'
                        AND d.status = 'pendente' AND i.id_unidade IN ({','.join('?' for _ in ids)})""",
                    ids).fetchall()}
                candidatas = [c for c in candidatas if c["id_unidade"] not in aguardando] or candidatas
            unidade = _selecionar(op, candidatas, id_atendimento, farmacia, id_unidade)
            # nov/2026: lote com validade mais próxima na mesma farmácia → aviso com
            # ciência (não trava). Nada é gravado até a ciência. Ver `validade_aviso`.
            from . import validade_aviso
            onde_aviso = f"no estoque da {rotulo_farmacia(unidade.get('farmacia'))}"
            anterior = None
            if unidade.get("status") == EM_ESTOQUE_FARMACIA:
                anterior = validade_aviso.lote_com_validade_anterior(
                    unidade, estoque=EM_ESTOQUE_FARMACIA, farmacia=unidade.get("farmacia") or "", conn=conn)
            if anterior and not ciencia_validade:
                raise _PedeCienciaValidade(validade_aviso.resposta_aviso(unidade, anterior, onde_aviso))
            id_disp = _abrir_ou_pegar(conn, id_atendimento, usuario)
            if anterior:
                validade_aviso.registrar_ciencia(conn, unidade, anterior, usuario, onde_aviso, id_atendimento)
            _registrar(conn, id_disp, unidade["id_unidade"], id_atendimento, usuario)
    except _PedeCienciaValidade as pedido:
        return pedido.resposta | {"codigo": codigo_lido}
    except EscolhaNecessaria as ambiguo:
        return {"ok": False, "escolha": True,
                "mensagem": "Mais de um item responde a este código — escolha qual é.",
                "opcoes": [formatar_item(c) for c in ambiguo.candidatas]}
    except ErroDeFluxo as recusa:
        log.info(f"dispensação recusada · codigo={codigo} · {recusa}", usuario)
        return {"ok": False, "mensagem": str(recusa)}

    item = dict(unidade) | {"status": TRANSITO_SALA}
    return {"ok": True, "pendente": True, "item": formatar_item(item),
            "devolucao": _resumo(id_disp),
            "mensagem": f"{unidade.get('xProd')} dispensado para a sala. {aviso}",
            "alertas": alertas_do_item(unidade) + ([aviso_etiqueta] if aviso_etiqueta else [])}


def remover_item(id_item: int, usuario: str) -> tuple[bool, str, str]:
    """Tira da dispensação pendente (bipado por engano). Caixa sai inteira."""
    linha = db.consultar_um(
        """SELECT i.*, d.id_atendimento, d.status AS status_disp FROM dispensacao_itens i
           JOIN dispensacoes d ON d.id_dispensacao = i.id_dispensacao WHERE i.id_item = ?""",
        (inteiro(id_item, 0),))
    if not linha or linha["situacao"] != "pendente" or linha["status_disp"] != "pendente":
        return False, "Este item não está mais pendente nesta dispensação.", ""
    with db.transacao() as conn:
        if linha["id_caixa"]:
            alvo = [dict(r) for r in conn.execute(
                "SELECT * FROM dispensacao_itens WHERE id_dispensacao = ? AND id_caixa = ? AND situacao = 'pendente'",
                (linha["id_dispensacao"], linha["id_caixa"])).fetchall()]
        else:
            alvo = [dict(linha)]
        for i in alvo:
            st = conn.execute("SELECT status FROM unidades WHERE id_unidade = ?", (i["id_unidade"],)).fetchone()
            if st and st[0] == TRANSITO_SALA:
                conn.execute(f"""UPDATE unidades SET status = {SQL_ESTOQUE_DE_VOLTA}, id_atendimento = NULL,
                                atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?""",
                             (db.agora(), usuario, i["id_unidade"]))
                db.registrar_evento(
                    conn, tipo="remover_da_dispensacao", id_unidade=i["id_unidade"],
                    id_atendimento=linha["id_atendimento"], status_anterior=TRANSITO_SALA,
                    status_novo=conn.execute("SELECT status FROM unidades WHERE id_unidade = ?",
                                             (i["id_unidade"],)).fetchone()[0], usuario=usuario,
                    observacao=(f"[{i['id_caixa']}] " if i["id_caixa"] else "")
                               + "Tirado da dispensação antes da ciência da sala; voltou ao estoque")
            conn.execute("""UPDATE dispensacao_itens SET situacao = 'removido', resolvido_em = ?,
                            resolvido_por = ? WHERE id_item = ?""", (db.agora(), usuario, i["id_item"]))
        if linha["id_caixa"]:
            # A caixa acompanha os itens: sem isto ela ficava "dispensada" sozinha.
            conn.execute("""UPDATE caixas SET status = ?, id_atendimento = NULL, atualizado_em = ?,
                            atualizado_por = ? WHERE UPPER(id_caixa) = UPPER(?) AND status = ?""",
                         (EM_ESTOQUE_FARMACIA, db.agora(), usuario, linha["id_caixa"], TRANSITO_SALA))
    return True, ("Caixa tirada da dispensação." if linha["id_caixa"] else "Item tirado da dispensação."), \
        linha["id_atendimento"]


def marcar_removido_por_desfazer(conn, id_unidade: str) -> None:
    """O operador desfez o bip de dispensação na própria tela."""
    conn.execute("""UPDATE dispensacao_itens SET situacao = 'removido', resolvido_em = ?
                    WHERE id_unidade = ? AND situacao = 'pendente'""", (db.agora(), id_unidade))


# ---------------------------------------------------------------- 2ª etapa: senha da sala

def identificar(id_dispensacao: str, codigo: str) -> dict:
    """Conferência bipando: que itens pendentes desta dispensação respondem ao código."""
    bruto = texto(codigo)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    lido = {bruto.upper(), texto(normalizar_codigo(bruto)).upper()}
    etiqueta = busca.interpretar(bruto)
    cand = []
    for i in db.consultar(
            """SELECT i.id_item, i.id_caixa, u.id_unidade, u.codigo_barras, u.numero_serie, u.nLote
               FROM dispensacao_itens i JOIN unidades u ON u.id_unidade = i.id_unidade
               WHERE i.id_dispensacao = ? AND i.situacao = 'pendente' ORDER BY i.id_item""",
            (texto(id_dispensacao),)):
        cods = {texto(i["codigo_barras"]).upper(), texto(normalizar_codigo(i["codigo_barras"] or "")).upper(),
                texto(i["numero_serie"]).upper(), texto(i["id_unidade"]).upper(),
                texto(i["id_caixa"]).upper()} - {""}
        if cods & lido:
            cand.append(i)
    if etiqueta and etiqueta.get("lote") and cand:
        do_lote = [i for i in cand if gs1._confere(i["nLote"], etiqueta["lote"], etiqueta.get("lote_ate_o_fim"))]
        cand = do_lote or cand
    if not cand:
        return {"ok": False, "mensagem": f"O código {bruto} não está nesta dispensação."}
    caixa = cand[0]["id_caixa"] if texto(cand[0]["id_caixa"]).upper() in lido else ""
    return {"ok": True, "itens": [i["id_item"] for i in cand], "caixa": bool(caixa)}


def confirmar(*, id_dispensacao: str, usuario_sala: str = "", senha: str = "",
              recebidos: set | None = None, modo: str = "lista",
              logado: dict | None = None) -> tuple[bool, str]:
    """O operador da sala confere (pela lista ou bipando) e confirma com a própria
    senha. `recebidos` = itens que chegaram; sem ele, tudo chegou. O que não
    chegou volta ao estoque da farmácia, com o registro de que a sala não recebeu."""
    disp = db.consultar_um("SELECT * FROM dispensacoes WHERE id_dispensacao = ?", (texto(id_dispensacao),))
    if not disp:
        return False, "Dispensação não encontrada."
    if disp["status"] != "pendente":
        return False, "Esta dispensação já foi confirmada."
    pend = itens(disp["id_dispensacao"], so_pendentes=True)
    if not pend:
        return False, "Não há nada pendente nesta dispensação."
    if logado:
        # A ciência é de quem está logado: basta clicar em "Dar ciência".
        quem = logado
    else:
        if not texto(usuario_sala) or not senha:
            return False, "O operador da sala precisa escolher o próprio nome e digitar a senha."
        ok_login, quem = usuarios.autenticar(usuario_sala, senha)
        if not ok_login:
            return False, quem
    if quem["papel"] not in PAPEIS_QUE_RECEBEM:
        return False, f"{quem['nome']} não é da sala de procedimento e não pode confirmar o recebimento."

    if recebidos is not None:
        recebidos = {inteiro(x, 0) for x in recebidos}
        # Caixa de consignado anda inteira: se faltou um item dela, a caixa toda não chegou.
        caixas_faltando = {i["id_caixa"] for i in pend if i["id_caixa"] and i["id_item"] not in recebidos}
        chegou = [i for i in pend if i["id_item"] in recebidos and i["id_caixa"] not in caixas_faltando]
        faltou = [i for i in pend if i not in chegou]
    else:
        chegou, faltou = pend, []
    if not chegou:
        return False, ("Nenhum item marcado como recebido. Se nada chegou, fale com a farmácia; "
                       "se o procedimento não vai acontecer, cancele o procedimento.")
    como = (("conferido bipando" if modo == "bipando" else "conferido pela lista")
            + (f", ciência de {quem['nome']} (usuário logado)" if logado else f", senha de {quem['nome']}"))
    ok, msg = _registrar_recebimento(disp, chegou, quem, f"Recebido na sala ({como})")
    if ok and faltou:
        _registrar_nao_recebidos(disp, faltou, quem)
        msg += (f" {len(faltou)} item(ns) não recebido(s): ficam como “não recebido — aguardando "
                f"conferência da farmácia” até a farmácia localizar o material.")
    return ok, msg


def _registrar_nao_recebidos(disp: dict, faltou: list[dict], quem: dict) -> None:
    agora = db.agora()
    with db.transacao() as conn:
        for i in faltou:
            st = conn.execute("SELECT status FROM unidades WHERE id_unidade = ?", (i["id_unidade"],)).fetchone()
            status = st[0] if st else ""
            if status == TRANSITO_SALA:
                # v18.4.3: não volta direto ao estoque — fica "não recebido —
                # aguardando conferência da farmácia" até ser localizado.
                conn.execute("""UPDATE unidades SET status = ?, id_atendimento = NULL,
                                atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?""",
                             (NAO_RECEBIDO, agora, quem["username"], i["id_unidade"]))
            novo = conn.execute("SELECT status FROM unidades WHERE id_unidade = ?", (i["id_unidade"],)).fetchone()
            db.registrar_evento(
                conn, tipo="nao_recebido_sala", id_unidade=i["id_unidade"],
                id_atendimento=disp["id_atendimento"], status_anterior=status,
                status_novo=novo[0] if novo else status, usuario=quem["username"], recebido_por=quem["nome"],
                observacao=(f"[{i['id_caixa']}] " if i["id_caixa"] else "")
                           + f"Sala informou que não recebeu (conferência de {quem['nome']}); "
                             f"dispensado por {i['bipado_por']}")
            conn.execute("""UPDATE dispensacao_itens SET situacao = 'nao_recebido', resolvido_em = ?,
                            resolvido_por = ? WHERE id_item = ?""", (agora, quem["username"], i["id_item"]))
            if i["id_caixa"]:
                conn.execute("""UPDATE caixas SET status = ?, id_atendimento = NULL, atualizado_em = ?,
                                atualizado_por = ? WHERE UPPER(id_caixa) = UPPER(?) AND status = ?""",
                             (NAO_RECEBIDO, agora, quem["username"], i["id_caixa"], TRANSITO_SALA))


def _registrar_recebimento(disp: dict, pend: list[dict], quem: dict, como: str) -> tuple[bool, str]:
    agora = db.agora()
    recebidos = 0
    with db.transacao() as conn:
        for i in pend:
            st = conn.execute("SELECT status FROM unidades WHERE id_unidade = ?", (i["id_unidade"],)).fetchone()
            status = st[0] if st else ""
            if status == TRANSITO_SALA:
                conn.execute("""UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                                WHERE id_unidade = ?""", (EM_SALA, agora, quem["username"], i["id_unidade"]))
            db.registrar_evento(
                conn, tipo="confirmar_recebimento_sala", id_unidade=i["id_unidade"],
                id_atendimento=disp["id_atendimento"], status_anterior=status,
                status_novo=EM_SALA if status == TRANSITO_SALA else status,
                usuario=quem["username"], recebido_por=quem["nome"],
                observacao=(f"[{i['id_caixa']}] " if i["id_caixa"] else "")
                           + f"{como}; dispensado por {i['bipado_por']}"
                           + (" (já tinha sido usado)" if status == UTILIZADO else ""))
            conn.execute("""UPDATE dispensacao_itens SET situacao = 'recebido', resolvido_em = ?,
                            resolvido_por = ? WHERE id_item = ?""", (agora, quem["username"], i["id_item"]))
            recebidos += 1
        conn.execute("""UPDATE dispensacoes SET status = 'confirmada', confirmada_em = ?, confirmada_por = ?,
                        recebido_por = ? WHERE id_dispensacao = ?""",
                     (agora, quem["username"], quem["nome"], disp["id_dispensacao"]))
    from .atendimentos import garantir_sala_aberta  # v18.3
    garantir_sala_aberta(disp["id_atendimento"], quem["username"])
    return True, f"Recebimento confirmado por {quem['nome']}: {recebidos} item(ns) na sala."


def atendimento_da_ultima_dispensacao(id_unidade: str) -> str:
    linha = db.consultar_um(
        """SELECT d.id_atendimento FROM dispensacao_itens i JOIN dispensacoes d
           ON d.id_dispensacao = i.id_dispensacao WHERE i.id_unidade = ? AND i.situacao <> 'removido'
           ORDER BY i.id_item DESC LIMIT 1""", (texto(id_unidade),))
    return linha["id_atendimento"] if linha else ""


def pendentes_da_sala(unidade: str, sala: str, id_atendimento: str = "") -> list[dict]:
    """Dispensações para a MESMA sala (unidade + sala) ainda sem a senha da sala.

    Com `id_atendimento`, só as daquele prontuário: a farmácia pode dispensar
    antes para vários pacientes da mesma sala, então a trava é por prontuário
    (out/2026) — primeiro a enfermagem confirma o material daquele paciente,
    depois bipa o uso nele. Os outros prontuários da sala seguem livres.
    """
    filtro = "AND a.id_atendimento = ?" if texto(id_atendimento) else ""
    params = (texto(unidade), texto(sala)) + ((texto(id_atendimento),) if filtro else ())
    return db.consultar(
        """SELECT d.id_dispensacao, d.criado_em, d.criado_por, a.prontuario, a.paciente,
                  a.id_atendimento,
                  (SELECT COUNT(*) FROM dispensacao_itens i WHERE i.id_dispensacao = d.id_dispensacao
                     AND i.situacao = 'pendente') AS qtd
           FROM dispensacoes d JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE d.status = 'pendente' AND a.unidade = ? AND a.sala = ? {filtro}
             AND EXISTS (SELECT 1 FROM dispensacao_itens i JOIN unidades u ON u.id_unidade = i.id_unidade
                         WHERE i.id_dispensacao = d.id_dispensacao AND i.situacao = 'pendente'
                           AND u.status = 'transito_sala'
                           AND NOT EXISTS (SELECT 1 FROM devolucao_itens di JOIN devolucoes dv
                                             ON dv.id_devolucao = di.id_devolucao
                                           WHERE di.id_unidade = u.id_unidade AND di.situacao = 'pendente'
                                             AND dv.status = 'pendente'))
           ORDER BY d.criado_em""".replace("{filtro}", filtro), params)


def bloqueio_do_prontuario(id_atendimento: str) -> list[dict]:
    """Dispensação deste prontuário ainda sem a confirmação da enfermagem."""
    at = db.consultar_um("SELECT unidade, sala FROM atendimentos WHERE id_atendimento = ?",
                         (texto(id_atendimento),))
    return pendentes_da_sala(at["unidade"], at["sala"], id_atendimento) if at else []


bloqueio_da_sala = bloqueio_do_prontuario  # nome antigo


def sala_ja_recebeu(id_atendimento: str) -> bool:
    """A sala já confirmou alguma entrega da farmácia para este paciente."""
    return bool(db.escalar(
        "SELECT COUNT(*) FROM dispensacoes WHERE id_atendimento = ? AND status = 'confirmada'",
        (texto(id_atendimento),)))


def trava_do_registro(id_atendimento: str) -> list[dict]:
    """O que impede a sala de bipar o uso neste prontuário.

    Só a PRIMEIRA entrega trava (a sala confirma o recebimento e começa). Com a
    sala já aberta, material pedido a mais e dispensado depois não trava: a
    sala segue bipando e dá ciência desses itens ao finalizar os utilizados.
    """
    if sala_ja_recebeu(id_atendimento):
        return []
    return bloqueio_do_prontuario(id_atendimento)


def complemento_pendente(id_atendimento: str) -> list[dict]:
    """Dispensado depois que a sala já estava aberta, ainda sem ciência.

    v18.19: cada item vem com o que já aconteceu com ele (`destino`), porque a
    sala pode ter bipado o uso antes de dar a ciência — o que é permitido. Na
    tela de finalizar, essa lista é a PRIMEIRA coisa que aparece.
    """
    from ..domain import UTILIZADO
    if not sala_ja_recebeu(id_atendimento):
        return []
    lista = []
    for item in pendentes_do_atendimento(id_atendimento):
        item = dict(item)
        status = db.escalar("SELECT status FROM unidades WHERE id_unidade = ?",
                            (texto(item.get("id_unidade")),)) if item.get("id_unidade") else ""
        item["status_unidade"] = texto(status)
        item["destino"] = ("já bipado como utilizado neste paciente" if status == UTILIZADO
                           else "ainda na sala — volta para a farmácia se não for usado")
        lista.append(item)
    return lista


def dar_ciencia_complemento(id_atendimento: str, quem: dict) -> tuple[bool, str]:
    """Ciência (usuário logado, sem senha) do que a farmácia dispensou depois que
    a sala já estava aberta — dada ao finalizar os materiais utilizados."""
    if quem.get("papel") not in PAPEIS_QUE_RECEBEM + ("admin",):
        return False, "Só a sala de procedimento dá ciência do recebimento."
    total = 0
    while True:
        disp = pendente_do_atendimento(id_atendimento)
        if not disp:
            break
        pend = itens(disp["id_dispensacao"], so_pendentes=True)
        if not pend:
            db.executar("UPDATE dispensacoes SET status = 'confirmada', confirmada_em = ?, confirmada_por = ? "
                        "WHERE id_dispensacao = ?", (db.agora(), quem["username"], disp["id_dispensacao"]))
            continue
        _registrar_recebimento(dict(disp), pend, quem,
                               f"Ciência de {quem.get('nome') or quem['username']} ao finalizar os utilizados "
                               "(dispensado com a sala já aberta)")
        total += len(pend)
    return True, f"Ciência dada em {total} item(ns) dispensado(s) depois."


# ---------------------------------------------------------------- conciliação

DESFECHOS = {
    "usado": "Usado no paciente",
    "devolvido": "Devolvido ao estoque",
    "aguardando_devolucao": "Devolução bipada — aguardando a farmácia",
    "na_sala": "Ainda na sala (sem uso e sem devolução)",
    "aguardando_sala": "Aguardando a ciência da sala",
    "divergencia": "Divergência",
    "outro": "Outra situação",
}


def conciliacao(inicio: str, fim: str, unidade: str = "", sala: str = "", prontuario: str = "",
                id_atendimento: str = "") -> dict:
    """v17 — o que foi dispensado, usado e devolvido, por sala e prontuário
    (cada procedimento é uma linha; data do procedimento)."""
    cond, params = ["date(a.data_procedimento) BETWEEN date(?) AND date(?)"], [inicio, fim]
    if texto(prontuario):
        cond.append("(a.prontuario LIKE ? OR a.paciente LIKE ?)")
        params += [f"%{texto(prontuario)}%"] * 2
    if texto(id_atendimento):
        cond.append("a.id_atendimento = ?"); params.append(texto(id_atendimento))
    if texto(unidade):
        cond.append("a.unidade = ?"); params.append(texto(unidade))
    if texto(sala):
        cond.append("a.sala = ?"); params.append(texto(sala))
    where = " AND ".join(cond)
    itens_ = db.consultar(
        f"""SELECT i.id_item, i.id_unidade, i.id_caixa, i.bipado_por, i.bipado_em, i.situacao,
                   d.recebido_por, d.status AS status_disp, d.id_dispensacao,
                   a.id_atendimento, a.prontuario, a.paciente, a.unidade, a.sala, a.data_procedimento,
                   u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.status,
                   u.id_atendimento AS atendimento_atual,
                   EXISTS (SELECT 1 FROM dispensacao_itens j WHERE j.id_unidade = i.id_unidade
                             AND j.id_item > i.id_item AND j.situacao <> 'removido') AS redispensado,
                   EXISTS (SELECT 1 FROM devolucao_itens di JOIN devolucoes dv ON dv.id_devolucao = di.id_devolucao
                             WHERE di.id_unidade = i.id_unidade AND di.situacao = 'pendente'
                               AND dv.status = 'pendente') AS devolucao_pendente
            FROM dispensacao_itens i
            JOIN dispensacoes d ON d.id_dispensacao = i.id_dispensacao
            JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
            LEFT JOIN unidades u ON u.id_unidade = i.id_unidade
            WHERE i.situacao <> 'removido' AND {where}
            ORDER BY a.unidade, a.sala, a.data_procedimento, a.prontuario, i.id_item""", params)
    for i in itens_:
        st = i["status"]
        if i["redispensado"]:
            i["desfecho"] = "devolvido"
        elif st == UTILIZADO:
            i["desfecho"] = "usado"
        elif i["devolucao_pendente"]:
            i["desfecho"] = "aguardando_devolucao"
        elif st == TRANSITO_SALA:
            i["desfecho"] = "aguardando_sala"
        elif st == EM_SALA:
            i["desfecho"] = "na_sala"
        elif st in ESTOQUE_LIVRE:
            i["desfecho"] = "devolvido"
        elif st == "divergencia":
            i["desfecho"] = "divergencia"
        else:
            i["desfecho"] = "outro"
        i["rotulo_desfecho"] = DESFECHOS[i["desfecho"]]
    sem_disp = db.consultar(
        f"""SELECT s.*, a.unidade, a.sala, a.prontuario, a.paciente, a.data_procedimento,
                   u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote
            FROM usos_sem_dispensacao s JOIN atendimentos a ON a.id_atendimento = s.id_atendimento
            LEFT JOIN unidades u ON u.id_unidade = s.id_unidade
            WHERE s.situacao <> 'cancelado' AND {where}""", params)
    salas: dict[tuple, dict] = {}
    def linha(reg):
        chave = (reg["unidade"], reg["sala"], reg["id_atendimento"])
        return salas.setdefault(chave, {"unidade": reg["unidade"], "sala": reg["sala"],
                                        "id_atendimento": reg["id_atendimento"],
                                        "prontuario": reg["prontuario"], "paciente": reg["paciente"],
                                        "data_procedimento": reg["data_procedimento"], "dispensado": 0,
                                        "usado": 0, "devolvido": 0, "aguardando_devolucao": 0,
                                        "na_sala": 0, "aguardando_sala": 0, "divergencia": 0,
                                        "outro": 0, "sem_dispensacao": 0, "sem_ciencia": 0})
    for i in itens_:
        l = linha(i)
        l["dispensado"] += 1
        l[i["desfecho"]] += 1
    for s in sem_disp:
        l = linha(s)
        l["sem_dispensacao"] += 1
        l["sem_ciencia"] += 1 if s["situacao"] == "pendente" else 0
    resumo = sorted(salas.values(), key=lambda x: (x["unidade"] or "", x["sala"] or "",
                                                   x["data_procedimento"] or "", x["prontuario"] or ""))
    for l in resumo:
        l["em_aberto"] = l["na_sala"] + l["aguardando_sala"] + l["aguardando_devolucao"]
        l["fechado"] = l["em_aberto"] == 0 and not l["divergencia"]
    total = {k: sum(l[k] for l in resumo) for k in ("dispensado", "usado", "devolvido", "em_aberto",
                                                     "divergencia", "sem_dispensacao", "sem_ciencia")}
    return {"salas": resumo, "itens": itens_, "sem_dispensacao": sem_disp, "total": total}


# ---------------------------------------------------------------- PDF para a sala

def pdf(id_dispensacao: str) -> bytes | None:
    """v17 — lista do material dispensado, para acompanhar o material até a sala."""
    from ..config import rotulo_unidade
    from ..pdf_simples import tabela
    from ..utils import data_hora_br
    disp = buscar(id_dispensacao)
    if not disp:
        return None
    itens_ = disp["itens"]
    caixas_ = sorted({i["id_caixa"] for i in itens_ if i["id_caixa"]})
    info = [("Prontuário", f"{disp.get('prontuario') or '—'}"
                           + (f" · {disp['paciente']}" if disp.get("paciente") else "")),
            ("Local", f"{rotulo_unidade(disp.get('unidade') or '')} — sala {disp.get('sala') or '—'}"),
            ("Dispensado por", f"{disp.get('criado_por') or '—'} em {data_hora_br(disp.get('criado_em'))}"),
            ("Situação", (f"recebido na sala por {disp.get('recebido_por')} em "
                          f"{data_hora_br(disp.get('confirmada_em'))}")
                         if disp.get("status") == "confirmada" else "aguardando a confirmação da sala")]
    linhas = [[i["codigo_aghu"] or "—", i["descritivo_hospital"] or i["xProd"] or "",
               i["nLote"] or "—", data_br(i["dVal"]) or "—", i["id_caixa"] or "—",
               "recebido" if i["situacao"] != "pendente" else "aguardando"] for i in itens_]
    return tabela(
        titulo="Dispensação para a sala — material do paciente",
        subtitulo=f"Dispensação {disp['id_dispensacao']}",
        informacoes=info,
        colunas=[("AGHU", .9), ("Descrição", 6.0), ("Lote", 1.4), ("Validade", 1.0),
                 ("Caixa", 1.1), ("Situação", 1.0)],
        linhas=linhas,
        totais=[f"{len(itens_)} item(ns)" + (f" · {len(caixas_)} caixa(s) de consignado: "
                                            + ", ".join(caixas_) if caixas_ else ""),
                "",
                "Entregue por (farmácia): ______________________________    "
                "Recebido por (sala): ______________________________"],
        rodape="TraceOPME · Farmácia > Dispensar para a sala",
        quebrar_linhas=True,
    )


# ---------------------------------------------------------------- v18.4.3: não recebidos
ACOES_NAO_RECEBIDO = {
    "localizado": "Localizado na farmácia — volta ao estoque",
    "na_sala": "Estava na sala — a sala recebeu",
    "recolhido_apos_finalizacao": "Estava na sala, mas o uso já foi finalizado — recolhido à farmácia",
    "extraviado": "Não localizado — registrar extravio (divergência)",
}
# v18.4.5: o que fica registrado no item da dispensação (a divergência inicial
# — "não recebido" — continua registrada no evento e na tratativa).
TRATATIVA_NAO_RECEBIDO = {
    "localizado": "localizado_farmacia",
    "na_sala": "recebido_na_conferencia",
    "recolhido_apos_finalizacao": "recolhido_apos_finalizacao",
    "extraviado": "extravio",
}


def nao_recebidos(farmacia: str = "") -> list[dict]:
    """Itens que a sala disse não ter recebido e a farmácia ainda não conferiu."""
    cond, params = "", []
    if texto(farmacia):
        cond, params = "AND u.farmacia = ?", [texto(farmacia)]
    return [dict(r) for r in db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS descricao,
                   u.nLote, u.dVal, u.numero_serie, u.farmacia, u.id_caixa,
                   e.data_evento AS informado_em, e.usuario AS informado_por, e.id_atendimento,
                   a.prontuario, a.paciente, a.sala, a.status AS status_atendimento,
                   a.uso_finalizado_em
            FROM unidades u
            LEFT JOIN eventos e ON e.id_evento = (SELECT MAX(id_evento) FROM eventos
                                                  WHERE id_unidade = u.id_unidade AND tipo = 'nao_recebido_sala')
            LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
            WHERE u.status = ? {cond}
            ORDER BY e.data_evento""", (NAO_RECEBIDO, *params))]


def _situacao_da_caixa(conn, id_caixa: str, id_atendimento, usuario: str, agora: str) -> None:
    """v18.4.5: a caixa só sai de "não recebido" quando TODAS as unidades dela
    foram conferidas. Enquanto houver unidade pendente, a caixa continua fora do estoque."""
    if not texto(id_caixa):
        return
    status = [r[0] for r in conn.execute("SELECT status FROM unidades WHERE id_caixa = ?", (id_caixa,))]
    if NAO_RECEBIDO in status:
        return
    if EM_SALA in status:
        novo, at = EM_SALA, id_atendimento
    elif any(st in ESTOQUE_LIVRE for st in status):
        novo, at = EM_ESTOQUE_FARMACIA, None
    else:
        novo, at = DIVERGENCIA, None
    conn.execute("""UPDATE caixas SET status = ?, id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
                    WHERE UPPER(id_caixa) = UPPER(?) AND status = ?""",
                 (novo, at, agora, usuario, id_caixa, NAO_RECEBIDO))


def tratar_nao_recebido(id_unidade: str, acao: str, usuario: str, motivo: str = "",
                        farmacia: str = "") -> tuple[bool, str]:
    """A farmácia confere o item não recebido: localizado, estava na sala, recolhido
    depois da finalização ou extraviado.

    v18.4.5: só a farmácia dona do material confere; "estava na sala" só vale com o
    registro de uso ainda aberto; e o item da dispensação acompanha o resultado.
    """
    if acao not in ACOES_NAO_RECEBIDO:
        return False, "Escolha o que aconteceu com o material."
    if acao in ("extraviado", "recolhido_apos_finalizacao") and not texto(motivo):
        return False, ("Descreva o que foi verificado antes de registrar o extravio." if acao == "extraviado"
                       else "Informe onde o material foi encontrado e quem o recolheu.")
    if not texto(farmacia):
        return False, "Escolha a farmácia em que você está trabalhando antes de conferir."
    agora = db.agora()
    try:
        with db.transacao() as conn:
            u = conn.execute("SELECT status, farmacia, id_caixa FROM unidades WHERE id_unidade = ?",
                             (texto(id_unidade),)).fetchone()
            if not u or u[0] != NAO_RECEBIDO:
                raise ErroDeNegocio("Este material já foi conferido.")
            ultimo = conn.execute("""SELECT id_atendimento FROM eventos WHERE id_unidade = ? AND tipo = 'nao_recebido_sala'
                                     ORDER BY id_evento DESC LIMIT 1""", (texto(id_unidade),)).fetchone()
            id_at = ultimo[0] if ultimo else None
            at = conn.execute("SELECT status, uso_finalizado_em, unidade FROM atendimentos WHERE id_atendimento = ?",
                              (id_at,)).fetchone()
            dona = texto(u[1]) or (texto(at[2]) if at else "")
            if dona and dona != texto(farmacia):
                raise ErroDeNegocio(f"Este material pertence à {rotulo_farmacia(dona)}. "
                                    f"Só ela pode conferir o não recebido.")
            finalizado = bool(at and (at[0] != "aberto" or at[1]))
            if acao == "localizado":
                novo, at_novo, obs = estoque_de_volta(u[1]), None, "Localizado pela farmácia; volta ao estoque"
            elif acao == "na_sala":
                if not at or at[0] != "aberto":
                    raise ErroDeNegocio("O procedimento deste paciente não está mais aberto. Use “Localizado” "
                                        "(volta ao estoque) e dispense de novo, se for o caso.")
                if at[1]:
                    raise ErroDeNegocio("A sala já finalizou o registro de uso e devoluções deste paciente. "
                                        "Use “Estava na sala, mas o uso já foi finalizado — recolhido à farmácia”, "
                                        "informando onde o material estava.")
                novo, at_novo, obs = EM_SALA, id_at, "Estava na sala: recebimento registrado depois, na conferência"
            elif acao == "recolhido_apos_finalizacao":
                if not finalizado:
                    raise ErroDeNegocio("O registro de uso deste paciente ainda está aberto: use “Estava na sala”.")
                novo, at_novo = estoque_de_volta(u[1]), None
                obs = (f"Encontrado na sala depois da finalização; recolhido à farmácia e conciliado. "
                       f"Local/conferência: {texto(motivo)}")
            else:
                novo, at_novo, obs = DIVERGENCIA, None, f"Não localizado (extravio): {texto(motivo)}"
            mudou = conn.execute("""UPDATE unidades SET status = ?, id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
                                    WHERE id_unidade = ? AND status = ?""",
                                 (novo, at_novo, agora, usuario, texto(id_unidade), NAO_RECEBIDO)).rowcount
            if not mudou:
                raise ErroDeNegocio("Este material já foi conferido.")
            # O item da dispensação acompanha o resultado. Só "estava na sala" vira
            # recebido; a tratativa guarda que houve divergência na chegada.
            item = conn.execute("""SELECT i.id_item FROM dispensacao_itens i JOIN dispensacoes d
                                     ON d.id_dispensacao = i.id_dispensacao
                                   WHERE i.id_unidade = ? AND i.situacao = 'nao_recebido'
                                     AND COALESCE(i.tratativa, '') = '' AND (? IS NULL OR d.id_atendimento = ?)
                                   ORDER BY i.id_item DESC LIMIT 1""", (texto(id_unidade), id_at, id_at)).fetchone()
            if item:
                conn.execute("""UPDATE dispensacao_itens SET situacao = ?, tratativa = ?, tratativa_em = ?,
                                tratativa_por = ? WHERE id_item = ?""",
                             ("recebido" if acao == "na_sala" else "nao_recebido", TRATATIVA_NAO_RECEBIDO[acao],
                              agora, usuario, item[0]))
            db.registrar_evento(conn, tipo="nao_recebido_conferido", id_unidade=texto(id_unidade),
                                id_atendimento=id_at, status_anterior=NAO_RECEBIDO, status_novo=novo,
                                usuario=usuario, motivo=ACOES_NAO_RECEBIDO[acao], observacao=obs)
            _situacao_da_caixa(conn, texto(u[2]), at_novo or id_at, usuario, agora)
    except ErroDeNegocio as recusa:
        return False, str(recusa)
    return True, {"localizado": "Material de volta ao estoque.", "na_sala": "Recebimento na sala registrado.",
                  "recolhido_apos_finalizacao": "Material recolhido à farmácia e conciliado (volta ao estoque).",
                  "extraviado": "Extravio registrado como divergência."}[acao]


def contar_nao_recebidos(farmacia: str = "") -> int:
    return len(nao_recebidos(farmacia))
