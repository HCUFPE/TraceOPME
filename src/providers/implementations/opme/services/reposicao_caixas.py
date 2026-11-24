"""v18.11.8 — Reposição das caixas de consignado.

Olha o que SAIU das caixas por USO no paciente num período e o que já VOLTOU a
entrar na mesma caixa (mesmo código AGHU) depois disso. A diferença é o que falta
repor. Para cada falta mostra se o almoxarifado tem saldo para enviar à farmácia
ou se é preciso pedir ao fornecedor.
"""

from __future__ import annotations

from .. import db
from ..domain import EM_ESTOQUE_RECEBIMENTO
from ..utils import texto
from . import caixas


def a_repor(de: str = "", ate: str = "") -> list[dict]:
    filtro, params = "", [caixas.SAIDA_USO]
    if texto(de):
        filtro += " AND substr(ci.saiu_em, 1, 10) >= ?"
        params.append(texto(de)[:10])
    if texto(ate):
        filtro += " AND substr(ci.saiu_em, 1, 10) <= ?"
        params.append(texto(ate)[:10])
    saidas = db.consultar(
        f"""SELECT ci.id_caixa, c.nome, c.farmacia, c.status AS status_caixa, c.local AS local_caixa,
                   UPPER(TRIM(COALESCE(u.codigo_aghu, ''))) AS aghu,
                   MAX(COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd)) AS descricao,
                   GROUP_CONCAT(DISTINCT u.fornecedor) AS fornecedores,
                   COUNT(*) AS usados, MIN(ci.saiu_em) AS primeira_saida, MAX(ci.saiu_em) AS ultima_saida
            FROM caixa_itens ci
            JOIN unidades u ON u.id_unidade = ci.id_unidade
            JOIN caixas c ON c.id_caixa = ci.id_caixa
            WHERE ci.motivo_saida = ?{filtro}
            GROUP BY ci.id_caixa, UPPER(TRIM(COALESCE(u.codigo_aghu, '')))
            ORDER BY ci.id_caixa, descricao""",
        tuple(params),
    )
    linhas = []
    saldo: dict[str, int] = {}   # v18.12: o saldo do almoxarifado é repartido entre as linhas do mesmo AGHU
    for s in saidas:
        repostos = db.escalar(
            """SELECT COUNT(*) FROM caixa_itens ci JOIN unidades u ON u.id_unidade = ci.id_unidade
               WHERE ci.id_caixa = ? AND UPPER(TRIM(COALESCE(u.codigo_aghu, ''))) = ?
                 AND ci.entrou_em > ?""",
            (s["id_caixa"], s["aghu"], s["primeira_saida"])) or 0
        faltam = int(s["usados"]) - int(repostos)
        if faltam <= 0:
            continue
        if s["aghu"] not in saldo:
            saldo[s["aghu"]] = int(db.escalar(
                """SELECT COUNT(*) FROM unidades
                   WHERE status = ? AND UPPER(TRIM(COALESCE(codigo_aghu, ''))) = ?
                     AND COALESCE(id_caixa, '') = ''
                     AND (dVal IS NULL OR dVal = '' OR substr(dVal, 1, 10) >= date('now'))""",
                (EM_ESTOQUE_RECEBIMENTO, s["aghu"])) or 0)
        no_almox = saldo[s["aghu"]]
        saldo[s["aghu"]] = max(0, no_almox - faltam)
        from . import caixas_almox
        local = caixas_almox.local({"local": s["local_caixa"]})
        linhas.append(dict(s) | {
            "repostos": int(repostos), "faltam": faltam, "no_almoxarifado": int(no_almox), "local": local,
            "acao": "enviar" if no_almox >= faltam else ("enviar_parcial" if no_almox else "fornecedor"),
        })
    return linhas
