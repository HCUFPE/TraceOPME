"""v18.6 — Nota de Consumo no AGHU (farmácia).

v18.7: o robô volta a rodar no computador de quem lança (o mesmo robô instalado da NF).
"Lançar no AGHU" gera um código de uso único e o link traceopme-aghu://lancar/… com
k = "consumo"; o robô busca os materiais em /api/robo-aghu/consumo e, no fim, conta
em /api/robo-aghu/retorno se a lista foi gravada.

A farmácia pesquisa os prontuários com uso no dia, vê tudo o que foi bipado para cada
paciente (agrupado por código AGHU) e manda o robô lançar na tela "Materiais Consumidos
Cirurgia" do AGHU. A pessoa abre a cirurgia no AGHU; o robô só preenche material e
quantidade e para antes de gravar (quem grava é a pessoa).

v18.8: o mesmo serviço atende a REQUISIÇÃO DE MATERIAL (RM). Cada documento tem a sua
situação no atendimento (colunas aghu_consumo_* e aghu_rm_*). A RM precisa do LOTE:
o robô recebe, por material, os lotes usados no paciente com a quantidade de cada um.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timedelta

from .. import db, log
from ..domain import UTILIZADO
from ..utils import data_br, texto

HORAS_TOKEN = 12

ROTULO = {"": "Não lançada", "em_lancamento": "Em lançamento", "lancada": "Lançada no AGHU"}


def prontuarios_com_uso(data: str, unidade: str = "", pendentes: bool = False) -> list[dict]:
    """Atendimentos do dia com material utilizado (bipado no paciente)."""
    cond, params = ["a.data_procedimento = ?"], [texto(data)]
    if texto(unidade):
        cond.append("a.unidade = ?")
        params.append(texto(unidade))
    if pendentes:   # v18.8: falta lançar a nota de consumo OU a RM
        cond.append("(COALESCE(a.aghu_consumo_status, '') <> 'lancada' OR COALESCE(a.aghu_rm_status, '') <> 'lancada')")
    linhas = db.consultar(
        f"""SELECT a.id_atendimento, a.prontuario, a.paciente, a.unidade, a.sala, a.especialidade, a.data_procedimento,
                   a.hora_inicio, a.status, a.uso_finalizado_em, COALESCE(a.aghu_consumo_status, '') AS consumo_status,
                   a.aghu_consumo_lancado_em, a.aghu_consumo_lancado_por, a.aghu_consumo_iniciado_por,
                   COALESCE(a.aghu_rm_status, '') AS rm_status, a.aghu_rm_lancado_em, a.aghu_rm_lancado_por,
                   a.aghu_rm_iniciado_por,
                   COUNT(u.id_unidade) AS qtd_itens,
                   COUNT(DISTINCT COALESCE(NULLIF(u.codigo_aghu, ''), u.id_unidade)) AS qtd_materiais,
                   SUM(CASE WHEN COALESCE(u.codigo_aghu, '') = '' THEN 1 ELSE 0 END) AS sem_codigo
            FROM atendimentos a JOIN unidades u ON u.id_atendimento = a.id_atendimento AND u.status = ?
            WHERE {' AND '.join(cond)}
            GROUP BY a.id_atendimento
            ORDER BY a.unidade, a.sala, a.hora_inicio, a.paciente""", (UTILIZADO, *params))
    for l in linhas:
        l["consumo_rotulo"] = ROTULO.get(l["consumo_status"], l["consumo_status"])
        l["rm_rotulo"] = ROTULO.get(l["rm_status"], l["rm_status"])
    return linhas


def itens(id_atendimento: str) -> list[dict]:
    """O que foi bipado no paciente, agrupado por código AGHU (com os lotes)."""
    linhas = db.consultar(
        """SELECT COALESCE(u.codigo_aghu, '') AS codigo_aghu,
                  MAX(COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd)) AS descricao,
                  COUNT(*) AS quantidade,
                  GROUP_CONCAT(DISTINCT COALESCE(NULLIF(u.nLote, ''), '—')) AS lotes,
                  MAX(CASE WHEN u.tipo_entrada = 'consignado' THEN 1 ELSE 0 END) AS consignado,
                  GROUP_CONCAT(u.id_unidade) AS unidades
           FROM unidades u
           WHERE u.id_atendimento = ? AND u.status = ?
           GROUP BY CASE WHEN COALESCE(u.codigo_aghu, '') = '' THEN u.id_unidade ELSE u.codigo_aghu END
           ORDER BY descricao""", (texto(id_atendimento), UTILIZADO))
    for l in linhas:
        l["lotes"] = [x for x in (l["lotes"] or "").split(",") if x]
        l["unidades"] = (l["unidades"] or "").split(",")
    return linhas


def atendimento(id_atendimento: str) -> dict | None:
    return db.consultar_um("SELECT * FROM atendimentos WHERE id_atendimento = ?", (texto(id_atendimento),))


# v18.8: os dois documentos que a farmácia lança no AGHU a partir do que foi usado no paciente
DOCUMENTOS = {
    "consumo": {"prefixo": "aghu_consumo_", "nome": "Nota de consumo", "artigo": "a nota de consumo"},
    "rm": {"prefixo": "aghu_rm_", "nome": "Requisição de material (RM)", "artigo": "a requisição de material (RM)"},
}


def _doc(tipo: str) -> dict:
    return DOCUMENTOS.get(tipo or "consumo", DOCUMENTOS["consumo"])


def itens_por_lote(id_atendimento: str) -> list[dict]:
    """v18.8 (RM): por código AGHU, os lotes usados no paciente e a quantidade de cada lote."""
    linhas = db.consultar(
        """SELECT u.codigo_aghu, COALESCE(NULLIF(u.nLote, ''), '') AS lote, u.dVal AS validade, COUNT(*) AS quantidade,
                  MAX(COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd)) AS descricao
           FROM unidades u WHERE u.id_atendimento = ? AND u.status = ? AND COALESCE(u.codigo_aghu, '') <> ''
           GROUP BY u.codigo_aghu, lote ORDER BY descricao, lote""", (texto(id_atendimento), UTILIZADO))
    por_codigo: dict[str, dict] = {}
    for l in linhas:
        it = por_codigo.setdefault(l["codigo_aghu"], {"codigo": l["codigo_aghu"], "descricao": l["descricao"],
                                                      "quantidade": 0, "lotes": []})
        it["quantidade"] += l["quantidade"]
        it["lotes"].append({"lote": l["lote"], "validade": data_br(l["validade"]) if l["validade"] else "",
                            "quantidade": l["quantidade"]})
    return list(por_codigo.values())


def iniciar(id_atendimento: str, usuario: str) -> None:
    db.executar("""UPDATE atendimentos SET aghu_consumo_status = 'em_lancamento', aghu_consumo_iniciado_em = ?,
                   aghu_consumo_iniciado_por = ? WHERE id_atendimento = ? AND COALESCE(aghu_consumo_status,'') <> 'lancada'""",
                (db.agora(), usuario, texto(id_atendimento)))


def marcar(id_atendimento: str, acao: str, usuario: str, tipo: str = "consumo") -> tuple[bool, str]:
    """lancada | desfazer | (vazio: volta para não lançada, se estava em lançamento)."""
    d = _doc(tipo)
    p = d["prefixo"]
    at = atendimento(id_atendimento)
    if not at:
        return False, "Atendimento não encontrado."
    if acao == "lancada":
        db.executar(f"""UPDATE atendimentos SET {p}status = 'lancada', {p}lancado_em = ?, {p}lancado_por = ?,
                        {p}token = NULL WHERE id_atendimento = ?""", (db.agora(), usuario, at["id_atendimento"]))
        msg = f"{d['nome']} marcada como lançada no AGHU."
    elif acao == "desfazer":
        db.executar(f"""UPDATE atendimentos SET {p}status = '', {p}lancado_em = NULL, {p}lancado_por = NULL,
                        {p}token = NULL WHERE id_atendimento = ?""", (at["id_atendimento"],))
        msg = f"{d['nome']} voltou para não lançada."
    else:
        db.executar(f"""UPDATE atendimentos SET {p}status = '' WHERE id_atendimento = ?
                        AND {p}status = 'em_lancamento'""", (at["id_atendimento"],))
        msg = f"{d['nome']} continua não lançada."
    return True, msg


# ---------------------------------------------------------------- v18.7: robô no computador

def iniciar_local(id_atendimento: str, usuario: str, servidor: str, tipo: str = "consumo") -> tuple[bool, str, str]:
    """Gera o código e o link que o navegador entrega ao robô deste computador."""
    d = _doc(tipo)
    p = d["prefixo"]
    at = atendimento(id_atendimento)
    if not at:
        return False, "Atendimento não encontrado.", ""
    if texto(at.get(f"{p}status")) == "lancada":
        return False, f"{d['artigo'][0].upper() + d['artigo'][1:]} deste paciente já está marcada como lançada no AGHU.", ""
    if not [i for i in itens(id_atendimento) if i["codigo_aghu"]]:
        return False, "Nenhum material com código AGHU foi utilizado neste paciente.", ""
    servidor = texto(servidor).rstrip("/")
    if not servidor.startswith(("http://", "https://")):
        return False, "Endereço do servidor inválido.", ""
    token = texto(at.get(f"{p}token"))   # v18.7.2: reaproveita o código ainda válido
    if not (texto(at.get(f"{p}status")) == "em_lancamento" and token
            and texto(at.get(f"{p}token_expira")) > datetime.now().isoformat(timespec="seconds")):
        token = secrets.token_urlsafe(24)
    expira = (datetime.now() + timedelta(hours=HORAS_TOKEN)).isoformat(timespec="seconds")
    db.executar(f"""UPDATE atendimentos SET {p}status = 'em_lancamento', {p}iniciado_em = ?, {p}iniciado_por = ?,
                    {p}token = ?, {p}token_expira = ? WHERE id_atendimento = ?""",
                (db.agora(), usuario, token, expira, at["id_atendimento"]))
    dados = {"k": tipo if tipo in DOCUMENTOS else "consumo", "s": servidor, "c": at["id_atendimento"], "t": token,
             "n": texto(at["prontuario"]), "a": os.getenv("AGHU_URL", ""), "b": os.getenv("AGHU_NAVEGADOR", "")}
    bloco = base64.urlsafe_b64encode(json.dumps(dados, separators=(",", ":")).encode()).decode().rstrip("=")
    log.info(f"robô do AGHU chamado para {d['artigo']} do prontuário {at['prontuario']}", usuario)
    return True, (f"Abrindo o robô neste computador ({d['nome']}, prontuário {at['prontuario']}). Se o navegador "
                  "perguntar, clique em “Abrir”. Siga a janela preta."), f"traceopme-aghu://lancar/{bloco}"


def _token_valido(at: dict | None, token: str, tipo: str = "consumo") -> str:
    p = _doc(tipo)["prefixo"]
    if not at or not texto(token) or not texto(at.get(f"{p}token")) \
            or not secrets.compare_digest(texto(at.get(f"{p}token")), texto(token)):
        return "Código do robô inválido (já usado ou de outro lançamento)."
    if texto(at.get(f"{p}token_expira")) < datetime.now().isoformat(timespec="seconds"):
        return "O código do robô expirou. Clique de novo em “Lançar no AGHU” na Farmácia."
    return ""


def para_robo(id_atendimento: str, token: str, tipo: str = "consumo") -> dict:
    """O que o robô precisa: paciente, data e materiais (com código AGHU; na RM, com os lotes)."""
    at = atendimento(id_atendimento)
    motivo = _token_valido(at, token, tipo)
    if motivo:
        return {"ok": False, "mensagem": motivo}
    lista = itens(id_atendimento)
    if tipo == "rm":
        itens_robo = itens_por_lote(id_atendimento)
    else:
        itens_robo = [{"codigo": i["codigo_aghu"], "descricao": i["descricao"], "quantidade": i["quantidade"]}
                      for i in lista if i["codigo_aghu"]]
    return {
        "ok": True, "tipo": tipo,
        "atendimento": {"prontuario": at["prontuario"], "paciente": at.get("paciente") or "",
                        "data_br": data_br(at["data_procedimento"]) if at.get("data_procedimento") else "",
                        "sala": at.get("sala") or "", "unidade": at.get("unidade") or "",
                        "sem_codigo": [i["descricao"] for i in lista if not i["codigo_aghu"]]},
        "itens": itens_robo,
    }


def retorno(id_atendimento: str, token: str, gravou: bool, tipo: str = "consumo") -> tuple[bool, str]:
    d = _doc(tipo)
    p = d["prefixo"]
    at = atendimento(id_atendimento)
    motivo = _token_valido(at, token, tipo)
    if motivo:
        return False, motivo
    quem = at.get(f"{p}iniciado_por") or "robô"
    if gravou:
        db.executar(f"""UPDATE atendimentos SET {p}status = 'lancada', {p}lancado_em = ?, {p}lancado_por = ?,
                        {p}token = NULL, {p}token_expira = NULL WHERE id_atendimento = ?""",
                    (db.agora(), quem, at["id_atendimento"]))
        log.info(f"{d['artigo']} do prontuário {at['prontuario']} lançada no AGHU (robô)", quem)
        return True, f"{d['nome']} do prontuário {at['prontuario']} marcada como lançada no AGHU."
    db.executar(f"""UPDATE atendimentos SET {p}status = '', {p}token = NULL, {p}token_expira = NULL
                    WHERE id_atendimento = ?""", (at["id_atendimento"],))
    return True, f"{d['nome']} do prontuário {at['prontuario']} continua como não lançada no AGHU."
