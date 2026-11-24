# tests/conftest.py
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src directory is in sys.path for test imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Bancos temporários: os testes nunca tocam o opme.db / app.db de produção.
_TEMP = Path(tempfile.mkdtemp(prefix="traceopme_pytest_"))
os.environ["OPME_DB"] = str(_TEMP / "opme.db")
os.environ["OPME_LOG_DIR"] = str(_TEMP / "logs")
os.environ["APP_DB_URL"] = f"sqlite+aiosqlite:///{_TEMP / 'app.db'}"
os.environ.pop("AD_URL", None)  # modo local (senhas do TraceOPME) nos testes

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402


@pytest.fixture
def client():
    """
    Fixture de teste que fornece um TestClient configurado para fazer requisições à aplicação FastAPI.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_headers(client):
    """Cabeçalho Authorization do administrador inicial (admin/admin no modo local)."""
    r = client.post("/api/login", data={"username": "admin", "password": "admin"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
