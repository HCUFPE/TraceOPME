# tests/test_login_ad.py
"""Login com o AD (nov/2026).

1. Login e senha conferidos no AD.
2. Se ok e a pessoa tem perfil ativo → entra, com o perfil local.
3. Se ok e não tem perfil → solicitação de acesso automática, com nome, e-mail
   e setor vindos do AD, para o administrador aprovar ou recusar.
4. Se o AD não confere → "Usuário ou senha inválidos."

O AD é simulado registrando um validador, como o `AuthHandler` faz quando há
AD_URL no .env.
"""
import pytest

from src.providers.implementations.opme import db, security

AD = {
    ("nova.pessoa", "SenhaRede1"): {"nome": "Nova Pessoa", "email": "nova.pessoa@ebserh.gov.br",
                                    "setor": "Farmácia Hospitalar"},
    ("admin", "SenhaRedeAdmin"): {"nome": "Administrador", "email": "admin@ebserh.gov.br", "setor": "EP"},
}


def _ad_falso(username, senha):
    if username == "fora.do.ar":
        raise security.AdIndisponivel("servidor indisponível")
    dados = AD.get((username, senha))
    return dict(dados, username=username) if dados else None


@pytest.fixture
def modo_ad(client):
    security.registrar_validador_externo(_ad_falso)
    yield
    security.registrar_validador_externo(None)


def _login(client, usuario, senha):
    return client.post("/api/login", data={"username": usuario, "password": senha})


def test_ad_senha_errada_e_usuario_inexistente(client, modo_ad):
    for usuario, senha in (("admin", "admin"), ("ninguem", "x1234567")):
        r = _login(client, usuario, senha)
        assert r.status_code == 401
        assert r.json()["detail"] == "Usuário ou senha inválidos."
    assert not db.escalar("SELECT COUNT(*) FROM solicitacoes_acesso WHERE username = 'ninguem'")


def test_ad_ok_com_perfil_entra(client, modo_ad):
    r = _login(client, "admin", "SenhaRedeAdmin")
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/users/me", headers=h).json()["papel"] == "admin"


def test_ad_ok_sem_perfil_gera_solicitacao(client, modo_ad, admin_headers_ad):
    r = _login(client, "nova.pessoa", "SenhaRede1")
    assert r.status_code == 403
    detalhe = r.json()["detail"]
    assert detalhe["solicitacao_acesso"] is True and "administrador" in detalhe["mensagem"]
    sol = db.consultar_um("SELECT * FROM solicitacoes_acesso WHERE username = 'nova.pessoa' AND status = 'pendente'")
    assert sol and sol["nome"] == "Nova Pessoa" and sol["email"] == "nova.pessoa@ebserh.gov.br"
    assert sol["setor"] == "Farmácia Hospitalar" and sol["tipo"] == "cadastro"

    # Tentar de novo não duplica: avisa que já está com o administrador.
    r = _login(client, "nova.pessoa", "SenhaRede1")
    assert r.status_code == 403 and "já está com o administrador" in r.json()["detail"]["mensagem"]
    assert db.escalar("SELECT COUNT(*) FROM solicitacoes_acesso WHERE username = 'nova.pessoa'") == 1

    # O administrador aprova com um perfil → a pessoa entra com a senha de rede.
    r = client.post(f"/api/admin/solicitacao/{sol['id_solicitacao']}/aprovar",
                    headers=admin_headers_ad, data={"papel": "farmacia"})
    assert r.status_code == 200
    r = _login(client, "nova.pessoa", "SenhaRede1")
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/users/me", headers=h).json()["papel"] == "farmacia"


def test_confirmacao_com_senha_nao_gera_solicitacao(client, modo_ad):
    from src.providers.implementations.opme.services import usuarios
    AD[("outra.pessoa", "SenhaRede2")] = {"nome": "Outra", "email": "", "setor": ""}
    ok, msg = usuarios.autenticar("outra.pessoa", "SenhaRede2")
    assert not ok and "perfil" in msg
    assert not db.escalar("SELECT COUNT(*) FROM solicitacoes_acesso WHERE username = 'outra.pessoa'")


def test_ad_fora_do_ar(client, modo_ad):
    r = _login(client, "fora.do.ar", "qualquer1")
    assert r.status_code == 401 and "Active Directory" in r.json()["detail"]


@pytest.fixture
def admin_headers_ad(client, modo_ad):
    r = _login(client, "admin", "SenhaRedeAdmin")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
