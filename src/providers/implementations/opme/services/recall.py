"""Bloqueio de lote — o caso de uso que justifica a rastreabilidade inteira.

Quando o fornecedor ou a ANVISA anuncia um recall, duas perguntas precisam de
resposta em minutos:

1. **Onde está o material desse lote agora?** Para tirar de circulação antes de
   alguém usar. É a parte urgente.
2. **Em quem já foi implantado?** Para o hospital convocar os pacientes. Não é
   urgente no mesmo sentido, mas é a parte que não pode falhar.

Consultar por lote já respondia às duas. O que faltava era **impedir o uso**: a
consulta mostra onde está o material, mas nada impedia alguém de bipar e mandar
para a sala cinco minutos depois. Aqui o bloqueio é aplicado no motor de
bipagem, então nenhuma tela precisa lembrar de verificar.

O bloqueio não altera o estado das unidades de propósito. O material continua
onde está, contabilizado, e só para de andar — a decisão do que fazer com ele
(devolver ao fornecedor, baixar) é do almoxarifado, com o registro de sempre.
"""

from .. import db, log
from ..domain import UTILIZADO, rotulo
from ..utils import gerar_id, texto
from . import alertas


def _normalizar(valor) -> str:
    return texto(valor).upper()


def bloquear(dados: dict, usuario: str) -> tuple[bool, str]:
    lote = _normalizar(dados.get("nLote"))
    motivo = texto(dados.get("motivo"))
    if not lote:
        return False, "Informe o lote a bloquear."
    if len(motivo) < 10:
        return False, ("Descreva o motivo do bloqueio — ele aparece para quem tentar "
                       "bipar o material e fica na auditoria.")

    codigo_aghu = _normalizar(dados.get("codigo_aghu"))
    ja_ativo = db.consultar_um(
        """SELECT id_bloqueio FROM lotes_bloqueados
           WHERE status = 'ativo' AND nLote = ? AND COALESCE(codigo_aghu,'') = ?""",
        (lote, codigo_aghu),
    )
    if ja_ativo:
        return False, "Este lote já está bloqueado."

    id_bloqueio = gerar_id("BLQ")
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO lotes_bloqueados
               (id_bloqueio, nLote, codigo_aghu, fornecedor, motivo, referencia,
                status, criado_em, criado_por)
               VALUES (?,?,?,?,?,?,'ativo',?,?)""",
            (id_bloqueio, lote, codigo_aghu or None, texto(dados.get("fornecedor")) or None,
             motivo, texto(dados.get("referencia")) or None, db.agora(), usuario),
        )

    afetadas = unidades_do_lote(lote, codigo_aghu)
    em_circulacao = [u for u in afetadas if u["status"] != UTILIZADO]
    implantadas = [u for u in afetadas if u["status"] == UTILIZADO]

    # Cada área precisa saber que tem material parado para retirar de circulação.
    for modulo in ("almoxarifado", "farmacia", "sala-procedimento"):
        alertas.criar(
            modulo_destino=modulo,
            titulo=f"Lote {lote} bloqueado — retirar de circulação",
            mensagem=(
                f"Motivo: {motivo}\n"
                f"{len(em_circulacao)} unidade(s) ainda em circulação e "
                f"{len(implantadas)} já implantada(s) em paciente.\n"
                f"O sistema recusa qualquer movimentação deste lote até a liberação."
            ),
            usuario=usuario,
            link=f"/consultas/recall/{id_bloqueio}",
        )

    log.aviso(f"lote bloqueado · lote={lote} · aghu={codigo_aghu or 'todos'} · "
              f"em_circulacao={len(em_circulacao)} · implantadas={len(implantadas)} · "
              f"motivo={motivo}", usuario)

    return True, (f"Lote {lote} bloqueado. {len(em_circulacao)} unidade(s) em circulação "
                  f"e {len(implantadas)} já implantada(s) — veja a lista para agir.")


def liberar(id_bloqueio: str, usuario: str, motivo: str) -> tuple[bool, str]:
    if len(texto(motivo)) < 10:
        return False, "Descreva por que o lote está sendo liberado."
    bloqueio = buscar(id_bloqueio)
    if not bloqueio:
        return False, "Bloqueio não encontrado."
    if bloqueio["status"] != "ativo":
        return False, "Este bloqueio já foi liberado."

    with db.transacao() as conn:
        conn.execute(
            """UPDATE lotes_bloqueados
               SET status = 'liberado', liberado_em = ?, liberado_por = ?, motivo_liberacao = ?
               WHERE id_bloqueio = ?""",
            (db.agora(), usuario, texto(motivo), texto(id_bloqueio)),
        )
    log.aviso(f"lote liberado · lote={bloqueio['nLote']} · motivo={texto(motivo)}", usuario)
    return True, f"Lote {bloqueio['nLote']} liberado. O material volta a circular normalmente."


def buscar(id_bloqueio: str) -> dict | None:
    return db.consultar_um(
        "SELECT * FROM lotes_bloqueados WHERE id_bloqueio = ?", (texto(id_bloqueio),))


def listar(somente_ativos: bool = False) -> list[dict]:
    filtro = " WHERE status = 'ativo'" if somente_ativos else ""
    linhas = db.consultar(
        f"SELECT * FROM lotes_bloqueados{filtro} ORDER BY status, criado_em DESC")
    for linha in linhas:
        afetadas = unidades_do_lote(linha["nLote"], linha["codigo_aghu"] or "")
        linha["em_circulacao"] = sum(1 for u in afetadas if u["status"] != UTILIZADO)
        linha["implantadas"] = sum(1 for u in afetadas if u["status"] == UTILIZADO)
    return linhas


def bloqueio_do_item(nLote: str, codigo_aghu: str = "", conn=None) -> dict | None:
    """Bloqueio ativo que atinge este lote, se houver.

    Um bloqueio sem código AGHU vale para o lote em qualquer produto — é o que
    o fornecedor costuma informar num recall. Com o código, restringe ao produto.
    """
    lote = _normalizar(nLote)
    if not lote:
        return None
    sql = """SELECT * FROM lotes_bloqueados
           WHERE status = 'ativo' AND nLote = ?
             AND (COALESCE(codigo_aghu,'') = '' OR codigo_aghu = ?)
           ORDER BY criado_em DESC LIMIT 1"""
    params = (lote, _normalizar(codigo_aghu))
    if conn is not None:
        # v18.4.2: dentro da transação que vai mover o material — um recall
        # registrado entre a conferência e a gravação é visto aqui.
        r = conn.execute(sql, params).fetchone()
        return dict(r) if r else None
    return db.consultar_um(sql, params)


def bloqueadas(unidades: list[dict], conn=None) -> list[tuple[dict, dict]]:
    """v18.4.1: [(unidade, bloqueio)] das unidades cujo lote está em recall."""
    saida = []
    for u in unidades:
        b = bloqueio_do_item(u.get("nLote"), u.get("codigo_aghu"), conn)
        if b:
            saida.append((u, b))
    return saida


def mensagem_bloqueio(u: dict, b: dict) -> str:
    return (f"Lote {u.get('nLote')} BLOQUEADO: {b['motivo']}. Não movimente este material. "
            "Separe fisicamente e avise o almoxarifado, que registra a devolução ao fornecedor ou a baixa.")


def unidades_do_lote(nLote: str, codigo_aghu: str = "") -> list[dict]:
    """Toda unidade do lote, com onde está e em quem foi usada."""
    condicoes = ["UPPER(u.nLote) = ?"]
    params: list = [_normalizar(nLote)]
    if _normalizar(codigo_aghu):
        condicoes.append("UPPER(COALESCE(u.codigo_aghu,'')) = ?")
        params.append(_normalizar(codigo_aghu))

    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.codigo_barras, u.codigo_aghu, u.xProd, u.nLote, u.dVal,
                   u.numero_serie, u.fornecedor, u.status, u.farmacia, u.numero_nf,
                   a.prontuario, a.paciente, a.sala, a.data_procedimento,
                   (SELECT data_evento FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.tipo = 'registrar_uso' ORDER BY ev.id_evento DESC LIMIT 1) AS data_uso
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE {' AND '.join(condicoes)}
            ORDER BY (u.status = '{UTILIZADO}') DESC, u.status, u.xProd""",
        params,
    )
    for linha in linhas:
        linha["situacao"] = rotulo(linha["status"])
    return linhas


def contar_ativos() -> int:
    return db.escalar("SELECT COUNT(*) FROM lotes_bloqueados WHERE status = 'ativo'")
