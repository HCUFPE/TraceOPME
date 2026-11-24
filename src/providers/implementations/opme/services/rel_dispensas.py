"""Relatório de movimentações de dispensa num período.

Junta, numa lista só, as duas saídas de material do fluxo:
- **Almoxarifado → Farmácia** (envios: `remessa_itens`), e
- **Farmácia → Sala** (dispensações para o paciente: `dispensacao_itens`).

Uma linha por unidade movimentada, com a situação daquela movimentação (recebido,
aguardando, não recebido, retirado) e a situação atual da unidade. A data é a do
bip de saída. Filtros: período, tipo de movimentação, farmácia e busca livre.
"""

from __future__ import annotations

from .. import db
from ..config import FARMACIAS, rotulo_farmacia, rotulo_unidade
from ..domain import rotulo
from ..utils import data_br, data_hora_br, data_iso, texto

TIPOS = {"": "Todas", "envios": "Almoxarifado → Farmácia", "dispensacoes": "Farmácia → Sala"}

_DESC = ("COALESCE(NULLIF(u.descritivo_hospital, ''), NULLIF(m.descritivo_hospital, ''), u.xProd)")

_SIT_ENVIO = {"recebido": "recebido pela farmácia", "nao_recebido": "não recebido pela farmácia",
              "removido": "retirado do envio"}
_TRATATIVA = {"recebido_depois": "recebido depois", "voltou_almoxarifado": "voltou ao almoxarifado",
              "divergencia": "divergência"}
_SIT_DISP = {"pendente": "aguardando a sala", "recebido": "recebido na sala",
             "nao_recebido": "sala não recebeu — aguardando conferência da farmácia",
             "removido": "retirado da dispensação"}
# v18.4.5: resultado da conferência da farmácia sobre o "não recebido".
_TRATATIVA_DISP = {
    "recebido_na_conferencia": "informado como não recebido; a farmácia confirmou que estava na sala",
    "localizado_farmacia": "localizado na farmácia — voltou ao estoque",
    "recolhido_apos_finalizacao": "estava na sala após a finalização — recolhido à farmácia",
    "extravio": "não localizado — extravio registrado",
}


def _sit_disp(situacao: str, tratativa: str) -> str:
    if tratativa in _TRATATIVA_DISP:
        if tratativa == "recebido_na_conferencia":
            return "recebido na sala (" + _TRATATIVA_DISP[tratativa] + ")"
        return "sala não recebeu · " + _TRATATIVA_DISP[tratativa]
    return _SIT_DISP.get(situacao, situacao)

# Movimentações que não chegaram a sair de fato (não entram nos totais).
NAO_CONTAM = {"removido"}


def _atual(l: dict) -> str:
    if l["status_atual"] == "em_estoque_farmacia":
        return "Em estoque — " + rotulo_farmacia(l.get("farmacia_atual"))
    return rotulo(l["status_atual"] or "")


def _busca(termo: str, params: list) -> str:
    if not texto(termo):
        return ""
    params += [f"%{texto(termo)}%"] * 6
    return (" AND (u.codigo_aghu LIKE ? OR u.xProd LIKE ? OR u.nLote LIKE ? OR u.numero_serie LIKE ?"
            f" OR {_DESC} LIKE ? OR COALESCE(a.prontuario, '') LIKE ?)")


def _envios(inicio: str, fim: str, farmacia: str, termo: str) -> list[dict]:
    params: list = [inicio, fim]
    filtro = ""
    if farmacia:
        filtro += " AND r.farmacia = ?"
        params.append(farmacia)
    filtro += _busca(termo, params).replace("COALESCE(a.prontuario, '')", "''")
    linhas = db.consultar(
        f"""SELECT i.bipado_em AS data, i.bipado_por AS por, i.situacao, i.tratativa, i.resolvido_em,
                   r.id_remessa AS documento, r.farmacia, r.status AS status_doc, r.conferida_nome,
                   r.conferida_por, r.conferida_em,
                   u.id_unidade, u.codigo_aghu, {_DESC} AS descricao, u.nLote, u.dVal, u.numero_serie,
                   u.status AS status_atual, u.farmacia AS farmacia_atual
            FROM remessa_itens i
            JOIN remessas r ON r.id_remessa = i.id_remessa
            JOIN unidades u ON u.id_unidade = i.id_unidade
            LEFT JOIN materiais_mestre m ON m.codigo_aghu = u.codigo_aghu
            WHERE date(i.bipado_em) BETWEEN date(?) AND date(?){filtro}""", params)
    saida = []
    for l in linhas:
        if l["situacao"] == "pendente":
            sit = "no envio (ainda aberto)" if l["status_doc"] == "aberta" else "aguardando ciência da farmácia"
        else:
            sit = _SIT_ENVIO.get(l["situacao"], l["situacao"])
            if l["tratativa"]:
                sit += f" · {_TRATATIVA.get(l['tratativa'], l['tratativa'])}"
        saida.append({
            "data": l["data"], "tipo": "Almoxarifado → Farmácia", "origem": "Almoxarifado",
            "destino": rotulo_farmacia(l["farmacia"]), "documento": l["documento"],
            "prontuario": "", "paciente": "", "unidade": "", "sala": "", "especialidade": "",
            "codigo_aghu": l["codigo_aghu"] or "", "descricao": l["descricao"] or "", "lote": l["nLote"] or "",
            "validade": l["dVal"], "serie": l["numero_serie"] or "", "por": l["por"] or "",
            "situacao": sit, "conta": l["situacao"] not in NAO_CONTAM,
            "recebido_por": (l["conferida_nome"] or l["conferida_por"] or "") if l["situacao"] == "recebido" else "",
            "situacao_atual": _atual(l), "id_unidade": l["id_unidade"],
            "chave_farmacia": l["farmacia"],
        })
    return saida


def _dispensacoes(inicio: str, fim: str, farmacia: str, termo: str) -> list[dict]:
    params: list = [inicio, fim]
    filtro = ""
    if farmacia:
        filtro += " AND a.unidade = ?"
        params.append(farmacia)
    filtro += _busca(termo, params)
    linhas = db.consultar(
        f"""SELECT i.bipado_em AS data, i.bipado_por AS por, i.situacao, i.id_caixa, i.tratativa,
                   d.id_dispensacao AS documento, d.recebido_por, d.confirmada_por,
                   a.prontuario, a.paciente, a.unidade, a.sala, a.especialidade,
                   u.id_unidade, u.codigo_aghu, {_DESC} AS descricao, u.nLote, u.dVal, u.numero_serie,
                   u.status AS status_atual, u.farmacia AS farmacia_atual
            FROM dispensacao_itens i
            JOIN dispensacoes d ON d.id_dispensacao = i.id_dispensacao
            LEFT JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
            JOIN unidades u ON u.id_unidade = i.id_unidade
            LEFT JOIN materiais_mestre m ON m.codigo_aghu = u.codigo_aghu
            WHERE date(i.bipado_em) BETWEEN date(?) AND date(?){filtro}""", params)
    saida = []
    for l in linhas:
        farm = l["unidade"] or ""
        saida.append({
            "data": l["data"], "tipo": "Farmácia → Sala",
            "origem": rotulo_farmacia(farm) if farm in FARMACIAS else "Farmácia",
            "destino": f"Sala {l['sala']}" if l["sala"] else "Sala", "documento": l["documento"],
            "prontuario": l["prontuario"] or "", "paciente": l["paciente"] or "",
            "unidade": rotulo_unidade(farm) if farm else "", "sala": l["sala"] or "",
            "especialidade": l["especialidade"] or "",
            "codigo_aghu": l["codigo_aghu"] or "", "descricao": l["descricao"] or "", "lote": l["nLote"] or "",
            "validade": l["dVal"], "serie": l["numero_serie"] or "", "por": l["por"] or "",
            "situacao": _sit_disp(l["situacao"], l["tratativa"] or "")
                        + (f" · caixa {l['id_caixa']}" if l["id_caixa"] else ""),
            "conta": l["situacao"] not in NAO_CONTAM,
            "recebido_por": (l["recebido_por"] or l["confirmada_por"] or "") if l["situacao"] == "recebido" else "",
            "situacao_atual": _atual(l), "id_unidade": l["id_unidade"],
            "chave_farmacia": farm,
        })
    return saida


def movimentacoes(inicio: str, fim: str, tipo: str = "", farmacia: str = "", termo: str = "") -> list[dict]:
    inicio, fim = data_iso(inicio), data_iso(fim)
    farmacia = farmacia if farmacia in FARMACIAS else ""
    linhas: list[dict] = []
    if tipo in ("", "envios"):
        linhas += _envios(inicio, fim, farmacia, termo)
    if tipo in ("", "dispensacoes"):
        linhas += _dispensacoes(inicio, fim, farmacia, termo)
        from . import caixas_sala
        linhas += caixas_sala.para_relatorio(inicio, fim, farmacia, termo)
    linhas.sort(key=lambda l: l["data"] or "", reverse=True)
    return linhas


def resumo(linhas: list[dict]) -> dict:
    """Totais (só o que saiu de fato) por tipo/farmácia e por material AGHU."""
    validas = [l for l in linhas if l["conta"]]
    por_fluxo: dict[str, int] = {}
    por_aghu: dict[tuple, dict] = {}
    for l in validas:
        chave = f"{l['origem']} → {l['destino'] if l['tipo'].startswith('Almox') else 'Sala'}"
        por_fluxo[chave] = por_fluxo.get(chave, 0) + 1
        k = (l["codigo_aghu"], l["descricao"])
        reg = por_aghu.setdefault(k, {"codigo_aghu": l["codigo_aghu"] or "—", "descricao": l["descricao"],
                                       "envios": 0, "dispensacoes": 0})
        reg["envios" if l["tipo"].startswith("Almox") else "dispensacoes"] += 1
    return {
        "total": len(validas), "retirados": len(linhas) - len(validas),
        "envios": sum(1 for l in validas if l["tipo"].startswith("Almox")),
        "dispensacoes": sum(1 for l in validas if not l["tipo"].startswith("Almox")),
        "por_fluxo": sorted(por_fluxo.items()),
        "por_aghu": sorted(por_aghu.values(), key=lambda r: (r["codigo_aghu"] == "—", r["codigo_aghu"])),
    }


def para_exportar(linhas: list[dict]) -> list[dict]:
    return [{
        "Data/hora": data_hora_br(l["data"]), "Movimentação": l["tipo"], "Origem": l["origem"],
        "Destino": l["destino"], "Documento": l["documento"], "Código AGHU": l["codigo_aghu"],
        "Descrição AGHU": l["descricao"], "Lote": l["lote"], "Validade": data_br(l["validade"]) or "",
        "Nº de série": l["serie"], "Prontuário": l["prontuario"], "Paciente": l["paciente"],
        "Unidade": l["unidade"], "Sala": l["sala"], "Especialidade": l["especialidade"],
        "Dispensado por": l["por"], "Situação da movimentação": l["situacao"],
        "Recebido por": l["recebido_por"], "Situação atual da unidade": l["situacao_atual"],
        "ID da unidade": l["id_unidade"],
    } for l in linhas]


def pdf(linhas: list[dict], inicio: str, fim: str, filtros_txt: str) -> bytes:
    from ..pdf_simples import tabela
    r = resumo(linhas)
    seta = lambda t: str(t or "").replace("→", ">")   # a fonte do PDF não tem a seta
    linhas = [{k: (seta(v) if isinstance(v, str) else v) for k, v in l.items()} for l in linhas]
    r["por_fluxo"] = [(seta(k), v) for k, v in r["por_fluxo"]]
    return tabela(
        titulo="Movimentações de dispensa",
        subtitulo=f"Período: {data_br(data_iso(inicio))} a {data_br(data_iso(fim))} · {filtros_txt}",
        informacoes=[("Total", f"{r['total']} unidade(s) movimentada(s) · {r['envios']} almoxarifado > farmácia · "
                               f"{r['dispensacoes']} farmácia > sala"
                               + (f" · {r['retirados']} retirada(s) antes de sair" if r["retirados"] else ""))]
                    + [(k, f"{v} unidade(s)") for k, v in r["por_fluxo"]],
        colunas=[("Data", 1.2), ("Movimentação", 1.45), ("Destino", 1.4), ("Prontuário", 1.25),
                 ("AGHU", 1.0), ("Descrição AGHU", 2.7), ("Lote", 1.05), ("Validade", 1.25),
                 ("Nº série", 1.0), ("Por", .85), ("Situação", 2.0)],
        linhas=[[data_hora_br(l["data"]), l["tipo"], l["destino"], l["prontuario"], l["codigo_aghu"],
                 l["descricao"], l["lote"], data_br(l["validade"]) or "", l["serie"], l["por"], l["situacao"]]
                for l in linhas],
        quebrar_linhas=True,
        totais=[f"{r['total']} unidade(s) no período"],
        rodape="TraceOPME · Consultas - Movimentações de dispensa",
    )
