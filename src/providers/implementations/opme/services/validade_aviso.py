"""nov/2026 — aviso de lote com validade mais próxima (FEFO) na dispensa.

Ao enviar do almoxarifado para a farmácia, ou ao dispensar da farmácia para
a sala, o certo é sair primeiro o lote que vence antes. Se a pessoa bipa um
lote e, no mesmo estoque, existe outro lote do mesmo material com validade
mais próxima, a tela avisa e pede ciência. Por enquanto o aviso NÃO trava: com
a ciência, a dispensa segue, e a ciência fica registrada no histórico do item
(evento `ciencia_validade`). Quando a regra for travar, é aqui que muda.

"Mesmo material" = mesmo código AGHU; sem AGHU, mesmo código de barras (GTIN).
Só contam lotes ainda dentro da validade, soltos (fora de caixa) e no mesmo
estoque: o do almoxarifado, ou o da mesma farmácia.
"""

from .. import db
from ..domain import EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO
from ..utils import data_br, hoje_iso, texto

TIPO_EVENTO = "ciencia_validade"


def lote_com_validade_anterior(unidade: dict, *, estoque: str, farmacia: str = "",
                               conn=None) -> dict | None:
    """O lote disponível que vence antes do lote da `unidade`, ou None.

    `estoque`: EM_ESTOQUE_RECEBIMENTO (almoxarifado) ou EM_ESTOQUE_FARMACIA
    (com `farmacia`).
    """
    validade = texto(unidade.get("dVal"))[:10]
    if not validade:
        return None  # sem validade no item escolhido não há com o que comparar
    aghu = texto(unidade.get("codigo_aghu")).strip().upper()
    if aghu:
        material, params_material = "UPPER(TRIM(u.codigo_aghu)) = ?", [aghu]
    elif texto(unidade.get("codigo_barras")):
        material, params_material = "gtin(u.codigo_barras) = gtin(?)", [unidade["codigo_barras"]]
    else:
        return None
    filtro_farmacia, params_farmacia = "", []
    if estoque == EM_ESTOQUE_FARMACIA:
        filtro_farmacia, params_farmacia = " AND COALESCE(u.farmacia, '') = ?", [texto(farmacia)]
    sql = f"""SELECT u.nLote, substr(u.dVal, 1, 10) AS validade, COUNT(*) AS quantidade,
                     MIN(COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd)) AS descricao
              FROM unidades u
              WHERE u.status = ? AND {material}{filtro_farmacia}
                AND COALESCE(u.id_caixa, '') = ''
                AND COALESCE(u.dVal, '') <> ''
                AND substr(u.dVal, 1, 10) >= ?
                AND substr(u.dVal, 1, 10) < ?
                AND u.id_unidade <> ?
                AND NOT EXISTS (SELECT 1 FROM devolucao_itens di JOIN devolucoes dv
                                  ON dv.id_devolucao = di.id_devolucao
                                WHERE di.id_unidade = u.id_unidade AND di.situacao = 'pendente'
                                  AND dv.status = 'pendente')
              GROUP BY u.nLote, substr(u.dVal, 1, 10)
              ORDER BY validade, u.nLote
              LIMIT 1"""
    params = [estoque, *params_material, *params_farmacia, hoje_iso(), validade,
              texto(unidade.get("id_unidade"))]
    if conn is not None:
        linha = conn.execute(sql, params).fetchone()  # sqlite3.Row: acesso por nome
    else:
        linha = db.consultar_um(sql, params)
    if not linha:
        return None
    return {
        "lote": texto(linha["nLote"]) or "—",
        "validade": linha["validade"],
        "validade_br": data_br(linha["validade"]),
        "quantidade": int(linha["quantidade"] or 0),
        "descricao": texto(linha["descricao"]),
    }


def resposta_aviso(unidade: dict, anterior: dict, onde: str) -> dict:
    """Corpo da resposta da bipagem que pede a ciência (nada foi gravado ainda)."""
    lote = texto(unidade.get("nLote")) or "—"
    validade = data_br(unidade.get("dVal")) or "—"
    return {
        "ok": False,
        "aviso_validade": True,
        "titulo": "HÁ LOTE COM VALIDADE MAIS PRÓXIMA",
        "mensagem": (f"Você bipou o lote {lote} (validade {validade}), mas {onde} há "
                     f"{anterior['quantidade']} unidade(s) do lote {anterior['lote']}, que vence antes "
                     f"({anterior['validade_br']}). O recomendado é usar primeiro o que vence antes."),
        "escolhido": {"id_unidade": unidade.get("id_unidade"), "lote": lote, "validade": validade,
                      "descricao": texto(unidade.get("descritivo_hospital")) or texto(unidade.get("xProd")),
                      "aghu": texto(unidade.get("codigo_aghu")) or "—"},
        "mais_proximo": anterior,
    }


def registrar_ciencia(conn, unidade: dict, anterior: dict, usuario: str, onde: str,
                      id_atendimento: str | None = None) -> None:
    db.registrar_evento(
        conn, tipo=TIPO_EVENTO, id_unidade=unidade["id_unidade"], id_atendimento=id_atendimento or None,
        status_anterior=unidade.get("status"), status_novo=unidade.get("status"), usuario=usuario,
        motivo="Ciente de lote com validade mais próxima",
        observacao=(f"Saiu o lote {texto(unidade.get('nLote')) or '—'} (val. {data_br(unidade.get('dVal')) or '—'}) "
                    f"havendo {anterior['quantidade']} unidade(s) do lote {anterior['lote']} "
                    f"(val. {anterior['validade_br']}) {onde}."))


__all__ = ["lote_com_validade_anterior", "resposta_aviso", "registrar_ciencia",
           "EM_ESTOQUE_FARMACIA", "EM_ESTOQUE_RECEBIMENTO", "TIPO_EVENTO"]
