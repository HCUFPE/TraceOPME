# tests/test_v18_42_nome_do_paciente.py
"""v18.42: o nome do paciente junto do prontuário nas telas de bipagem.

Camila (20/11/2026), na tela "Dispensar para a sala": "nessa tela trazer o
nome do paciente também." Quem dispensa confere o paciente pelo nome, não
pelo número do prontuário.

O nome entra em `atendimentos.descrever`, que é a linha de identificação de
todas as telas de bipagem, da ficha da sala e das dispensações/devoluções.
"""
from src.providers.implementations.opme.services import atendimentos
from src.providers.implementations.opme.utils import hoje_iso

BASE = {"prontuario": "11443090", "unidade": "HEMODINAMICA", "sala": "01",
        "especialidade": "RADIOLOGIA INTERVENCIONISTA", "data_procedimento": "2026-11-23"}


def test_descrever_traz_o_nome_depois_do_prontuario():
    linha = atendimentos.descrever(BASE | {"paciente": "JOAO MANOEL ALVES"})
    assert linha.startswith("Prontuário 11443090 · JOAO MANOEL ALVES · ")
    assert "Sala 01" in linha and "23/11/2026" in linha


def test_sem_nome_a_linha_fica_como_era():
    for sem in ("", "   ", None):
        assert atendimentos.descrever(BASE | {"paciente": sem}) == \
               "Prontuário 11443090 · HEMODINAMICA — Sala 01 · Radiologia Intervencionista · 23/11/2026"


def test_a_tela_de_dispensar_mostra_o_nome(client, admin_headers):
    ok, ida = atendimentos.abrir({"prontuario": "11443099", "paciente": "JOAO MANOEL ALVES",
                                  "unidade": "BLOCO CIRURGICO", "sala": "12",
                                  "especialidade": "ORTOPEDIA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    r = client.get("/api/bipagem/dispensar_sala", params={"atendimento": ida}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "JOAO MANOEL ALVES" in r.text
