"""nov/2026 — "Reportar problema": chamados para a Administração.

Qualquer usuário logado abre um chamado (texto + imagem opcional, a página em
que estava e a versão do sistema). A Administração acompanha, responde e
muda a situação: aberto → em andamento → resolvido.
"""

from __future__ import annotations

import re

from .. import db
from ..utils import gerar_id, inteiro, texto
from .nao_cadastrados import _ler_foto

SITUACOES = {"aberto": "Aberto", "andamento": "Em andamento", "resolvido": "Resolvido"}


def _pasta():
    from ..config import DATA_DIR
    pasta = DATA_DIR / "chamados"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def abrir(dados: dict, usuario: dict) -> tuple[bool, str, int | None]:
    descricao = texto(dados.get("descricao"))
    if len(descricao) < 5:
        return False, "Descreva o problema (o que aconteceu e onde).", None
    if len(descricao) > 5000:
        return False, "O texto ficou longo demais (até 5.000 caracteres).", None
    imagem_bytes, erro = _ler_foto(dados.get("imagem"))
    if erro:
        return False, erro.replace("da etiqueta", "").replace("  ", " "), None
    nome_imagem = None
    if imagem_bytes:
        extensao = "png" if imagem_bytes[:4] == b"\x89PNG" else "jpg"
        nome_imagem = f"{gerar_id('CHAM')}.{extensao}"
        (_pasta() / nome_imagem).write_bytes(imagem_bytes)
    with db.transacao() as conn:
        cur = conn.execute(
            """INSERT INTO chamados (criado_em, criado_por, criado_nome, pagina, versao, descricao, imagem, status)
               VALUES (?,?,?,?,?,?,?,'aberto')""",
            (db.agora(), usuario["username"], usuario.get("nome") or usuario["username"],
             texto(dados.get("pagina"))[:300], texto(dados.get("versao"))[:30], descricao, nome_imagem))
        numero = cur.lastrowid
    return True, f"Chamado nº {numero} enviado para a Administração. Obrigado!", numero


def listar(status: str = "") -> list[dict]:
    if status:
        return db.consultar("SELECT * FROM chamados WHERE status = ? ORDER BY id_chamado DESC LIMIT 300", (status,))
    return db.consultar(
        """SELECT * FROM chamados ORDER BY CASE status WHEN 'aberto' THEN 0 WHEN 'andamento' THEN 1 ELSE 2 END,
                  id_chamado DESC LIMIT 300""")


def meus(username: str, limite: int = 10) -> list[dict]:
    return db.consultar("SELECT id_chamado, criado_em, descricao, status, resposta, atualizado_em FROM chamados "
                        "WHERE criado_por = ? ORDER BY id_chamado DESC LIMIT ?", (username, limite))


def contar_abertos() -> int:
    return db.escalar("SELECT COUNT(*) FROM chamados WHERE status <> 'resolvido'") or 0


def atualizar(id_chamado, status: str, resposta: str, usuario: str) -> tuple[bool, str]:
    if status not in SITUACOES:
        return False, "Situação inválida."
    atual = db.consultar_um("SELECT id_chamado FROM chamados WHERE id_chamado = ?", (inteiro(id_chamado, 0),))
    if not atual:
        return False, "Chamado não encontrado."
    db.executar("UPDATE chamados SET status = ?, resposta = ?, atualizado_em = ?, atualizado_por = ? WHERE id_chamado = ?",
                (status, texto(resposta), db.agora(), usuario, atual["id_chamado"]))
    return True, f"Chamado nº {atual['id_chamado']} atualizado: {SITUACOES[status]}."


def caminho_imagem(nome: str):
    if not re.fullmatch(r"CHAM-[A-Za-z0-9]+\.(jpg|png)", texto(nome)):
        return None
    caminho = _pasta() / nome
    return caminho if caminho.is_file() else None
