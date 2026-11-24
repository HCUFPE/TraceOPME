"""nov/2026 — caixas de consignado montadas no ALMOXARIFADO.

O almoxarifado passa a ter as caixas também: cria a caixa, bipa o material do
estoque dele para dentro e DISPENSA a caixa para uma farmácia (Bloco ou
Hemodinâmica). A farmácia dá CIÊNCIA do recebimento; daí em diante a caixa é da
farmácia e segue como já acontece — vai para a sala, volta, é completada.

Onde a caixa está fica em `caixas.local`:
    almoxarifado → montando no almoxarifado (só entra material do estoque dele);
    transito     → enviada à farmácia, aguardando a ciência (não recebe item, não sai);
    farmacia     → na farmácia (vazio = farmácia, como as caixas de antes).

Os itens acompanham a caixa (a caixa é um contêiner): ao enviar, saem do estoque
do almoxarifado e ficam "em trânsito para a farmácia"; na ciência, entram no
estoque da farmácia. Enquanto a farmácia não deu ciência, o almoxarifado pode
cancelar o envio.
"""

from .. import db, log
from ..config import FARMACIAS, rotulo_farmacia
from ..domain import EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, TRANSITO_FARMACIA
from ..utils import texto
from . import caixas_consignado

ALMOX, TRANSITO, FARMACIA = "almoxarifado", "transito", "farmacia"


def local(caixa: dict | None) -> str:
    return texto((caixa or {}).get("local")) or FARMACIA


def _caixa(id_caixa: str) -> dict | None:
    return caixas_consignado.buscar(id_caixa)


def criar(dados: dict, usuario: str) -> tuple[bool, str, str]:
    ok, mensagem, id_caixa = caixas_consignado.criar(dados, usuario)
    if ok:
        db.executar("UPDATE caixas SET local = ?, status = ?, farmacia = NULL WHERE id_caixa = ?",
                    (ALMOX, EM_ESTOQUE_RECEBIMENTO, id_caixa))
        mensagem = (f"Caixa {id_caixa} criada no almoxarifado. Bipe os itens para dentro e depois "
                    f"dispense para a farmácia.")
    return ok, mensagem, id_caixa


def listar(locais: tuple[str, ...] = (ALMOX, TRANSITO), farmacia: str = "") -> list[dict]:
    marcadores = ",".join("?" for _ in locais)
    filtro, params = "", list(locais)
    if texto(farmacia):
        filtro, params = " AND c.farmacia = ?", params + [texto(farmacia)]
    linhas = db.consultar(
        f"""SELECT c.*, (SELECT COUNT(*) FROM unidades u WHERE u.id_caixa = c.id_caixa) AS total,
                   (SELECT GROUP_CONCAT(f, ', ') FROM (SELECT DISTINCT TRIM(u2.fornecedor) AS f FROM unidades u2
                    WHERE u2.id_caixa = c.id_caixa AND TRIM(COALESCE(u2.fornecedor,'')) <> '' ORDER BY 1)) AS fornecedores
            FROM caixas c
            WHERE c.encerrada_em IS NULL AND COALESCE(NULLIF(c.local, ''), 'farmacia') IN ({marcadores}){filtro}
            ORDER BY c.local, c.id_caixa""", params)
    for l in linhas:
        l["farmacia_rotulo"] = rotulo_farmacia(l["farmacia"]) if texto(l.get("farmacia")) else ""
    return linhas


def a_receber(farmacia: str = "") -> list[dict]:
    return listar((TRANSITO,), farmacia)


def enviar(id_caixa: str, farmacia: str, usuario: str) -> tuple[bool, str]:
    caixa = _caixa(id_caixa)
    if not caixa:
        return False, "Caixa não encontrada."
    if local(caixa) != ALMOX:
        return False, "Só dá para dispensar caixa que está no almoxarifado."
    farmacia = texto(farmacia).upper()
    if farmacia not in FARMACIAS:
        return False, "Escolha a farmácia de destino (Bloco Cirúrgico ou Hemodinâmica)."
    if caixa.get("bloqueada"):
        return False, "A caixa está bloqueada para conferência. Confira e libere antes de dispensar."
    dentro = db.consultar("SELECT id_unidade, status FROM unidades WHERE id_caixa = ?", (caixa["id_caixa"],))
    if not dentro:
        return False, "A caixa está vazia. Bipe os itens para dentro antes de dispensar."
    fora = [u for u in dentro if u["status"] != EM_ESTOQUE_RECEBIMENTO]
    if fora:
        return False, (f"{len(fora)} item(ns) da caixa não estão no estoque do almoxarifado. "
                       "Confira a caixa antes de dispensar.")
    agora, destino = db.agora(), rotulo_farmacia(farmacia)
    marcador = f"[{caixa['id_caixa']}]"
    with db.transacao() as conn:
        for u in dentro:
            conn.execute("""UPDATE unidades SET status = ?, farmacia = ?, atualizado_em = ?, atualizado_por = ?
                            WHERE id_unidade = ? AND status = ?""",
                         (TRANSITO_FARMACIA, farmacia, agora, usuario, u["id_unidade"], EM_ESTOQUE_RECEBIMENTO))
            db.registrar_evento(conn, tipo="caixa_enviada_farmacia", id_unidade=u["id_unidade"],
                                status_anterior=EM_ESTOQUE_RECEBIMENTO, status_novo=TRANSITO_FARMACIA,
                                usuario=usuario, observacao=f"{marcador} caixa dispensada para a {destino}")
        conn.execute("""UPDATE caixas SET local = ?, status = ?, farmacia = ?, envio_farmacia = ?, enviada_em = ?,
                        enviada_por = ?, recebida_em = NULL, recebida_por = NULL, recebida_nome = NULL,
                        atualizado_em = ?, atualizado_por = ? WHERE id_caixa = ?""",
                     (TRANSITO, TRANSITO_FARMACIA, farmacia, farmacia, agora, usuario, agora, usuario,
                      caixa["id_caixa"]))
    log.info(f"caixa dispensada à farmácia · {caixa['id_caixa']} · {farmacia} · {len(dentro)} item(ns)", usuario)
    return True, (f"Caixa {caixa['id_caixa']} dispensada para a {destino} com {len(dentro)} item(ns). "
                  "A farmácia dá ciência do recebimento.")


def cancelar_envio(id_caixa: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    caixa = _caixa(id_caixa)
    if not caixa or local(caixa) != TRANSITO:
        return False, "Esta caixa não está a caminho da farmácia."
    if len(texto(motivo)) < 3:
        return False, "Informe o motivo do cancelamento."
    agora = db.agora()
    marcador = f"[{caixa['id_caixa']}]"
    with db.transacao() as conn:
        atual = conn.execute("SELECT local FROM caixas WHERE id_caixa = ?", (caixa["id_caixa"],)).fetchone()
        if texto(atual["local"]) != TRANSITO:
            return False, "A farmácia acabou de dar ciência; não dá mais para cancelar."
        for u in conn.execute("SELECT id_unidade FROM unidades WHERE id_caixa = ? AND status = ?",
                              (caixa["id_caixa"], TRANSITO_FARMACIA)).fetchall():
            conn.execute("""UPDATE unidades SET status = ?, farmacia = NULL, atualizado_em = ?, atualizado_por = ?
                            WHERE id_unidade = ?""", (EM_ESTOQUE_RECEBIMENTO, agora, usuario, u["id_unidade"]))
            db.registrar_evento(conn, tipo="envio_cancelado", id_unidade=u["id_unidade"],
                                status_anterior=TRANSITO_FARMACIA, status_novo=EM_ESTOQUE_RECEBIMENTO,
                                usuario=usuario, motivo=texto(motivo),
                                observacao=f"{marcador} envio da caixa cancelado; voltou ao almoxarifado")
        conn.execute("""UPDATE caixas SET local = ?, status = ?, farmacia = NULL, envio_farmacia = NULL,
                        atualizado_em = ?, atualizado_por = ? WHERE id_caixa = ?""",
                     (ALMOX, EM_ESTOQUE_RECEBIMENTO, agora, usuario, caixa["id_caixa"]))
    return True, f"Envio da caixa {caixa['id_caixa']} cancelado. Ela voltou ao almoxarifado."


def receber(id_caixa: str, quem: dict, farmacia_da_tela: str = "") -> tuple[bool, str]:
    """A farmácia dá ciência do recebimento da caixa."""
    caixa = _caixa(id_caixa)
    if not caixa or local(caixa) != TRANSITO:
        return False, "Esta caixa não está aguardando ciência."
    if texto(farmacia_da_tela) and texto(farmacia_da_tela) != texto(caixa["farmacia"]):
        return False, (f"Esta caixa foi dispensada para a {rotulo_farmacia(caixa['farmacia'])}. "
                       "Quem dá ciência é essa farmácia.")
    nome = quem.get("nome") or quem["username"]
    agora = db.agora()
    marcador = f"[{caixa['id_caixa']}]"
    with db.transacao() as conn:
        n = 0
        for u in conn.execute("SELECT id_unidade FROM unidades WHERE id_caixa = ? AND status = ?",
                              (caixa["id_caixa"], TRANSITO_FARMACIA)).fetchall():
            conn.execute("""UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                            WHERE id_unidade = ?""", (EM_ESTOQUE_FARMACIA, agora, quem["username"], u["id_unidade"]))
            db.registrar_evento(conn, tipo="caixa_recebida_farmacia", id_unidade=u["id_unidade"],
                                status_anterior=TRANSITO_FARMACIA, status_novo=EM_ESTOQUE_FARMACIA,
                                usuario=quem["username"], recebido_por=nome,
                                observacao=f"{marcador} ciência do recebimento da caixa por {nome}")
            n += 1
        conn.execute("""UPDATE caixas SET local = ?, status = ?, recebida_em = ?, recebida_por = ?, recebida_nome = ?,
                        atualizado_em = ?, atualizado_por = ? WHERE id_caixa = ?""",
                     (FARMACIA, EM_ESTOQUE_FARMACIA, agora, quem["username"], nome, agora, quem["username"],
                      caixa["id_caixa"]))
    return True, (f"Ciência registrada: a caixa {caixa['id_caixa']} ({n} item(ns)) está no estoque da "
                  f"{rotulo_farmacia(caixa['farmacia'])}.")
