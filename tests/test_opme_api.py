# tests/test_opme_api.py
"""Regras do framework aplicadas ao TraceOPME: rotas privadas, RBAC local, envelope e auditoria."""
import asyncio

from sqlalchemy import select


def test_rotas_do_traceopme_exigem_token(client):
    for caminho in ("/api/", "/api/almoxarifado", "/api/farmacia", "/api/consultas/itens", "/api/admin"):
        r = client.get(caminho)
        assert r.status_code == 401, caminho
        assert "detail" in r.json()


def test_login_errado_devolve_401_com_detail(client):
    r = client.post("/api/login", data={"username": "admin", "password": "errada"})
    assert r.status_code == 401
    assert r.json()["detail"]


def test_users_me_traz_papel_e_modulos(client, admin_headers):
    r = client.get("/api/users/me", headers=admin_headers)
    assert r.status_code == 200
    dados = r.json()
    assert dados["papel"] == "admin"
    assert "almoxarifado" in dados["modulos"] and "admin" in dados["modulos"]


def test_envelope_de_tela(client, admin_headers):
    r = client.get("/api/almoxarifado", headers=admin_headers)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["tela"] == "almoxarifado/hub.html"
    assert "em_estoque" in corpo["dados"]


def test_rbac_local_bloqueia_modulo_sem_permissao(client, admin_headers):
    # cria um usuário "consulta" e confere que ele não entra no almoxarifado
    r = client.post("/api/admin/usuarios", headers=admin_headers, json={
        "username": "consulta.teste", "nome": "Consulta Teste", "papel": "consulta",
        "senha": "Consulta2026"})
    assert r.status_code == 200, r.text
    r = client.post("/api/login", data={"username": "consulta.teste", "password": "Consulta2026"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.get("/api/almoxarifado", headers=h)
    assert r.json() == {"redirecionar": "/?sem_permissao=1"}
    r = client.get("/api/admin/ad-user-search/joao.silva", headers=h)
    assert r.status_code == 403


def test_mutacao_gera_audit_log_com_ip(client, admin_headers):
    from src.models.audit_log import AuditLog

    r = client.post("/api/farmacia/unidade", headers=admin_headers, data={"unidade": "BLOCO CIRURGICO"})
    assert r.json()["sessao"]["unidade_farmacia"] == "BLOCO CIRURGICO"

    async def ultimo():
        async with client.app.state.app_db.async_session_maker() as s:
            res = await s.execute(select(AuditLog).where(AuditLog.acao == "ESCOLHER_UNIDADE"))
            return res.scalars().all()

    logs = asyncio.run(ultimo())
    assert logs, "a escolha de unidade deveria estar na trilha de auditoria"
    assert logs[-1].usuario == "admin" and logs[-1].categoria == "NEGOCIO_CLINICO"
    assert logs[-1].ip_origem


def test_meta_do_sistema(client, admin_headers):
    r = client.get("/api/sistema/meta", headers=admin_headers)
    dados = r.json()["dados"]
    assert dados["estados"]["utilizado"]["rotulo"]
    assert "BLOCO CIRURGICO" in dados["farmacias"]
    assert dados["modo_autenticacao"] == "local"
