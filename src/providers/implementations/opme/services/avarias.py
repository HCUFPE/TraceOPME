"""v18 — material com problema registrado no paciente (caiu no chão, veio danificado…).

Na sala, o material que caiu ou veio quebrado é bipado na conta do paciente do
mesmo jeito; o que faltava era SINALIZAR isso de um jeito simples: antes do bip
(escolhendo o problema do próximo item) ou depois, no item da lista "Já
registrado neste paciente". Fica um evento `avaria_sinalizada` no histórico da
unidade (motivo + detalhe + quem).

v18.4.7: não gera mais alerta. O registro alimenta o indicador "Problemas com
material na sala" (Indicadores → Qualidade), para identificar os maiores problemas.
"""

from __future__ import annotations

from .. import db
from ..domain import UTILIZADO
from ..utils import texto

MOTIVOS_AVARIA = [
    "Caiu no chão / contaminou",
    "Veio danificado / embalagem violada",
    "Defeito ao usar (não funcionou)",
    "Outro problema",
]


def sinalizar(id_unidade: str, id_atendimento: str, motivo: str, detalhe: str, usuario: str) -> tuple[bool, str]:
    motivo, detalhe = texto(motivo), texto(detalhe)
    if motivo not in MOTIVOS_AVARIA:
        return False, "Escolha o problema do material."
    if motivo == "Outro problema" and len(detalhe) < 3:
        return False, "Descreva o problema quando escolher “Outro problema”."
    u = db.consultar_um(
        """SELECT u.id_unidade, u.status, u.id_atendimento, u.xProd, u.descritivo_hospital, u.nLote,
                  u.codigo_aghu, a.prontuario, a.sala, a.unidade
           FROM unidades u LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE u.id_unidade = ?""", (texto(id_unidade),))
    if not u or u["status"] != UTILIZADO or texto(u["id_atendimento"]) != texto(id_atendimento):
        return False, "Este material não está registrado neste paciente."
    with db.transacao() as conn:
        db.registrar_evento(conn, tipo="avaria_sinalizada", id_unidade=u["id_unidade"],
                            id_atendimento=u["id_atendimento"], status_anterior=UTILIZADO, status_novo=UTILIZADO,
                            usuario=usuario, motivo=motivo, observacao=detalhe or None)
    return True, f"Problema registrado no material: {motivo}."


def do_atendimento(id_atendimento: str) -> dict[str, dict]:
    """Última sinalização de cada unidade do atendimento: {id_unidade: {motivo, detalhe, por, quando}}."""
    linhas = db.consultar(
        """SELECT e.id_unidade, e.motivo, e.observacao, e.usuario, e.data_evento
           FROM eventos e
           JOIN (SELECT id_unidade, MAX(id_evento) AS ultimo FROM eventos
                 WHERE tipo = 'avaria_sinalizada' AND id_atendimento = ? GROUP BY id_unidade) x
             ON x.ultimo = e.id_evento""", (texto(id_atendimento),))
    return {l["id_unidade"]: {"motivo": l["motivo"], "detalhe": l["observacao"] or "", "por": l["usuario"],
                              "quando": l["data_evento"]} for l in linhas}
