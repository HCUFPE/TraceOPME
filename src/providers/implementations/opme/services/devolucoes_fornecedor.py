"""v18 — devolução ao fornecedor com NÚMERO.

Antes o romaneio era uma lista de itens devolvidos no período. Agora cada
devolução tem número (DEV-2026-0001), é de UM fornecedor e junta os itens
bipados em "Devolver ao fornecedor":

* cada item bipado entra na devolução ABERTA de quem bipou para o fornecedor
  daquele item (se não houver, ela é criada) — bipar itens de dois fornecedores
  abre duas devoluções;
* "Finalizar" fecha a devolução; o romaneio em PDF é por devolução (com as
  assinaturas do hospital e do fornecedor) e pode ser baixado a qualquer hora;
* dá para CANCELAR a devolução inteira ou um item: o material volta para onde
  estava antes (almoxarifado ou a farmácia), com o motivo no histórico;
* devoluções antigas (antes da v18) são agrupadas sozinhas por fornecedor, dia e
  usuário, marcadas como "anteriores à v18".
"""

from __future__ import annotations

from datetime import datetime

from .. import db
from ..domain import DEVOLVIDO_FORNECEDOR, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO
from ..utils import data_br, data_hora_br, data_iso, moeda, texto

SITUACOES = {"aberta": "Aberta (bipando)", "finalizada": "Finalizada", "cancelada": "Cancelada"}


def _nome_fornecedor(valor) -> str:
    return texto(valor) or "Fornecedor não informado"


def _novo_id(conn, ano: int) -> tuple[str, int]:
    ultimo = conn.execute("SELECT MAX(numero) FROM devolucoes_fornecedor WHERE ano = ?", (ano,)).fetchone()[0]
    numero = int(ultimo or 0) + 1
    return f"DEV-{ano}-{numero:04d}", numero


def _criar(conn, fornecedor: str, usuario: str, quando: str, status: str = "aberta", legado: int = 0) -> str:
    ano = int(quando[:4]) if quando[:4].isdigit() else datetime.now().year
    id_dev, numero = _novo_id(conn, ano)
    conn.execute(
        """INSERT INTO devolucoes_fornecedor (id_devolucao, ano, numero, fornecedor, status, criada_em, criada_por,
                                              finalizada_em, finalizada_por, legado)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (id_dev, ano, numero, fornecedor, status, quando, usuario,
         quando if status == "finalizada" else None, usuario if status == "finalizada" else None, legado))
    return id_dev


# ---------------------------------------------------------------- bipagem

def anexar(id_unidade: str, usuario: str, motivo: str = "") -> dict | None:
    """Coloca a unidade recém-devolvida na devolução aberta (de quem bipou + fornecedor)."""
    u = db.consultar_um("SELECT id_unidade, fornecedor, status, farmacia FROM unidades WHERE id_unidade = ?",
                        (texto(id_unidade),))
    if not u or u["status"] != DEVOLVIDO_FORNECEDOR:
        return None
    ev = db.consultar_um(
        "SELECT status_anterior FROM eventos WHERE id_unidade = ? AND tipo = 'devolver_fornecedor' "
        "ORDER BY id_evento DESC LIMIT 1", (u["id_unidade"],))
    fornecedor = _nome_fornecedor(u["fornecedor"])
    agora = db.agora()
    with db.transacao() as conn:
        ja = conn.execute(
            """SELECT i.id_devolucao FROM devolucao_fornecedor_itens i JOIN devolucoes_fornecedor d
                 ON d.id_devolucao = i.id_devolucao
               WHERE i.id_unidade = ? AND i.situacao = 'ativo' AND d.status <> 'cancelada'""",
            (u["id_unidade"],)).fetchone()
        if ja:
            return buscar(ja[0])
        linha = conn.execute(
            """SELECT id_devolucao FROM devolucoes_fornecedor
               WHERE status = 'aberta' AND criada_por = ? AND fornecedor = ?
               ORDER BY criada_em DESC LIMIT 1""", (usuario, fornecedor)).fetchone()
        id_dev = linha[0] if linha else _criar(conn, fornecedor, usuario, agora)
        conn.execute(
            """INSERT INTO devolucao_fornecedor_itens (id_devolucao, id_unidade, status_anterior, farmacia_anterior,
                                                       motivo, adicionado_em, adicionado_por)
               VALUES (?,?,?,?,?,?,?)""",
            (id_dev, u["id_unidade"], (ev or {}).get("status_anterior") or EM_ESTOQUE_RECEBIMENTO,
             u["farmacia"], texto(motivo), agora, usuario))
    return buscar(id_dev)


def desfeito(id_unidade: str) -> None:
    """A devolução da unidade foi desfeita na bipagem ("Desfazer"): sai da devolução."""
    u = db.consultar_um("SELECT status FROM unidades WHERE id_unidade = ?", (texto(id_unidade),))
    if u and u["status"] == DEVOLVIDO_FORNECEDOR:
        return
    db.executar("""UPDATE devolucao_fornecedor_itens SET situacao = 'desfeito', cancelado_em = ?
                   WHERE id_unidade = ? AND situacao = 'ativo'""", (db.agora(), texto(id_unidade)))


def abertas(usuario: str) -> list[dict]:
    return [_resumo(d) for d in db.consultar(
        "SELECT * FROM devolucoes_fornecedor WHERE status = 'aberta' AND criada_por = ? ORDER BY criada_em",
        (usuario,))]


def finalizar(id_devolucao: str, usuario: str) -> tuple[bool, str]:
    d = buscar(id_devolucao)
    if not d:
        return False, "Devolução não encontrada."
    if d["status"] != "aberta":
        return False, f"A devolução {d['id_devolucao']} já está {SITUACOES[d['status']].lower()}."
    if not d["qtd_itens"]:
        return False, "A devolução não tem itens."
    db.executar("""UPDATE devolucoes_fornecedor SET status = 'finalizada', finalizada_em = ?, finalizada_por = ?
                   WHERE id_devolucao = ?""", (db.agora(), usuario, d["id_devolucao"]))
    return True, (f"Devolução {d['id_devolucao']} finalizada ({d['qtd_itens']} item(ns) para {d['fornecedor']}). "
                  "Baixe o romaneio para as assinaturas.")


# ---------------------------------------------------------------- consulta

def _resumo(d: dict) -> dict:
    d = dict(d)
    tot = db.consultar_um(
        """SELECT COUNT(*) AS qtd, COALESCE(SUM(u.vUnCom), 0) AS valor
           FROM devolucao_fornecedor_itens i JOIN unidades u ON u.id_unidade = i.id_unidade
           WHERE i.id_devolucao = ? AND i.situacao = 'ativo'""", (d["id_devolucao"],)) or {}
    d["qtd_itens"] = int(tot.get("qtd") or 0)
    d["valor"] = float(tot.get("valor") or 0)
    d["valor_br"] = moeda(d["valor"])
    d["rotulo_status"] = SITUACOES.get(d["status"], d["status"])
    return d


def buscar(id_devolucao: str) -> dict | None:
    d = db.consultar_um("SELECT * FROM devolucoes_fornecedor WHERE id_devolucao = ?", (texto(id_devolucao),))
    return _resumo(d) if d else None


def itens(id_devolucao: str, so_ativos: bool = False) -> list[dict]:
    linhas = db.consultar(
        f"""SELECT i.*, u.codigo_aghu, u.codigo_consignado, u.codigo_barras, u.nLote, u.numero_serie, u.dVal,
                   u.numero_nf, u.vUnCom, u.status AS status_unidade,
                   COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd) AS descricao
            FROM devolucao_fornecedor_itens i JOIN unidades u ON u.id_unidade = i.id_unidade
            WHERE i.id_devolucao = ? {"AND i.situacao = 'ativo'" if so_ativos else ""}
            ORDER BY i.situacao, i.adicionado_em""", (texto(id_devolucao),))
    for l in linhas:
        l["validade"] = data_br(l["dVal"]) or "—"
        l["quando"] = data_hora_br(l["adicionado_em"])
    return linhas


def listar(inicio: str = "", fim: str = "", fornecedor: str = "", status: str = "") -> list[dict]:
    migrar_legado()
    cond, params = ["1=1"], []
    if data_iso(inicio):
        cond.append("substr(criada_em, 1, 10) >= ?")
        params.append(data_iso(inicio))
    if data_iso(fim):
        cond.append("substr(criada_em, 1, 10) <= ?")
        params.append(data_iso(fim))
    if texto(fornecedor):
        cond.append("fornecedor = ?")
        params.append(texto(fornecedor))
    if texto(status):
        cond.append("status = ?")
        params.append(texto(status))
    return [_resumo(d) for d in db.consultar(
        f"SELECT * FROM devolucoes_fornecedor WHERE {' AND '.join(cond)} ORDER BY criada_em DESC LIMIT 500",
        params)]


def fornecedores() -> list[str]:
    return [l["fornecedor"] for l in db.consultar(
        "SELECT DISTINCT fornecedor FROM devolucoes_fornecedor ORDER BY fornecedor")]


# ---------------------------------------------------------------- cancelar

def _voltar_unidade(conn, item: dict, usuario: str, motivo: str, id_dev: str) -> bool:
    atual = conn.execute("SELECT status, farmacia FROM unidades WHERE id_unidade = ?", (item["id_unidade"],)).fetchone()
    if not atual or atual[0] != DEVOLVIDO_FORNECEDOR:
        return False
    destino = texto(item.get("status_anterior")) or EM_ESTOQUE_RECEBIMENTO
    if destino not in (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA):
        destino = EM_ESTOQUE_FARMACIA if texto(item.get("farmacia_anterior") or atual[1]) else EM_ESTOQUE_RECEBIMENTO
    agora = db.agora()
    conn.execute("UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?",
                 (destino, agora, usuario, item["id_unidade"]))
    db.registrar_evento(conn, tipo="devolucao_fornecedor_cancelada", id_unidade=item["id_unidade"],
                        status_anterior=DEVOLVIDO_FORNECEDOR, status_novo=destino, usuario=usuario, motivo=motivo,
                        observacao=f"Devolução {id_dev} cancelada para este item: o material voltou ao estoque.")
    conn.execute("""UPDATE devolucao_fornecedor_itens SET situacao = 'cancelado', cancelado_em = ?, cancelado_por = ?,
                    motivo_cancelamento = ? WHERE id = ?""", (agora, usuario, motivo, item["id"]))
    return True


def cancelar(id_devolucao: str, usuario: str, motivo: str) -> tuple[bool, str]:
    motivo = texto(motivo)
    d = buscar(id_devolucao)
    if not d:
        return False, "Devolução não encontrada."
    if d["status"] == "cancelada":
        return False, "Esta devolução já foi cancelada."
    if len(motivo) < 5:
        return False, "Informe o motivo do cancelamento."
    voltaram = 0
    with db.transacao() as conn:
        for item in itens(d["id_devolucao"], so_ativos=True):
            voltaram += 1 if _voltar_unidade(conn, item, usuario, motivo, d["id_devolucao"]) else 0
        conn.execute("""UPDATE devolucoes_fornecedor SET status = 'cancelada', cancelada_em = ?, cancelada_por = ?,
                        motivo_cancelamento = ? WHERE id_devolucao = ?""",
                     (db.agora(), usuario, motivo, d["id_devolucao"]))
    return True, f"Devolução {d['id_devolucao']} cancelada. {voltaram} item(ns) voltaram ao estoque."


def cancelar_item(id_devolucao: str, id_unidade: str, usuario: str, motivo: str) -> tuple[bool, str]:
    motivo = texto(motivo)
    d = buscar(id_devolucao)
    if not d or d["status"] == "cancelada":
        return False, "Devolução não encontrada ou já cancelada."
    if len(motivo) < 5:
        return False, "Informe o motivo."
    item = next((i for i in itens(d["id_devolucao"], so_ativos=True) if i["id_unidade"] == texto(id_unidade)), None)
    if not item:
        return False, "Item não está nesta devolução."
    with db.transacao() as conn:
        ok = _voltar_unidade(conn, item, usuario, motivo, d["id_devolucao"])
    if not ok:
        return False, "O item não está mais como devolvido ao fornecedor."
    restante = buscar(d["id_devolucao"])
    if restante and not restante["qtd_itens"]:
        db.executar("""UPDATE devolucoes_fornecedor SET status = 'cancelada', cancelada_em = ?, cancelada_por = ?,
                       motivo_cancelamento = ? WHERE id_devolucao = ?""",
                    (db.agora(), usuario, "Todos os itens foram cancelados", d["id_devolucao"]))
    return True, "Item tirado da devolução: o material voltou ao estoque."


# ---------------------------------------------------------------- romaneio (PDF)

def pdf(id_devolucao: str, usuario: str = "") -> tuple[bytes | None, str]:
    from ..pdf_simples import tabela
    d = buscar(id_devolucao)
    if not d:
        return None, "Devolução não encontrada."
    linhas = itens(d["id_devolucao"], so_ativos=True)
    if not linhas:
        return None, "A devolução não tem itens ativos."
    agora = datetime.now()
    notas = sorted({texto(l["numero_nf"]) for l in linhas if texto(l["numero_nf"])})
    situacao = d["rotulo_status"] + (" (cancelada)" if d["status"] == "cancelada" else "")
    conteudo = tabela(
        titulo=f"Romaneio de devolução ao fornecedor — {d['id_devolucao']}",
        subtitulo="TraceOPME · Almoxarifado · material devolvido ao fornecedor",
        informacoes=[("Devolução", f"{d['id_devolucao']} · {situacao}"),
                     ("Fornecedor", d["fornecedor"]),
                     ("Data da devolução", data_br(d["criada_em"][:10]) or "—"),
                     ("Notas fiscais de origem", ", ".join(notas) or "—"),
                     ("Emitido por", f"{usuario or '—'} em {agora.strftime('%d/%m/%Y %H:%M')}")],
        colunas=[("#", .35), ("AGHU", .75), ("Consignado", 1.0), ("Material", 3.6), ("Lote", 1.1),
                 ("Nº série", 1.1), ("Validade", .85), ("NF", .7), ("Valor unit.", .85), ("Motivo", 1.6)],
        linhas=[[str(n), l["codigo_aghu"] or "—", l["codigo_consignado"] or "—", l["descricao"] or "",
                 l["nLote"] or "—", l["numero_serie"] or "—", l["validade"], l["numero_nf"] or "—",
                 moeda(l["vUnCom"] or 0), l["motivo"] or ""] for n, l in enumerate(linhas, 1)],
        quebrar_linhas=True,
        totais=[f"Total: {len(linhas)} item(ns) · {moeda(sum(float(l['vUnCom'] or 0) for l in linhas))}"],
        texto_final=("Declaramos que os materiais relacionados acima foram conferidos e entregues pelo hospital ao "
                     "fornecedor nesta data, nas quantidades e com os lotes/números de série indicados."),
        assinaturas=["Pelo hospital (entregue por)", "Pelo fornecedor (recebido por)"],
        rodape=f"TraceOPME · Romaneio {d['id_devolucao']}",
    )
    nome = "".join(c if c.isalnum() or c in "._-" else "_"
                   for c in f"romaneio_{d['id_devolucao']}_{d['fornecedor'][:30]}.pdf")
    return conteudo, nome


# ---------------------------------------------------------------- devoluções antigas

def migrar_legado() -> int:
    """Itens devolvidos antes da v18 (sem devolução): uma devolução finalizada por fornecedor + dia + usuário."""
    soltos = db.consultar(
        f"""SELECT u.id_unidade, u.fornecedor, u.farmacia, e.data_evento, e.usuario, e.status_anterior, e.motivo
            FROM unidades u JOIN eventos e ON e.id_evento = (
                 SELECT MAX(x.id_evento) FROM eventos x WHERE x.id_unidade = u.id_unidade AND x.tipo = 'devolver_fornecedor')
            WHERE u.status = '{DEVOLVIDO_FORNECEDOR}'
              AND NOT EXISTS (SELECT 1 FROM devolucao_fornecedor_itens i WHERE i.id_unidade = u.id_unidade
                                AND i.situacao = 'ativo')""")
    if not soltos:
        return 0
    grupos: dict[tuple, list] = {}
    for s in soltos:
        grupos.setdefault((_nome_fornecedor(s["fornecedor"]), texto(s["data_evento"])[:10], texto(s["usuario"])),
                          []).append(s)
    with db.transacao() as conn:
        for (fornecedor, dia, usuario), lista in sorted(grupos.items(), key=lambda g: g[0][1]):
            id_dev = _criar(conn, fornecedor, usuario, lista[0]["data_evento"], status="finalizada", legado=1)
            for s in lista:
                conn.execute(
                    """INSERT INTO devolucao_fornecedor_itens (id_devolucao, id_unidade, status_anterior,
                                                               farmacia_anterior, motivo, adicionado_em, adicionado_por)
                       VALUES (?,?,?,?,?,?,?)""",
                    (id_dev, s["id_unidade"], s["status_anterior"] or EM_ESTOQUE_RECEBIMENTO, s["farmacia"],
                     texto(s["motivo"]), s["data_evento"], s["usuario"]))
    return len(grupos)
