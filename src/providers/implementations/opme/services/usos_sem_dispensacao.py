"""v17 (out/2026) — uso na sala de material que NÃO foi dispensado pela farmácia.

O uso é aceito (não dá para travar o paciente), a saída da farmácia é gravada no
próprio uso, e a FARMÁCIA precisa DAR CIÊNCIA de cada caso — não basta consultar.
Cada caso fica pendente até alguém da farmácia dar ciência (com o próprio login),
e entra nos indicadores (taxa de uso sem dispensação e ciência em até 24 h).
Se o uso for desfeito/estornado antes da ciência, o caso é cancelado.
"""

from .. import db
from ..utils import texto


def registrar(conn, *, id_unidade: str, id_atendimento: str, usuario: str) -> None:
    conn.execute(
        """INSERT INTO usos_sem_dispensacao (id_unidade, id_atendimento, usado_em, usado_por, situacao)
           VALUES (?,?,?,?,'pendente')""", (id_unidade, id_atendimento, db.agora(), usuario))


def cancelar(conn, id_unidade: str, motivo: str = "") -> None:
    """Uso desfeito, excluído ou estornado: não há mais o que a farmácia saber."""
    conn.execute(
        """UPDATE usos_sem_dispensacao SET situacao = 'cancelado', observacao = ?
           WHERE id_unidade = ? AND situacao = 'pendente'""",
        (texto(motivo) or "Uso desfeito antes da ciência", id_unidade))


def _consulta(condicao: str, params=(), limite: int = 500) -> list[dict]:
    return db.consultar(
        f"""SELECT s.*, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal, u.tipo_entrada,
                   a.prontuario, a.paciente, a.unidade, a.sala, a.data_procedimento
            FROM usos_sem_dispensacao s
            LEFT JOIN unidades u ON u.id_unidade = s.id_unidade
            LEFT JOIN atendimentos a ON a.id_atendimento = s.id_atendimento
            WHERE {condicao} ORDER BY s.usado_em DESC LIMIT ?""", (*params, limite))


def pendentes() -> list[dict]:
    return _consulta("s.situacao = 'pendente'")


def com_ciencia(limite: int = 50) -> list[dict]:
    return _consulta("s.situacao = 'ciente'", limite=limite)


def contar_pendentes() -> int:
    return db.escalar("SELECT COUNT(*) FROM usos_sem_dispensacao WHERE situacao = 'pendente'")


def dar_ciencia(ids: list, usuario: dict, observacao: str = "") -> tuple[bool, str]:
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return False, "Marque pelo menos um material para dar ciência."
    agora = db.agora()
    with db.transacao() as conn:
        linhas = conn.execute(
            f"""SELECT id, id_unidade, id_atendimento FROM usos_sem_dispensacao
                WHERE situacao = 'pendente' AND id IN ({','.join('?' for _ in ids)})""", ids).fetchall()
        for linha in linhas:
            conn.execute(
                """UPDATE usos_sem_dispensacao SET situacao = 'ciente', ciente_em = ?, ciente_por = ?,
                          ciente_nome = ?, observacao = ? WHERE id = ?""",
                (agora, usuario["username"], usuario.get("nome") or usuario["username"],
                 texto(observacao), linha[0]))
            db.registrar_evento(
                conn, tipo="ciencia_uso_sem_dispensacao", id_unidade=linha[1], id_atendimento=linha[2],
                usuario=usuario["username"], recebido_por=usuario.get("nome") or usuario["username"],
                observacao=("Farmácia ciente do uso sem dispensação. " + texto(observacao)).strip())
    if not linhas:
        return False, "Esses materiais já tinham ciência."
    return True, f"Ciência registrada para {len(linhas)} material(is)."


def taxa_e_ciencia(inicio: str, fim: str, *, unidade: str = "") -> dict:
    """Base dos indicadores: usos válidos no período, quantos sem dispensação e
    quantos tiveram ciência em até 24 h.

    v18.15: `unidade` separa Bloco e Hemodinâmica (pela unidade física do caso)."""
    from . import indicadores as ind
    filtro = ind._f_unidades("fu", unidade)
    casos = db.consultar(
        f"""SELECT usado_em, ciente_em, situacao FROM usos_sem_dispensacao s
            WHERE situacao <> 'cancelado' AND date(usado_em) BETWEEN date(?) AND date(?)
              {"AND EXISTS (SELECT 1 FROM unidades fu WHERE fu.id_unidade = s.id_unidade" + filtro + ")" if filtro else ""}""",
        (inicio, fim))
    no_prazo = sum(1 for c in casos if c["ciente_em"] and db.escalar(
        "SELECT (julianday(?) - julianday(?)) * 24 <= 24", (c["ciente_em"], c["usado_em"])))
    return {"casos": len(casos), "com_ciencia": sum(1 for c in casos if c["situacao"] == "ciente"),
            "no_prazo": no_prazo}
