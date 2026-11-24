"""Alertas entre módulos.

Quando a Farmácia devolve material ao Almoxarifado porque "não identificou o
recebimento" — ou o Bloco devolve material à Farmácia porque não reconheceu a
dispensação — isso não pode só reaparecer silenciosamente na lista "ainda
pendente" do outro lado, como se fosse uma chegada nova. É uma devolução, e
quem devolveu já sabe o motivo; quem recebe de volta precisa de um sinal
explícito para investigar com atenção diferenciada, não só ver o número da
pendência mudar.

Este módulo é deliberadamente simples: um alerta é aberto, alguém do módulo de
destino resolve (lê e confirma que tratou), e ele sai da lista. Nada além
disso — sem prioridade, sem prazo, sem escalonamento. Se isso um dia não for
suficiente, dá para crescer a partir daqui.
"""

from .. import db
from ..utils import gerar_id, texto


def criar(
    *, modulo_destino: str, titulo: str, mensagem: str, usuario: str,
    id_atendimento: str = "", id_unidade: str = "", ids_unidade: list[str] | None = None,
    link: str = "",
) -> str:
    id_alerta = gerar_id("AL")
    ids_unidade = [texto(i) for i in (ids_unidade or []) if texto(i)]
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO alertas
               (id_alerta, modulo_destino, titulo, mensagem, id_atendimento, id_unidade,
                ids_unidade, link, status, criado_em, criado_por)
               VALUES (?,?,?,?,?,?,?,?,'aberto',?,?)""",
            (id_alerta, modulo_destino, titulo, mensagem,
             texto(id_atendimento) or None, texto(id_unidade) or None,
             ",".join(ids_unidade) or None, texto(link) or None, db.agora(), usuario),
        )
    return id_alerta


def itens(alerta: dict) -> list[dict]:
    """Detalhe de cada unidade ligada ao alerta — produto, lote, código AGHU e de
    barras. Sem isto, quem recebe o alerta sabe só o nome do produto, e se
    existir mais de um lote em estoque não dá para saber qual unidade exata
    voltou, então não dá para tratar."""
    ids = [i for i in texto(alerta.get("ids_unidade")).split(",") if i]
    if not ids:
        return []
    marcadores = ",".join("?" for _ in ids)
    linhas = db.consultar(
        f"""SELECT id_unidade, xProd, codigo_aghu, nLote, codigo_barras, status
            FROM unidades WHERE id_unidade IN ({marcadores})""",
        ids,
    )
    por_id = {l["id_unidade"]: l for l in linhas}
    return [por_id[i] for i in ids if i in por_id]


def listar_abertos(limite: int = 50) -> list[dict]:
    """Todos os alertas em aberto, de qualquer módulo. Quem chama filtra por perfil."""
    return db.consultar(
        "SELECT * FROM alertas WHERE status = 'aberto' ORDER BY criado_em DESC LIMIT ?",
        (limite,),
    )


def abertos_do_modulo(modulo: str, limite: int = 30) -> list[dict]:
    return db.consultar(
        """SELECT * FROM alertas WHERE modulo_destino = ? AND status = 'aberto'
           ORDER BY criado_em DESC LIMIT ?""",
        (modulo, limite),
    )


def contar_abertos(modulo: str) -> int:
    return db.escalar(
        "SELECT COUNT(*) FROM alertas WHERE modulo_destino = ? AND status = 'aberto'", (modulo,)
    )


def resolver(id_alerta: str, usuario: str) -> tuple[bool, str]:
    alerta = db.consultar_um("SELECT * FROM alertas WHERE id_alerta = ?", (texto(id_alerta),))
    if not alerta:
        return False, "Alerta não encontrado."
    if alerta["status"] != "aberto":
        return False, "Este alerta já tinha sido resolvido."
    with db.transacao() as conn:
        conn.execute(
            "UPDATE alertas SET status = 'resolvido', resolvido_em = ?, resolvido_por = ? "
            "WHERE id_alerta = ?",
            (db.agora(), usuario, texto(id_alerta)),
        )
    return True, "Alerta resolvido."
