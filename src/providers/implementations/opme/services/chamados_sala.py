"""v18.3 — Chamados da sala de procedimento para o QG da enfermagem.

De dentro da sala (ficha do procedimento) a equipe chama o MAQUEIRO ou a
equipe de LIMPEZA. O chamado aparece no QG da enfermagem, que direciona alguém
(nome do maqueiro / da equipe) e marca como atendido. A sala acompanha a
situação na própria ficha, e a Central das salas mostra os chamados abertos.

    aberto → direcionado → atendido      (ou cancelado, pela sala ou pelo QG)
"""

from __future__ import annotations

from datetime import datetime

from .. import db
from ..config import UNIDADES_ATIVAS, rotulo_unidade
from ..utils import gerar_id, texto

TIPOS = {
    "maqueiro": {"rotulo": "Maqueiro", "icone": "🛏",
                 "motivos": ["Buscar o paciente", "Levar o paciente para a RPA",
                             "Levar o paciente para a enfermaria / UTI", "Transporte de material / exame", "Outro"]},
    "limpeza": {"rotulo": "Limpeza", "icone": "🧹",
                "motivos": ["Limpeza entre procedimentos", "Limpeza terminal da sala",
                            "Derramamento / sujidade urgente", "Recolher resíduos", "Outro"]},
}
STATUS = {"aberto": "Aguardando o QG", "direcionado": "A caminho", "atendido": "Atendido", "cancelado": "Cancelado"}
ABERTOS = ("aberto", "direcionado")


def _minutos(desde: str, agora: datetime) -> int:
    try:
        return max(0, int((agora - datetime.fromisoformat(texto(desde).replace(" ", "T")[:19])).total_seconds() // 60))
    except ValueError:
        return 0


def _formatar(c: dict, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now()
    c = dict(c)
    t = TIPOS.get(c["tipo"], {"rotulo": c["tipo"], "icone": "•"})
    c["tipo_rotulo"], c["icone"] = t["rotulo"], t["icone"]
    c["status_rotulo"] = STATUS.get(c["status"], c["status"])
    c["unidade_rotulo"] = rotulo_unidade(c["unidade"])
    c["espera_min"] = _minutos(c["criado_em"], agora) if c["status"] == "aberto" else None
    c["a_caminho_min"] = _minutos(c["direcionado_em"], agora) if c["status"] == "direcionado" else None
    fim = c.get("atendido_em") or ""
    c["tempo_total_min"] = (_minutos(c["criado_em"], datetime.fromisoformat(fim.replace(" ", "T")[:19]))
                            if fim else None)
    return c


def chamar(*, tipo: str, unidade: str, sala: str, usuario: str, motivo: str = "", observacao: str = "",
           id_atendimento: str = "") -> tuple[bool, str]:
    tipo = texto(tipo).lower()
    if tipo not in TIPOS:
        return False, "Escolha: maqueiro ou limpeza."
    unidade, sala = texto(unidade).upper(), texto(sala)
    if unidade not in UNIDADES_ATIVAS or not sala:
        return False, "Sala não identificada para o chamado."
    motivo = texto(motivo)
    if motivo == "Outro" and not texto(observacao):
        return False, "Escreva o que precisa no campo de observação."
    # Já tem um chamado igual aberto para a sala: não duplica.
    igual = db.consultar_um("SELECT * FROM chamados_sala WHERE tipo = ? AND unidade = ? AND sala = ? "
                            f"AND status IN {ABERTOS} ORDER BY criado_em DESC LIMIT 1", (tipo, unidade, sala))
    if igual:
        return False, (f"Já existe um chamado de {TIPOS[tipo]['rotulo'].lower()} aberto para esta sala "
                       f"({STATUS[igual['status']].lower()}). Aguarde ou cancele o anterior.")
    novo = gerar_id("CH")
    agora = db.agora()
    with db.transacao() as conn:
        conn.execute("""INSERT INTO chamados_sala (id_chamado, tipo, motivo, observacao, unidade, sala, id_atendimento,
                        status, criado_em, criado_por) VALUES (?,?,?,?,?,?,?, 'aberto', ?, ?)""",
                     (novo, tipo, motivo, texto(observacao), unidade, sala, texto(id_atendimento) or None,
                      agora, usuario))
        db.registrar_evento(conn, tipo="chamado_sala", id_atendimento=texto(id_atendimento) or None, usuario=usuario,
                            motivo=f"{TIPOS[tipo]['rotulo']}: {motivo or '—'}",
                            observacao=f"{rotulo_unidade(unidade)} — sala {sala}. {texto(observacao)}".strip())
    return True, f"{TIPOS[tipo]['rotulo']} chamado. O QG da enfermagem foi avisado."


def buscar(id_chamado: str) -> dict | None:
    c = db.consultar_um("SELECT * FROM chamados_sala WHERE id_chamado = ?", (texto(id_chamado),))
    return _formatar(c) if c else None


def _mudar(id_chamado: str, de: tuple, sql: str, params: tuple, msg: str, tipo_evento: str,
           usuario: str, detalhe: str = "") -> tuple[bool, str]:
    c = buscar(id_chamado)
    if not c:
        return False, "Chamado não encontrado."
    if c["status"] not in de:
        return False, f"Este chamado já está {c['status_rotulo'].lower()}."
    with db.transacao() as conn:
        conn.execute(f"UPDATE chamados_sala SET {sql} WHERE id_chamado = ?", (*params, c["id_chamado"]))
        db.registrar_evento(conn, tipo=tipo_evento, id_atendimento=c["id_atendimento"], usuario=usuario,
                            motivo=f"{c['tipo_rotulo']} — sala {c['sala']}", observacao=detalhe)
    return True, msg


def direcionar(id_chamado: str, responsavel: str, usuario: str) -> tuple[bool, str]:
    responsavel = texto(responsavel)
    if not responsavel:
        return False, "Informe quem vai (nome do maqueiro / da equipe)."
    return _mudar(id_chamado, ("aberto", "direcionado"),
                  "status = 'direcionado', direcionado_em = ?, direcionado_por = ?, responsavel = ?",
                  (db.agora(), usuario, responsavel), f"Direcionado para {responsavel}.", "chamado_direcionado",
                  usuario, responsavel)


def atender(id_chamado: str, usuario: str) -> tuple[bool, str]:
    return _mudar(id_chamado, ABERTOS, "status = 'atendido', atendido_em = ?, atendido_por = ?",
                  (db.agora(), usuario), "Chamado atendido.", "chamado_atendido", usuario)


def cancelar(id_chamado: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    return _mudar(id_chamado, ABERTOS,
                  "status = 'cancelado', cancelado_em = ?, cancelado_por = ?, motivo_cancelamento = ?",
                  (db.agora(), usuario, texto(motivo)), "Chamado cancelado.", "chamado_cancelado", usuario,
                  texto(motivo))


def da_sala(unidade: str, sala: str, *, so_abertos: bool = False, limite: int = 10) -> list[dict]:
    filtro = f"AND status IN {ABERTOS}" if so_abertos else "AND substr(criado_em, 1, 10) = date('now', 'localtime')"
    agora = datetime.now()
    return [_formatar(c, agora) for c in db.consultar(
        f"SELECT * FROM chamados_sala WHERE unidade = ? AND sala = ? {filtro} ORDER BY criado_em DESC LIMIT ?",
        (texto(unidade).upper(), texto(sala), limite))]


def abertos_por_sala() -> dict:
    """{(unidade, sala): [chamados abertos]} — para a Central das salas."""
    agora = datetime.now()
    saida: dict = {}
    for c in db.consultar(f"SELECT * FROM chamados_sala WHERE status IN {ABERTOS} ORDER BY criado_em"):
        saida.setdefault((c["unidade"], c["sala"]), []).append(_formatar(c, agora))
    return saida


def painel_qg(unidade: str = "") -> dict:
    """O quadro do QG: aguardando, a caminho e atendidos hoje."""
    agora = datetime.now()
    cond, params = "", []
    if texto(unidade).upper() in UNIDADES_ATIVAS:
        cond, params = "AND unidade = ?", [texto(unidade).upper()]
    abertos = [_formatar(c, agora) for c in db.consultar(
        f"SELECT * FROM chamados_sala WHERE status IN {ABERTOS} {cond} ORDER BY criado_em", tuple(params))]
    hoje = [_formatar(c, agora) for c in db.consultar(
        f"""SELECT * FROM chamados_sala WHERE status IN ('atendido','cancelado') {cond}
            AND substr(COALESCE(atendido_em, cancelado_em), 1, 10) = date('now', 'localtime')
            ORDER BY COALESCE(atendido_em, cancelado_em) DESC LIMIT 60""", tuple(params))]
    atendidos = [c for c in hoje if c["status"] == "atendido"]
    tempos = [c["tempo_total_min"] for c in atendidos if c["tempo_total_min"] is not None]
    return {
        "aguardando": [c for c in abertos if c["status"] == "aberto"],
        "a_caminho": [c for c in abertos if c["status"] == "direcionado"],
        "finalizados": hoje,
        "resumo": {"aguardando": sum(1 for c in abertos if c["status"] == "aberto"),
                   "a_caminho": sum(1 for c in abertos if c["status"] == "direcionado"),
                   "atendidos_hoje": len(atendidos),
                   "tempo_medio": round(sum(tempos) / len(tempos)) if tempos else None},
        "unidade": texto(unidade).upper() if texto(unidade).upper() in UNIDADES_ATIVAS else "",
        "unidades": {k: rotulo_unidade(k) for k in UNIDADES_ATIVAS},
        "atualizado_em": agora.strftime("%H:%M:%S"),
        "ultimo_id": max((c["criado_em"] + c["id_chamado"] for c in abertos), default=""),
    }
