"""v18.14 — dispensação de OPME para OUTROS PROCEDIMENTOS.

A farmácia e o almoxarifado às vezes entregam OPME para um procedimento que não
passa pelo fluxo de sala/paciente deste sistema: outro setor, ambulatório, um
serviço que registra o uso no próprio prontuário/AGHU. O que o TraceOPME precisa
garantir é o que ele garante em qualquer saída: o item **sai do estoque** na hora,
com registro de quem retirou, para onde foi e por quê.

O acompanhamento do uso item a item não é feito aqui (é isso que diferencia esta
saída da dispensação para a sala). O que fica é a trilha: o evento `saida_outros`
(ou `saida_outros_almox`) com o motivo/destino, o responsável e a observação.

A bipagem em si é a genérica (`fluxo.bipar` com a operação `saida_outros` na
farmácia e `saida_outros_almox` no almoxarifado). Este módulo é a leitura: a tela
"Saídas para outros procedimentos", com filtro de período e totais por destino.
"""

from .. import db
from ..config import rotulo_farmacia
from ..domain import SAIDA_OUTROS
from ..utils import data_br, hoje_iso, texto

# Destinos sugeridos (a pessoa pode digitar outro — o campo é livre).
DESTINOS = (
    "Ambulatório",
    "Centro cirúrgico — outro procedimento",
    "Hemodinâmica — outro procedimento",
    "UTI",
    "Pronto atendimento / emergência",
    "Internação / enfermaria",
    "Outra unidade do hospital",
    "Outro hospital / serviço externo",
    "Ensino e pesquisa",
)

OPERACOES = ("saida_outros", "saida_outros_almox")


def listar(de: str = "", ate: str = "", destino: str = "", origem: str = "") -> list[dict]:
    """Saídas para outros procedimentos no período (uma linha por item).

    `origem`: "farmacia" ou "almoxarifado" (de onde o material saiu); vazio = as duas.
    `destino`: filtra pelo texto do destino/motivo.
    """
    onde = ["e.tipo IN ('saida_outros','saida_outros_almox')"]
    params: list = []
    if de:
        onde.append("DATE(e.data_evento) >= DATE(?)")
        params.append(de)
    if ate:
        onde.append("DATE(e.data_evento) <= DATE(?)")
        params.append(ate)
    if origem == "farmacia":
        onde.append("e.tipo = 'saida_outros'")
    elif origem == "almoxarifado":
        onde.append("e.tipo = 'saida_outros_almox'")
    if texto(destino):
        onde.append("UPPER(COALESCE(e.motivo,'')) LIKE ?")
        params.append(f"%{texto(destino).upper()}%")
    linhas = db.consultar(
        f"""SELECT e.data_evento, e.usuario, e.motivo, e.observacao, e.tipo,
                   u.id_unidade, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                   u.fornecedor, u.farmacia, u.status
            FROM eventos e
            JOIN unidades u ON u.id_unidade = e.id_unidade
            WHERE {' AND '.join(onde)}
            ORDER BY e.data_evento DESC, e.id_evento DESC""", tuple(params))
    for l in linhas:
        l["origem"] = "Almoxarifado" if l["tipo"] == "saida_outros_almox" else (
            rotulo_farmacia(l["farmacia"]) if texto(l.get("farmacia")) else "Farmácia")
        l["destino"] = texto(l.get("motivo")) or "—"
        l["data_br"] = data_br(texto(l["data_evento"])[:10]) or texto(l["data_evento"])[:10]
        l["hora"] = texto(l["data_evento"])[11:16]
        l["validade_br"] = data_br(l.get("dVal")) or "—"
        l["material"] = texto(l.get("descritivo_hospital")) or texto(l.get("xProd"))
        # Saída desfeita depois (correção do almoxarifado): o item voltou ao estoque.
        l["desfeita"] = l["status"] != SAIDA_OUTROS
    return linhas


def resumo(linhas: list[dict]) -> list[dict]:
    """Totais por destino, do maior para o menor (a tela mostra acima da lista)."""
    por: dict[str, dict] = {}
    for l in linhas:
        if l["desfeita"]:
            continue
        alvo = por.setdefault(l["destino"], {"destino": l["destino"], "itens": 0, "materiais": set()})
        alvo["itens"] += 1
        alvo["materiais"].add(texto(l.get("codigo_aghu")) or l["material"])
    saida = [{"destino": v["destino"], "itens": v["itens"], "materiais": len(v["materiais"])}
             for v in por.values()]
    return sorted(saida, key=lambda r: (-r["itens"], r["destino"]))


def desfazer(id_unidade: str, usuario: str, motivo: str) -> tuple[bool, str]:
    """Bipou por engano: o item volta para o estoque de onde saiu.

    Volta para a farmácia dona do item; sem farmácia, para o almoxarifado — a
    mesma regra de qualquer retorno (`domain.estoque_de_volta`).
    """
    from ..domain import estoque_de_volta
    motivo = texto(motivo)
    if len(motivo) < 5:
        return False, "Informe o motivo para desfazer a saída."
    u = db.consultar_um(
        "SELECT id_unidade, status, farmacia, xProd, descritivo_hospital, nLote FROM unidades "
        "WHERE id_unidade = ?", (texto(id_unidade),))
    if not u:
        return False, "Item não encontrado."
    if u["status"] != SAIDA_OUTROS:
        return False, "Este item não está como saída para outro procedimento."
    destino = estoque_de_volta(u.get("farmacia"))
    with db.transacao() as conn:
        conn.execute("UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ? "
                     "WHERE id_unidade = ? AND status = ?",
                     (destino, db.agora(), usuario, u["id_unidade"], SAIDA_OUTROS))
        db.registrar_evento(conn, tipo="saida_outros_desfeita", id_unidade=u["id_unidade"],
                            status_anterior=SAIDA_OUTROS, status_novo=destino,
                            usuario=usuario, motivo=motivo)
    onde = "estoque da farmácia" if destino != "em_estoque_recebimento" else "estoque do almoxarifado"
    nome = texto(u.get("descritivo_hospital")) or texto(u.get("xProd"))
    return True, f"Saída desfeita: {nome} (lote {u.get('nLote') or '—'}) voltou para o {onde}."


def periodo_padrao(de: str = "", ate: str = "") -> tuple[str, str]:
    from datetime import date, timedelta
    if not de and not ate:
        return (date.today() - timedelta(days=30)).isoformat(), hoje_iso()
    return de, ate
