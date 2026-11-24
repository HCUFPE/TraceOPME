"""nov/2026 — lançar a NF no AGHU pelo robô, a partir da tela da NF.

O TraceOPME roda num SERVIDOR e o robô fica no computador de quem lança a nota
(instalado uma vez com o instalador baixado da própria tela da NF). O botão
"Lançar no AGHU" gera um código de uso único e um link traceopme-aghu://… que o
navegador entrega ao robô daquele computador. O robô baixa a planilha da NF do
servidor (/api/robo-aghu/planilha, com o código), faz o lançamento e, no fim,
responde em /api/robo-aghu/retorno se a nota foi gravada. A NF passa a mostrar
"lançada no AGHU" com data e quem lançou. Também dá para marcar à mão.

Situações (notas_fiscais.aghu_status): '' (não lançada) · 'em_lancamento' · 'lancada'.
"""

from __future__ import annotations

import base64
import io
import json
import os
import secrets
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from .. import db, log
from ..utils import texto
from . import planilha_aghu

RAIZ = Path(__file__).resolve().parents[5]
ROBO = RAIZ / "ferramentas" / "robo_nota_aghu" / "robo_nota_aghu.py"
HORAS_TOKEN = 12
PASTA_ROBO = ROBO.parent
ROTULOS = {"": "Não lançada no AGHU", "em_lancamento": "Robô aberto — aguardando a gravação no AGHU",
           "lancada": "Lançada no AGHU"}


def _nota(chave: str) -> dict | None:
    return db.consultar_um("SELECT * FROM notas_fiscais WHERE chave_nf = ?", (texto(chave),))


def situacao(chave: str) -> dict:
    n = _nota(chave) or {}
    status = texto(n.get("aghu_status"))
    pendentes = db.escalar("SELECT COALESCE(SUM(qtd_pendente), 0) FROM nf_itens WHERE chave_nf = ?",
                           (texto(chave),)) or 0
    return {"status": status, "rotulo": ROTULOS.get(status, status),
            "iniciado_em": n.get("aghu_iniciado_em"), "iniciado_por": n.get("aghu_iniciado_por"),
            "lancada_em": n.get("aghu_lancada_em"), "lancada_por": n.get("aghu_lancada_por"),
            "nr": n.get("aghu_nr"), "entrada_concluida": int(pendentes) == 0,
            "instalador_disponivel": ROBO.is_file()}


def a_lancar() -> list[dict]:
    """NFs com a entrada concluída no TraceOPME e ainda não lançadas no AGHU."""
    return db.consultar(
        """SELECT n.chave_nf, n.numero_nf, n.fornecedor, n.data_importacao, COALESCE(n.aghu_status, '') AS aghu_status,
                  n.aghu_iniciado_em
           FROM notas_fiscais n
           WHERE COALESCE(n.aghu_status, '') <> 'lancada'
             AND EXISTS (SELECT 1 FROM nf_itens i WHERE i.chave_nf = n.chave_nf)
             AND NOT EXISTS (SELECT 1 FROM nf_itens i WHERE i.chave_nf = n.chave_nf AND COALESCE(i.qtd_pendente, 0) > 0)
             AND EXISTS (SELECT 1 FROM unidades u WHERE u.chave_nf = n.chave_nf AND COALESCE(u.origem, '') = 'xml')
           ORDER BY n.data_importacao DESC LIMIT 100""")


def iniciar(chave: str, usuario: str, servidor: str) -> tuple[bool, str, str]:
    """Gera o código e o link que o navegador entrega ao robô deste computador.

    Devolve (ok, mensagem, link). `servidor` é o endereço do TraceOPME como o
    navegador de quem clicou o enxerga (ex.: http://10.34.1.20:8000)."""
    nota = _nota(chave)
    if not nota:
        return False, "Nota fiscal não encontrada.", ""
    if texto(nota.get("aghu_status")) == "lancada":
        return False, "Esta NF já está marcada como lançada no AGHU.", ""
    if not planilha_aghu.linhas(chave):
        return False, "Nenhum item desta nota deu entrada ainda.", ""
    servidor = texto(servidor).rstrip("/")
    if not servidor.startswith(("http://", "https://")):
        return False, "Endereço do servidor inválido.", ""
    # v18.7.2: clicar de novo (ou o navegador abrir o link duas vezes) não invalida o código que um
    # robô já aberto está usando — enquanto o lançamento está aberto e o código vale, reaproveita.
    token = texto(nota.get("aghu_token"))
    if not (texto(nota.get("aghu_status")) == "em_lancamento" and token
            and texto(nota.get("aghu_token_expira")) > datetime.now().isoformat(timespec="seconds")):
        token = secrets.token_urlsafe(24)
    expira = (datetime.now() + timedelta(hours=HORAS_TOKEN)).isoformat(timespec="seconds")
    db.executar("""UPDATE notas_fiscais SET aghu_status = 'em_lancamento', aghu_iniciado_em = ?, aghu_iniciado_por = ?,
                   aghu_token = ?, aghu_token_expira = ? WHERE chave_nf = ?""",
                (db.agora(), usuario, token, expira, nota["chave_nf"]))
    dados = {"s": servidor, "c": nota["chave_nf"], "t": token, "n": texto(nota["numero_nf"]),
             "a": os.getenv("AGHU_URL", ""), "b": os.getenv("AGHU_NAVEGADOR", "")}
    # Tudo num bloco só (base64url): sem "&" nem "%" no link, que o Windows passa inteiro ao robô.
    bloco = base64.urlsafe_b64encode(json.dumps(dados, separators=(",", ":")).encode()).decode().rstrip("=")
    log.info(f"robô do AGHU chamado para a NF {nota['numero_nf']}", usuario)
    return True, (f"Abrindo o robô neste computador para a NF {nota['numero_nf']}. Se o navegador perguntar, "
                  "clique em “Abrir”. Siga a janela preta."), f"traceopme-aghu://lancar/{bloco}"


def _token_valido(nota: dict | None, token: str) -> str:
    """'' se vale; senão o motivo."""
    if not nota or not texto(token) or not texto(nota.get("aghu_token")) \
            or not secrets.compare_digest(texto(nota.get("aghu_token")), texto(token)):
        return "Código do robô inválido (já usado ou de outro lançamento)."
    if texto(nota.get("aghu_token_expira")) < datetime.now().isoformat(timespec="seconds"):
        return "O código do robô expirou. Clique de novo em “Lançar no AGHU” na tela da NF."
    return ""


def planilha_para_robo(chave: str, token: str) -> tuple[bytes | None, str]:
    nota = _nota(chave)
    motivo = _token_valido(nota, token)
    if motivo:
        return None, motivo
    return planilha_aghu.xlsx(chave)


def instalador_zip(servidor: str = "") -> bytes:
    """Pacote para instalar o robô no computador de quem lança (com o endereço do servidor)."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(PASTA_ROBO.iterdir()):
            if arq.is_file() and arq.suffix.lower() in (".py", ".bat", ".txt", ".ini"):
                z.write(arq, f"robo_nota_aghu/{arq.name}")
    return saida.getvalue()


def retorno(chave: str, token: str, gravou: bool, numero_nr: str = "") -> tuple[bool, str]:
    nota = _nota(chave)
    motivo = _token_valido(nota, token)
    if motivo:
        return False, motivo
    quem = nota.get("aghu_iniciado_por") or "robô"
    if gravou:
        db.executar("""UPDATE notas_fiscais SET aghu_status = 'lancada', aghu_lancada_em = ?, aghu_lancada_por = ?,
                       aghu_nr = ?, aghu_token = NULL, aghu_token_expira = NULL WHERE chave_nf = ?""",
                    (db.agora(), quem, texto(numero_nr)[:30], nota["chave_nf"]))
        log.info(f"NF {nota['numero_nf']} lançada no AGHU (robô)", quem)
        return True, f"NF {nota['numero_nf']} marcada como lançada no AGHU."
    db.executar("UPDATE notas_fiscais SET aghu_status = '', aghu_token = NULL, aghu_token_expira = NULL "
                "WHERE chave_nf = ?", (nota["chave_nf"],))
    return True, f"NF {nota['numero_nf']} continua como não lançada no AGHU."


def marcar(chave: str, acao: str, usuario: str, numero_nr: str = "") -> tuple[bool, str]:
    nota = _nota(chave)
    if not nota:
        return False, "Nota fiscal não encontrada."
    if acao == "lancada":
        db.executar("""UPDATE notas_fiscais SET aghu_status = 'lancada', aghu_lancada_em = ?, aghu_lancada_por = ?,
                       aghu_nr = ?, aghu_token = NULL, aghu_token_expira = NULL WHERE chave_nf = ?""",
                    (db.agora(), usuario, texto(numero_nr)[:30], nota["chave_nf"]))
        log.info(f"NF {nota['numero_nf']} marcada à mão como lançada no AGHU", usuario)
        return True, f"NF {nota['numero_nf']} marcada como lançada no AGHU."
    if acao in ("desfazer", "cancelar"):
        db.executar("""UPDATE notas_fiscais SET aghu_status = '', aghu_lancada_em = NULL, aghu_lancada_por = NULL,
                       aghu_nr = NULL, aghu_token = NULL, aghu_token_expira = NULL WHERE chave_nf = ?""",
                    (nota["chave_nf"],))
        log.info(f"NF {nota['numero_nf']}: situação no AGHU voltou para não lançada", usuario)
        return True, f"NF {nota['numero_nf']} voltou para “não lançada no AGHU”."
    return False, "Ação inválida."
