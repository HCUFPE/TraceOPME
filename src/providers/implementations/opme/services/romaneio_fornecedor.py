"""nov/2026 — romaneio da devolução ao fornecedor.

A devolução ao fornecedor continua sendo feita na bipagem (operação
`devolver_fornecedor`). Esta tela junta o que foi devolvido — por período e
fornecedor — e gera o ROMANEIO em PDF: a lista dos itens com espaço para a
assinatura de quem entrega pelo hospital e de quem recebe pelo fornecedor.

Só entram unidades que continuam "devolvidas ao fornecedor" (uma devolução
desfeita sai do romaneio) e o evento de devolução mais recente de cada uma.
"""

from datetime import datetime

from .. import db
from ..domain import DEVOLVIDO_FORNECEDOR
from ..utils import data_br, data_hora_br, data_iso, hoje_iso, moeda, texto

TIPO = "devolver_fornecedor"


def _fornecedor_sql() -> str:
    return "COALESCE(NULLIF(TRIM(u.fornecedor), ''), 'Fornecedor não informado')"


def devolucoes(inicio: str = "", fim: str = "", fornecedor: str = "", ids: list[str] | None = None,
               limite: int = 2000) -> list[dict]:
    """Itens devolvidos ao fornecedor (o evento de devolução mais recente de cada unidade)."""
    cond = ["u.status = ?", "e.tipo = ?",
            "e.id_evento = (SELECT MAX(x.id_evento) FROM eventos x WHERE x.id_unidade = u.id_unidade AND x.tipo = ?)"]
    params: list = [DEVOLVIDO_FORNECEDOR, TIPO, TIPO]
    ids = [texto(i) for i in (ids or []) if texto(i)]
    if ids:
        cond.append(f"u.id_unidade IN ({','.join('?' for _ in ids)})")
        params += ids
    else:
        if data_iso(inicio):
            cond.append("substr(e.data_evento, 1, 10) >= ?")
            params.append(data_iso(inicio))
        if data_iso(fim):
            cond.append("substr(e.data_evento, 1, 10) <= ?")
            params.append(data_iso(fim))
        if texto(fornecedor):
            cond.append(f"{_fornecedor_sql()} = ?")
            params.append(texto(fornecedor))
    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, u.codigo_consignado, u.codigo_barras, u.nLote, u.numero_serie,
                   u.dVal, u.numero_nf, u.vUnCom, u.tipo_entrada, u.marca_fabricante,
                   COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd) AS descricao,
                   {_fornecedor_sql()} AS fornecedor_nome,
                   e.data_evento, e.usuario, e.motivo, e.observacao
            FROM unidades u JOIN eventos e ON e.id_unidade = u.id_unidade
            WHERE {' AND '.join(cond)}
            ORDER BY fornecedor_nome, e.data_evento DESC, descricao LIMIT {int(limite)}""", params)
    for l in linhas:
        l["validade"] = data_br(l["dVal"]) or "—"
        l["quando"] = data_hora_br(l["data_evento"])
    return linhas


def por_fornecedor(linhas: list[dict]) -> list[dict]:
    grupos: dict[str, dict] = {}
    for l in linhas:
        g = grupos.setdefault(l["fornecedor_nome"], {"fornecedor": l["fornecedor_nome"], "itens": [], "valor": 0.0})
        g["itens"].append(l)
        g["valor"] += float(l["vUnCom"] or 0)
    for g in grupos.values():
        g["valor_br"] = moeda(g["valor"])
    return list(grupos.values())


def pdf(ids: list[str], usuario: str = "") -> tuple[bytes | None, str]:
    """(PDF do romaneio, nome do arquivo). Um fornecedor por romaneio."""
    from ..pdf_simples import tabela
    linhas = devolucoes(ids=ids)
    if not linhas:
        return None, "Escolha os itens do romaneio."
    fornecedores = sorted({l["fornecedor_nome"] for l in linhas})
    if len(fornecedores) > 1:
        return None, "Um romaneio é de um fornecedor só. Marque os itens de um fornecedor por vez."
    fornecedor = fornecedores[0]
    agora = datetime.now()
    numero = "ROM-" + agora.strftime("%Y%m%d-%H%M")
    datas = sorted({l["data_evento"][:10] for l in linhas if l.get("data_evento")})
    periodo = (data_br(datas[0]) if len(datas) == 1 else f"{data_br(datas[0])} a {data_br(datas[-1])}") if datas else "—"
    notas = sorted({texto(l["numero_nf"]) for l in linhas if texto(l["numero_nf"])})
    valor = sum(float(l["vUnCom"] or 0) for l in linhas)
    conteudo = tabela(
        titulo=f"Romaneio de devolução ao fornecedor — {numero}",
        subtitulo="TraceOPME · Almoxarifado · material devolvido ao fornecedor",
        informacoes=[("Fornecedor", fornecedor),
                     ("Data da devolução", periodo),
                     ("Notas fiscais de origem", ", ".join(notas) or "—"),
                     ("Emitido por", f"{usuario or '—'} em {agora.strftime('%d/%m/%Y %H:%M')}")],
        colunas=[("#", .35), ("AGHU", .75), ("Consignado", 1.0), ("Material", 3.6), ("Lote", 1.1),
                 ("Nº série", 1.1), ("Validade", .85), ("NF", .7), ("Valor unit.", .85), ("Motivo", 1.6)],
        linhas=[[str(n), l["codigo_aghu"] or "—", l["codigo_consignado"] or "—", l["descricao"] or "",
                 l["nLote"] or "—", l["numero_serie"] or "—", l["validade"], l["numero_nf"] or "—",
                 moeda(l["vUnCom"] or 0), l["motivo"] or ""] for n, l in enumerate(linhas, 1)],
        quebrar_linhas=True,
        totais=[f"Total: {len(linhas)} item(ns) · {moeda(valor)}"],
        texto_final=("Declaramos que os materiais relacionados acima foram conferidos e entregues pelo hospital ao "
                     "fornecedor nesta data, nas quantidades e com os lotes/números de série indicados."),
        assinaturas=["Pelo hospital (entregue por)", "Pelo fornecedor (recebido por)"],
        rodape=f"TraceOPME · Romaneio {numero}",
    )
    nome = f"romaneio_devolucao_{fornecedor[:30]}_{agora.strftime('%Y%m%d_%H%M')}.pdf"
    nome = "".join(c if c.isalnum() or c in "._-" else "_" for c in nome)
    return conteudo, nome


def periodo_padrao() -> tuple[str, str]:
    return hoje_iso(), hoje_iso()
