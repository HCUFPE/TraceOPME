# tests/test_v18_12_permissoes.py
"""v18.12: cada perfil só abre as telas dos seus módulos (varre todas as rotas GET)."""
import pytest

from src.main import app
from src.providers.implementations.opme.security import PAPEIS, modulos_do_papel
from src.providers.implementations.opme.services import usuarios

SENHA = "Teste#Perfil2026"   # só deste teste, no banco temporário
PREFIXOS = {"almoxarifado": "/api/almoxarifado", "farmacia": "/api/farmacia",
            "sala-procedimento": "/api/sala-procedimento", "admin": "/api/admin",
            "consignados": "/api/consignados", "inventario": "/api/inventario"}


def _rotas(prefixo):
    return sorted({r.path for r in app.routes if "GET" in getattr(r, "methods", ())
                   and r.path.startswith(prefixo) and "{" not in r.path})


@pytest.mark.parametrize("papel", [p for p in PAPEIS if p != "admin"])
def test_perfil_nao_abre_modulo_alheio(client, papel):
    login = f"perm_{papel.replace('-', '_')}"[:30]
    usuarios.cadastrar_direto({"username": login, "nome": f"Teste {papel}", "papel": papel, "senha": SENHA}, "admin")
    r = client.post("/api/login", data={"username": login, "password": SENHA})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    meus = set(modulos_do_papel(papel))
    vazou = []
    for modulo, prefixo in PREFIXOS.items():
        if modulo in meus:
            continue
        for caminho in _rotas(prefixo):
            resp = client.get(caminho, headers=h)
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                corpo = resp.json()
                if isinstance(corpo, dict) and corpo.get("tela") and not corpo.get("redirecionar") \
                        and corpo["tela"] not in ("erro.html", "sem_acesso.html", "login.html"):
                    vazou.append(f"{papel} abriu {caminho} → {corpo['tela']}")
    assert not vazou, "\n".join(vazou)
