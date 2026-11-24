"""v18.37: trocar a peça registrada num uso, quando o bipe pegou a errada.

Caso real (HC-UFPE, 18/11/2026): a farmácia dispensou uma unidade para o
paciente, a sala deu ciência, e o bipe do uso consumiu OUTRA unidade do mesmo
produto — parada no estoque de outra farmácia ou ainda no almoxarifado —,
gravando "uso sem dispensação". A unidade dispensada ficou presa na sala e
virou pendência de devolução.

Consertar isso à mão exigia três telas e a ordem certa. Aqui é uma operação só:
a peça que a farmácia dispensou passa a ser a utilizada, e a que foi consumida
por engano volta para o estoque de onde saiu. Nada é apagado — o uso original
continua no histórico das duas unidades, marcado como corrigido.
"""
from __future__ import annotations

from .. import db
from ..domain import (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, EM_SALA, TRANSITO_SALA,
                      UTILIZADO, rotulo)
from ..utils import texto

NA_SALA = (EM_SALA, TRANSITO_SALA)
_CAMPOS = """u.id_unidade, u.codigo_aghu, u.nLote, u.dVal, u.status, u.farmacia, u.id_caixa,
             COALESCE(NULLIF(u.descritivo_hospital, ''), u.xProd) AS material"""


def _unidade(id_unidade: str) -> dict | None:
    return db.consultar_um(f"SELECT {_CAMPOS} FROM unidades u WHERE u.id_unidade = ?",
                           (texto(id_unidade),))


def _estado_antes_do_uso(id_unidade: str) -> str:
    """Para onde a peça volta: a situação que ela tinha antes do uso."""
    anterior = db.escalar(
        """SELECT status_anterior FROM eventos
           WHERE id_unidade = ? AND tipo = 'registrar_uso' AND COALESCE(status_anterior,'') <> ''
           ORDER BY id_evento DESC LIMIT 1""", (texto(id_unidade),))
    if texto(anterior) in (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA):
        return texto(anterior)
    return EM_ESTOQUE_RECEBIMENTO


def pendencias(id_atendimento: str) -> list[dict]:
    """Usos que parecem ter pegado a peça errada, com as trocas possíveis.

    Um uso entra aqui quando foi registrado "sem dispensação" neste atendimento
    e existe, no mesmo atendimento, peça do MESMO código AGHU que a farmácia
    dispensou e continua na sala sem uso.
    """
    id_atendimento = texto(id_atendimento)
    if not id_atendimento:
        return []
    usados = db.consultar(
        f"""SELECT {_CAMPOS}, e.data_evento AS usado_em, e.usuario AS usado_por
            FROM unidades u
            JOIN eventos e ON e.id_unidade = u.id_unidade AND e.tipo = 'saida_sem_dispensacao'
                          AND e.id_atendimento = ?
            WHERE u.id_atendimento = ? AND u.status = ?
            ORDER BY e.data_evento""",
        (id_atendimento, id_atendimento, UTILIZADO))
    if not usados:
        return []
    na_sala = db.consultar(
        f"""SELECT {_CAMPOS} FROM unidades u
            WHERE u.id_atendimento = ? AND u.status IN (?, ?)
            ORDER BY u.nLote""",
        (id_atendimento, EM_SALA, TRANSITO_SALA))
    saida = []
    for uso in usados:
        trocas = []
        for n in na_sala:
            if texto(n["id_caixa"]) or not _combinam(uso, n):
                continue
            # v18.37.1: no banco do HC-UFPE havia a mesma peça cadastrada com o
            # AGHU trocado (92259 e 92529). A troca vale, mas a tela avisa.
            trocas.append({**n, "aghu_diferente": texto(n["codigo_aghu"]) != texto(uso["codigo_aghu"])})
        if trocas:
            saida.append({**uso, "volta_para": rotulo(_estado_antes_do_uso(uso["id_unidade"])),
                          "trocas": trocas})
    return saida


def _combinam(usado: dict, na_sala: dict) -> bool:
    """Mesma peça: pelo código AGHU, ou pelo par lote + validade."""
    if texto(usado["codigo_aghu"]) and texto(usado["codigo_aghu"]) == texto(na_sala["codigo_aghu"]):
        return True
    return (bool(texto(usado["nLote"])) and texto(usado["nLote"]) == texto(na_sala["nLote"])
            and texto(usado["dVal"]) == texto(na_sala["dVal"]))


def trocar(id_usado: str, id_na_sala: str, usuario: str, motivo: str) -> tuple[bool, str]:
    """A peça da sala passa a ser a utilizada; a outra volta ao estoque de origem."""
    motivo = texto(motivo)
    if len(motivo) < 10:
        return False, "Descreva o motivo da correção com mais detalhe — ele fica na auditoria."
    usado, na_sala = _unidade(id_usado), _unidade(id_na_sala)
    if not usado or not na_sala:
        return False, "Material não encontrado."
    if usado["status"] != UTILIZADO:
        return False, (f"A peça a corrigir não está como utilizada "
                       f"(situação: “{rotulo(usado['status'])}”).")
    if na_sala["status"] not in NA_SALA:
        return False, (f"A peça que entraria no lugar não está na sala "
                       f"(situação: “{rotulo(na_sala['status'])}”).")
    if texto(na_sala["id_caixa"]):
        return False, "A peça da sala está dentro de uma caixa de consignado — use a caixa."
    ida_usado = db.escalar("SELECT id_atendimento FROM unidades WHERE id_unidade = ?", (texto(id_usado),))
    ida_sala = db.escalar("SELECT id_atendimento FROM unidades WHERE id_unidade = ?", (texto(id_na_sala),))
    if not texto(ida_usado):
        return False, "Este uso não está ligado a um procedimento."
    if ida_usado != ida_sala:
        return False, "As duas peças precisam ser do mesmo procedimento."
    atendimento = {"id_atendimento": ida_usado}
    if not _combinam(usado, na_sala):
        return False, ("As peças são de materiais diferentes (AGHU "
                       f"{usado['codigo_aghu']} e {na_sala['codigo_aghu']}, lotes "
                       f"{usado['nLote'] or '—'} e {na_sala['nLote'] or '—'}).")

    ida = atendimento["id_atendimento"]
    volta_para = _estado_antes_do_uso(id_usado)
    quando = db.escalar(
        """SELECT data_evento FROM eventos WHERE id_unidade = ? AND tipo = 'registrar_uso'
           ORDER BY id_evento DESC LIMIT 1""", (texto(id_usado),)) or db.agora()
    quem_bipou = db.escalar(
        """SELECT usuario FROM eventos WHERE id_unidade = ? AND tipo = 'registrar_uso'
           ORDER BY id_evento DESC LIMIT 1""", (texto(id_usado),)) or usuario
    agora = db.agora()

    with db.transacao() as conn:
        # 1. a peça dispensada passa a ser a utilizada, guardando a hora do uso real
        conn.execute("""UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                        WHERE id_unidade = ?""", (UTILIZADO, agora, usuario, id_na_sala))
        db.registrar_evento(
            conn, tipo="registrar_uso", id_unidade=texto(id_na_sala), id_atendimento=ida,
            usuario=quem_bipou, status_anterior=na_sala["status"], status_novo=UTILIZADO,
            observacao=(f"Correção do registro: esta é a peça que a farmácia dispensou para o "
                        f"paciente. Uso bipado em {quando[:16].replace('T', ' ')} tinha ficado na "
                        f"unidade {id_usado} (lote {usado['nLote'] or '—'}). Motivo: {motivo}"))

        # 2. a peça consumida por engano volta para onde estava
        conn.execute("""UPDATE unidades SET status = ?, id_atendimento = NULL,
                               atualizado_em = ?, atualizado_por = ?
                        WHERE id_unidade = ?""", (volta_para, agora, usuario, id_usado))
        db.registrar_evento(
            conn, tipo="uso_corrigido", id_unidade=texto(id_usado), id_atendimento=ida,
            usuario=usuario, status_anterior=UTILIZADO, status_novo=volta_para,
            observacao=(f"Uso corrigido: esta peça não foi usada no paciente — quem foi usada é a "
                        f"unidade {id_na_sala} (lote {na_sala['nLote'] or '—'}), dispensada pela "
                        f"farmácia. Volta para “{rotulo(volta_para)}”. Motivo: {motivo}"))

        # 3. some a pendência de "uso sem dispensação" da peça corrigida
        from . import usos_sem_dispensacao
        usos_sem_dispensacao.cancelar(conn, texto(id_usado), f"Uso corrigido: {motivo}")

        # 4. se a peça certa estava na lista de não utilizados, sai de lá
        conn.execute(
            """UPDATE devolucao_itens SET situacao = 'removido', resolvido_em = ?, resolvido_por = ?,
                      motivo = ? WHERE id_unidade = ? AND situacao = 'pendente'""",
            (agora, usuario, "Foi usada no paciente (correção de registro)", texto(id_na_sala)))

    return True, (f"Corrigido: a peça do lote {na_sala['nLote'] or '—'} passou a constar como "
                  f"utilizada, e a do lote {usado['nLote'] or '—'} voltou para "
                  f"“{rotulo(volta_para)}”.")
