# tests/test_chamados.py
"""Reportar problema → chamado para a Administração (nov/2026)."""
import base64

from src.providers.implementations.opme import db


def test_abrir_listar_responder(client, admin_headers):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    r = client.post("/api/chamados/abrir", headers=admin_headers, json={
        "descricao": "Erro ao bipar na sala 03", "pagina": "/bipagem/registrar_uso", "versao": "17.3.18",
        "imagem": "data:image/png;base64," + base64.b64encode(png).decode()}).json()
    assert r["ok"] and r["numero"]
    c = db.consultar_um("SELECT * FROM chamados WHERE id_chamado = ?", (r["numero"],))
    assert c["status"] == "aberto" and c["imagem"] and c["pagina"] == "/bipagem/registrar_uso"
    lista = client.get("/api/chamados", headers=admin_headers).json()["dados"]
    assert lista["abertos"] >= 1 and lista["chamados"][0]["id_chamado"] == r["numero"]
    assert client.get(f"/api/chamados/imagem/{c['imagem']}", headers=admin_headers).content == png
    client.post(f"/api/chamados/{r['numero']}/atualizar", headers=admin_headers,
                data={"status": "resolvido", "resposta": "Corrigido."})
    meus = client.get("/api/chamados/meus", headers=admin_headers).json()["chamados"]
    assert meus[0]["status"] == "resolvido" and meus[0]["resposta"] == "Corrigido."
    assert client.post("/api/chamados/abrir", headers=admin_headers, json={"descricao": "x"}).json()["ok"] is False
    # A imagem não vai para a trilha de auditoria.
    assert not db.escalar("SELECT COUNT(*) FROM auditoria WHERE dados LIKE '%base64%'") if \
        db.escalar("SELECT name FROM sqlite_master WHERE name = 'auditoria'") else True
