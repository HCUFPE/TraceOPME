"""v17 — materiais cuja caixa precisa ser recolhida e entregue ao paciente.

A lista é de códigos AGHU, mantida na Administração. Ao bipar o uso de um
material desses, a tela mostra um aviso vermelho e quem está bipando dá ciência
de que vai recolher a caixa e entregar ao paciente. A ciência fica gravada como
evento (quem, quando, qual item) — e o atendimento só encerra com todas dadas.
"""

import re

from .. import db
from ..domain import UTILIZADO
from ..utils import texto
from . import materiais


def _normalizar(codigo) -> str:
    return texto(codigo).strip().upper()


def exige(codigo_aghu) -> bool:
    codigo = _normalizar(codigo_aghu)
    if not codigo:
        return False
    return bool(db.escalar(
        "SELECT COUNT(*) FROM aghu_entrega_paciente WHERE UPPER(codigo_aghu) = ?", (codigo,)))


def listar() -> list[dict]:
    linhas = db.consultar(
        """SELECT e.codigo_aghu, e.observacao, e.criado_em, e.criado_por,
                  m.descritivo_hospital
           FROM aghu_entrega_paciente e
           LEFT JOIN materiais_mestre m ON UPPER(m.codigo_aghu) = UPPER(e.codigo_aghu)
           ORDER BY e.codigo_aghu""")
    return linhas


def marcar(codigos_texto: str, observacao: str, usuario: str) -> tuple[bool, str]:
    """Acrescenta um ou vários códigos (separados por espaço, vírgula, ; ou linha)."""
    codigos = [c for c in (_normalizar(x) for x in re.split(r"[\s,;]+", texto(codigos_texto))) if c]
    if not codigos:
        return False, "Informe pelo menos um código AGHU."
    novos, repetidos, sem_catalogo = 0, 0, []
    with db.transacao() as conn:
        for codigo in dict.fromkeys(codigos):
            if conn.execute("SELECT 1 FROM aghu_entrega_paciente WHERE UPPER(codigo_aghu) = ?",
                            (codigo,)).fetchone():
                repetidos += 1
                continue
            conn.execute(
                "INSERT INTO aghu_entrega_paciente (codigo_aghu, observacao, criado_em, criado_por)"
                " VALUES (?,?,?,?)", (codigo, texto(observacao), db.agora(), usuario))
            db.registrar_evento(conn, tipo="entrega_paciente_marcado", usuario=usuario,
                                observacao=f"AGHU {codigo}")
            novos += 1
            if not materiais.descritivo_hospital(codigo):
                sem_catalogo.append(codigo)
    partes = [f"{novos} código(s) incluído(s)"]
    if repetidos:
        partes.append(f"{repetidos} já estavam na lista")
    if sem_catalogo:
        partes.append("não encontrados no catálogo (confira a digitação): " + ", ".join(sem_catalogo))
    return True, " · ".join(partes) + "."


def desmarcar(codigo_aghu: str, usuario: str) -> tuple[bool, str]:
    codigo = _normalizar(codigo_aghu)
    with db.transacao() as conn:
        apagados = conn.execute(
            "DELETE FROM aghu_entrega_paciente WHERE UPPER(codigo_aghu) = ?", (codigo,)).rowcount
        if apagados:
            db.registrar_evento(conn, tipo="entrega_paciente_desmarcado", usuario=usuario,
                                observacao=f"AGHU {codigo}")
    return (True, f"AGHU {codigo} saiu da lista.") if apagados else (False, "Código não estava na lista.")


def _uso_atual(id_unidade: str) -> dict | None:
    return db.consultar_um(
        """SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.id_atendimento, u.status,
                  (SELECT MAX(id_evento) FROM eventos
                    WHERE id_unidade = u.id_unidade AND tipo = 'registrar_uso') AS evento_uso
           FROM unidades u WHERE u.id_unidade = ?""", (texto(id_unidade),))


def registrar_ciencia(id_unidade: str, usuario: str) -> tuple[bool, str]:
    uso = _uso_atual(id_unidade)
    if not uso or uso["status"] != UTILIZADO:
        return False, "Este item não está registrado como utilizado."
    if not exige(uso["codigo_aghu"]):
        return False, "Este material não exige entrega da caixa ao paciente."
    if tem_ciencia(uso):
        return True, "Ciência já registrada."
    with db.transacao() as conn:
        db.registrar_evento(
            conn, tipo="ciencia_entrega_paciente", id_unidade=uso["id_unidade"],
            id_atendimento=uso["id_atendimento"], usuario=usuario,
            observacao="Ciente: recolher a caixa e entregar ao paciente.")
    return True, "Ciência registrada: a caixa deste material vai para o paciente."


def tem_ciencia(uso: dict) -> bool:
    return bool(db.escalar(
        """SELECT COUNT(*) FROM eventos WHERE id_unidade = ? AND tipo = 'ciencia_entrega_paciente'
           AND id_evento > ?""", (uso["id_unidade"], uso["evento_uso"] or 0)))


def do_atendimento(id_atendimento: str) -> list[dict]:
    """Itens usados neste atendimento que exigem entrega da caixa, com a ciência."""
    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.codigo_aghu, u.xProd, u.nLote, u.descritivo_hospital,
                   (SELECT MAX(id_evento) FROM eventos
                     WHERE id_unidade = u.id_unidade AND tipo = 'registrar_uso') AS evento_uso
            FROM unidades u
            JOIN aghu_entrega_paciente e ON UPPER(e.codigo_aghu) = UPPER(u.codigo_aghu)
            WHERE u.id_atendimento = ? AND u.status = '{UTILIZADO}'
            ORDER BY u.xProd""", (texto(id_atendimento),))
    for linha in linhas:
        ciencia = db.consultar_um(
            """SELECT usuario, data_evento FROM eventos WHERE id_unidade = ?
               AND tipo = 'ciencia_entrega_paciente' AND id_evento > ?
               ORDER BY id_evento DESC LIMIT 1""", (linha["id_unidade"], linha["evento_uso"] or 0))
        linha["ciencia_por"] = ciencia["usuario"] if ciencia else ""
        linha["ciencia_em"] = ciencia["data_evento"] if ciencia else ""
    return linhas


def pendentes_de_ciencia(id_atendimento: str) -> list[dict]:
    return [l for l in do_atendimento(id_atendimento) if not l["ciencia_por"]]
