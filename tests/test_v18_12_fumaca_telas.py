# tests/test_v18_12_fumaca_telas.py
"""v18.12: fumaça — toda rota GET sem parâmetro responde e toda tela devolvida existe no Vue."""
import re
from pathlib import Path

from src.main import app

RAIZ = Path(__file__).resolve().parents[1]
IGNORAR = ("/api/logout", "/api/health", "/openapi", "/docs", "/redoc", "/api/robo-aghu", "/api/zabbix")


def _rotas_get():
    for r in app.routes:
        caminho = getattr(r, "path", "")
        if "GET" in getattr(r, "methods", ()) and caminho.startswith("/api/") and "{" not in caminho \
                and not caminho.startswith(IGNORAR):
            yield caminho


def test_todas_as_telas_abrem(client, admin_headers):
    telas_vue = set(re.findall(r"^\s*'([^']+\.html)'", (RAIZ / "frontend/src/views/opme/telas.ts").read_text("utf-8"), re.M))
    problemas, vistas = [], 0
    for caminho in sorted(set(_rotas_get())):
        r = client.get(caminho, headers=admin_headers)
        if r.status_code >= 500:
            problemas.append(f"{caminho}: HTTP {r.status_code} {r.text[:200]}")
            continue
        if r.status_code != 200 or "application/json" not in r.headers.get("content-type", ""):
            continue
        corpo = r.json()
        if isinstance(corpo, dict) and corpo.get("tela"):
            vistas += 1
            if corpo["tela"] not in telas_vue:
                problemas.append(f"{caminho}: tela {corpo['tela']} não registrada no telas.ts")
    assert not problemas, "\n".join(problemas)
    assert vistas > 40, vistas
