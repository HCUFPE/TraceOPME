# tests/test_agenda_metabase.py
"""Agenda de procedimentos direto do relatórios (Metabase) — nov/2026.

Um Metabase de mentira (thread local) responde como o do HC-UFPE: login,
modelo 1703 e a consulta filtrada pelo dia.
"""
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.config import settings
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import agenda_metabase

COLS = [{"name": n, "display_name": n.replace("_", " ").title(), "base_type": t} for n, t in (
    ("PRONTUARIO", "type/Text"), ("NOME", "type/Text"), ("DESCRICAO_UNIDADE_FUNCIONAL", "type/Text"),
    ("SALA", "type/Text"), ("ESPECIALIDADE", "type/Text"), ("DTHR_INICIO_CIRG", "type/DateTime"),
    ("SOLICITACAO_ESPECIAL", "type/Text"))]
CONSULTAS = []


class Falso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, codigo=200):
        corpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/session":
            ok = json.loads(corpo)["password"] == "certa"
            return self._json({"id": "tok"} if ok else {"errors": {}}, 200 if ok else 401)
        if self.path == "/api/dataset":
            q = json.loads(corpo)
            CONSULTAS.append(q)
            dia = q["query"]["filter"][2]
            linhas = [["21.472.063", "MARIA", "BLOCO CIRURGICO", "SALA 05", "CARDIOLOGIA", f"{dia}T07:30:00-03:00",
                       '["OPME (1) - STENT 3.0"]'],
                      ["10.000.001", "JOSE", "BLOCO CIRURGICO", "SALA 02", "ORTOPEDIA", f"{dia}T09:00:00-03:00", ""]]
            return self._json({"status": "completed", "data": {"cols": COLS, "rows": linhas}})
        self._json({}, 404)

    def do_GET(self):
        if self.path == "/api/card/1703":
            return self._json({"name": "Escala prévia definitiva", "database_id": 4, "result_metadata": COLS})
        self._json({}, 404)

    def do_DELETE(self):
        self.send_response(204)
        self.end_headers()


@pytest.fixture
def metabase(monkeypatch, client):
    srv = HTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "METABASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(settings, "METABASE_USUARIO", "servico.opme")
    monkeypatch.setattr(settings, "METABASE_SENHA", "certa")
    monkeypatch.setattr(settings, "AGENDA_HORARIOS", "06:00,12:00")
    yield srv
    srv.shutdown()


def test_busca_e_importa_sem_duplicar(metabase):
    ok, msg = agenda_metabase.buscar_e_importar("2026-11-04", "admin")
    assert ok and "2 atendimento(s) importado(s)" in msg, msg
    filtro = CONSULTAS[-1]["query"]["filter"]
    assert filtro[1][1] == "DTHR_INICIO_CIRG" and filtro[2] == "2026-11-04"
    at = db.consultar_um("SELECT * FROM atendimentos WHERE prontuario = '21472063' AND data_procedimento = '2026-11-04'")
    assert at and at["hora_inicio"] == "07:30" and "STENT" in at["opme_solicitado"]
    ok, msg = agenda_metabase.buscar_e_importar("2026-11-04", "admin")
    assert ok and "2 já existia" in msg, msg
    assert agenda_metabase.ultimas(1)[0]["ok"] == 1


def test_senha_errada_fica_registrada(metabase):
    ok, msg = agenda_metabase.buscar_e_importar("2026-11-04", "admin", usuario="x", senha="errada")
    assert not ok and "não aceitou" in msg
    assert agenda_metabase.ultimas(1)[0]["ok"] == 0


def test_rotina_busca_uma_vez_por_horario(metabase):
    antes = len(CONSULTAS)
    msgs = agenda_metabase.executar_rotina(datetime(2026, 11, 5, 13, 0))
    assert len(msgs) == 1 and msgs[0].startswith("12:00 · 2026-11-05 · ok"), msgs
    assert agenda_metabase.executar_rotina(datetime(2026, 11, 5, 13, 1)) == []
    assert agenda_metabase.executar_rotina(datetime(2026, 11, 5, 5, 0)) == []
    assert len(CONSULTAS) == antes + 1


def test_botao_na_tela(metabase, client, admin_headers):
    r = client.get("/api/procedimentos", headers=admin_headers)
    assert r.json()["dados"]["agenda_metabase"]["configurada"] is True
    r = client.post("/api/procedimentos/agenda/buscar", headers=admin_headers, data={"data": "2026-11-06"})
    assert r.status_code == 200 and CONSULTAS[-1]["query"]["filter"][2] == "2026-11-06"


def test_csv_com_ponto_e_virgula_e_virgulas_nos_campos():
    """Arquivo do relatórios: separado por ';' e com vírgulas dentro dos campos."""
    from src.providers.implementations.opme.services import atendimentos
    linhas = ["codigo_cirurgia;codigo_unidade_funcional;descricao_unidade_funcional;sala;prontuario;nome;dthr_inicio_cirg;solicitacao_especial"]
    for i in range(30):
        linhas.append(f'9{i:03d};1;BLOCO CIRURGICO;SALA 0{i % 5 + 1};21.472.{i:03d};PACIENTE {i};5/11/2026, 07:30;'
                      f'"[""OPME (1) - PARAFUSO, PLACA"", ""INSTRUMENTAIS CME (1) - X, Y""]"')
    ok, msg = atendimentos.importar_agenda_csv("\n".join(linhas).encode("utf-8-sig"), "admin")
    assert ok, msg


def test_lista_do_relatorios_vira_pedido_de_opme():
    from src.providers.implementations.opme.services import agenda_metabase, atendimentos
    v = agenda_metabase._valor_csv(["OPME (1) - PLACA BLOQUEADA", "INSTRUMENTAIS CME (1) - CAIXA"])
    assert v.startswith('["OPME (1)')
    assert atendimentos._extrair_opme(v) == "OPME (1) - PLACA BLOQUEADA"
    assert atendimentos._extrair_opme("['OPME (2) - PARAFUSO', 'CME (1) - X']") == "OPME (2) - PARAFUSO"
    assert atendimentos._coluna_opme('["PARAFUSO CORTICAL 3.5 (4)"]') == "PARAFUSO CORTICAL 3.5 (4)"
    assert atendimentos._coluna_opme("[]") == "" and atendimentos._coluna_opme("Não") == ""


def test_tela_procedimentos_mostra_todos(client, admin_headers):
    from src.providers.implementations.opme.services import atendimentos
    cab = "codigo_cirurgia;descricao_unidade_funcional;sala;prontuario;nome;dthr_inicio_cirg;solicitacao_especial"
    linhas = [cab, '1;ENDOSCOPIA;01;111;A;7/12/2031, 07:00;', '2;BLOCO CIRURGICO;02;222;B;7/12/2031, 08:00;',
              '3;BLOCO CIRURGICO;03;333;C;7/12/2031, 09:00;"[""OPME (1) - PLACA""]"']
    assert atendimentos.importar_agenda_csv("\n".join(linhas).encode(), "admin")[0]
    r = client.get("/api/procedimentos?data=2031-12-07", headers=admin_headers).json()["dados"]
    assert {a["prontuario"] for a in r["atendimentos"]} == {"111", "222", "333"}
