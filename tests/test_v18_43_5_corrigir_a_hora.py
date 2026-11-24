# tests/test_v18_43_5_corrigir_a_hora.py
"""v18.43.5: corrigir a hora do procedimento na aba "Corrigir dados do atendimento".

Camila (23/11/2026): "NA ABA DE CORRIGIR ATENDIMENTO, INCLUIR A HORA TAMBÉM."

A hora define o turno na agenda e aparece na identificação do atendimento, mas
só podia ser definida na abertura.
"""
import pytest

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos
from src.providers.implementations.opme.utils import hoje_iso

_n = [0]


def _abrir(hora="08:00"):
    _n[0] += 1
    ok, ida = atendimentos.abrir({"prontuario": f"43500{_n[0]:03d}", "paciente": "JOAO MANOEL ALVES",
                                  "unidade": "HEMODINAMICA - PDT", "sala": "01",
                                  "especialidade": "HEMODINAMICA", "hora_inicio": hora,
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


def test_corrige_a_hora(client):
    ida = _abrir("08:00")
    ok, msg = atendimentos.atualizar(ida, {"prontuario": "43500001", "paciente": "JOAO MANOEL ALVES",
                                           "unidade": "HEMODINAMICA - PDT", "sala": "01",
                                           "hora_inicio": "14:30"}, "camila.melo.3")
    assert ok, msg
    assert atendimentos.buscar(ida)["hora_inicio"] == "14:30"


def test_a_mudanca_fica_na_auditoria(client):
    ida = _abrir("08:00")
    atendimentos.atualizar(ida, {"hora_inicio": "16:45"}, "camila.melo.3")
    obs = db.escalar("""SELECT observacao FROM eventos WHERE id_atendimento = ?
                        AND tipo = 'atendimento_atualizado' ORDER BY id_evento DESC LIMIT 1""", (ida,))
    assert "16:45" in obs and "era 08:00" in obs


def test_pode_apagar_a_hora(client):
    ida = _abrir("08:00")
    ok, msg = atendimentos.atualizar(ida, {"hora_inicio": ""}, "camila.melo.3")
    assert ok, msg
    assert not (atendimentos.buscar(ida)["hora_inicio"] or "")


@pytest.mark.parametrize("ruim", ["25:00", "12:99", "14h30", "1430", "meio-dia"])
def test_hora_invalida_e_recusada(client, ruim):
    ida = _abrir("08:00")
    ok, msg = atendimentos.atualizar(ida, {"hora_inicio": ruim}, "camila.melo.3")
    assert not ok and "Hora inválida" in msg
    assert atendimentos.buscar(ida)["hora_inicio"] == "08:00", "não pode ter mexido"


def test_quem_nao_manda_hora_nao_perde_a_que_tem(client):
    """Outras telas que atualizam o atendimento sem o campo hora."""
    ida = _abrir("09:15")
    ok, msg = atendimentos.atualizar(ida, {"paciente": "OUTRO NOME"}, "camila.melo.3")
    assert ok, msg
    at = atendimentos.buscar(ida)
    assert at["hora_inicio"] == "09:15" and at["paciente"] == "OUTRO NOME"


def test_pela_tela(client, admin_headers):
    ida = _abrir("08:00")
    r = client.post(f"/api/sala-procedimento/atendimento/{ida}",
                    data={"prontuario": "43500999", "paciente": "JOAO MANOEL ALVES",
                          "local": "HEMODINAMICA - PDT|01", "hora_inicio": "11:20",
                          "observacao": ""}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert atendimentos.buscar(ida)["hora_inicio"] == "11:20"
