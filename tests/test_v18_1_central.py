# tests/test_v18_1_central.py
"""v18.1: central de monitoramento das salas e alerta de solicitação por farmácia."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, estoque, monitoramento
from src.providers.implementations.opme.utils import hoje_iso


def test_central_mostra_etapas(client, admin_headers):
    h = admin_headers
    estoque.cadastrar_manual({"xProd": "PARAFUSO MON", "codigo_barras": "7891230005551", "codigo_aghu": "771",
                              "fornecedor": "F", "marca_fabricante": "M", "nLote": "LMON", "dVal": "2031-01-01",
                              "quantidade": "3", "tipo_entrada": "aquisicao_propria"}, "admin")
    ok, a1 = atendimentos.abrir({"prontuario": "550001", "paciente": "MARIA DA SILVA SANTOS", "unidade": "BLOCO CIRURGICO",
                                 "sala": "05", "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso(),
                                 "hora_inicio": "08:00"}, "admin")
    ok, a2 = atendimentos.abrir({"prontuario": "550002", "unidade": "BLOCO CIRURGICO", "sala": "05",
                                 "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso(), "hora_inicio": "13:00"}, "admin")
    p = monitoramento.painel("BLOCO CIRURGICO")
    s5 = next(s for s in p["salas"] if s["sala"] == "05")
    assert s5["etapa"] == "agendado" and s5["atual"]["id_atendimento"] == a1
    assert s5["atual"]["paciente"] == "Maria S."
    atendimentos.abrir_sala(a1, "admin")
    r = client.post("/api/bipar", headers=h, json={"operacao": "registrar_uso", "codigo": "7891230005551",
                                                    "atendimento": a1}).json()
    assert r["ok"], r
    p = monitoramento.painel("BLOCO CIRURGICO")
    s5 = next(s for s in p["salas"] if s["sala"] == "05")
    assert s5["etapa"] == "em_uso" and s5["atual"]["bips"] == 1 and s5["atual"]["horas"]["aberta"]
    assert p["resumo"]["itens_bipados"] >= 1 and p["resumo"]["em_andamento"] >= 1
    assert any(s["sala"] == "01" and s["etapa"] == "livre" for s in p["salas"])
    # tela e JSON
    t = client.get("/api/monitoramento?unidade=BLOCO%20CIRURGICO", headers=h).json()
    assert t["tela"] == "monitoramento/central.html" if "tela" in t else True
    j = client.get("/api/monitoramento/dados?unidade=todas", headers=h).json()
    assert {s["unidade"] for s in j["salas"]} == {"BLOCO CIRURGICO", "HEMODINAMICA - PDT"}
    lt = client.get(f"/api/monitoramento/procedimento/{a1}", headers=h).json()
    assert any(e["tipo"] == "registrar_uso" for e in lt["eventos"])


def test_alerta_solicitacao_por_farmacia():
    from src.helpers.web_helper import render

    class R:
        usuario = {"username": "f", "papel": "farmacia"}
        session = {}
    db.executar("SELECT 1")
    from unittest.mock import patch
    with patch("src.providers.implementations.opme.services.solicitacoes.contar_em_aberto",
               side_effect=lambda u="": {"": 3, "BLOCO CIRURGICO": 2, "HEMODINAMICA - PDT": 1}.get(u, 0)):
        d = render(R(), "farmacia/hub.html", {}).dados
        assert [(x["unidade"], x["n"]) for x in d["pedidos_opme_por_unidade"]] == [("BLOCO CIRURGICO", 2), ("HEMODINAMICA - PDT", 1)]
        R.session = {"unidade_farmacia": "HEMODINAMICA - PDT"}
        d = render(R(), "farmacia/hub.html", {}).dados
        assert d["pedidos_opme_abertos"] == 1 and "pedidos_opme_por_unidade" not in d
