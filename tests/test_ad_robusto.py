# tests/test_ad_robusto.py
"""Login no AD (nov/2026): senha conferida no bind não pode virar "AD indisponível"."""
import pytest
from fastapi import HTTPException

from src.auth import auth


class _Entradas(list):
    pass


def _fake(bind_erro=None, busca_erro=None, achar=True):
    class FakeConn:
        def __init__(self, *a, **k):
            self.entries = _Entradas()
        def bind(self):
            if bind_erro:
                raise bind_erro
            return True
        def search(self, base, filtro, **k):
            if busca_erro:
                raise busca_erro
            if achar:
                class E:
                    entry_attributes = ["displayName"]
                    def __getitem__(self, k):
                        return type("V", (), {"value": "Camila Teste"})()
                self.entries = _Entradas([E()])
        def unbind(self):
            pass
    return FakeConn


class FakeServer:
    def __init__(self, *a, **k):
        self.info = None


def _provedor(monkeypatch, **kw):
    monkeypatch.setenv("AD_URL", "ldap://ad.teste:389")
    monkeypatch.setenv("AD_BASEDN", "DC=errado")
    monkeypatch.setattr(auth, "Server", FakeServer)
    monkeypatch.setattr(auth, "Connection", _fake(**kw))
    return auth.ActiveDirectoryAuthProvider()


def test_senha_errada_401(monkeypatch):
    p = _provedor(monkeypatch, bind_erro=Exception("invalidCredentials data 52e"))
    with pytest.raises(HTTPException) as e:
        p.authenticate_user("u", "x")
    assert e.value.status_code == 401


def test_sem_rede_503_com_motivo(monkeypatch):
    p = _provedor(monkeypatch, bind_erro=OSError("timed out"))
    with pytest.raises(HTTPException) as e:
        p.authenticate_user("u", "x")
    assert e.value.status_code == 503 and "ad.teste" in e.value.detail and "timed out" in e.value.detail


def test_bind_ok_busca_falha_entra_assim_mesmo(monkeypatch):
    p = _provedor(monkeypatch, busca_erro=Exception("noSuchObject"))
    info = p.authenticate_user("camila", "x")
    assert info["username"] == "camila"


def test_bind_ok_com_dados(monkeypatch):
    p = _provedor(monkeypatch)
    assert p.authenticate_user("camila", "x")["displayName"] == ["Camila Teste"]
