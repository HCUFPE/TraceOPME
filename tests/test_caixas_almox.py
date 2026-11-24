# tests/test_caixas_almox.py
"""Caixas de consignado montadas no almoxarifado e dispensadas às farmácias (nov/2026)."""
from src.providers.implementations.opme import db


def _cadastra(client, h, lote, modulo="almoxarifado", **extra):
    dados = {"xProd": "PARAFUSO CX", "codigo_barras": f"78900{lote}", "codigo_aghu": "555", "fornecedor": "ORTOVIDA",
             "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01", "quantidade": "2",
             "tipo_entrada": "consignado", "codigo_consignado": "C555"} | extra
    client.post(f"/api/{modulo}/manual", headers=h, data=dados)
    return [l["id_unidade"] for l in db.consultar("SELECT id_unidade FROM unidades WHERE nLote = ?", (lote,))]


def _caixa_nova(client, h):
    client.post("/api/almoxarifado/caixas", headers=h, data={"nome": "Caixa almox", "fornecedor": "ORTOVIDA"})
    return db.consultar_um("SELECT * FROM caixas WHERE nome = 'Caixa almox' ORDER BY rowid DESC")


def test_fluxo_almox_farmacia(client, admin_headers):
    h = admin_headers
    ids = _cadastra(client, h, "LCXA1")
    farm = _cadastra(client, h, "LCXF1", modulo="farmacia", farmacia="HEMODINAMICA - PDT")
    cx = _caixa_nova(client, h)
    assert cx["local"] == "almoxarifado"
    r = client.get("/api/almoxarifado/caixas", headers=h).json()["dados"]
    assert r["modo"] == "almoxarifado" and any(c["id_caixa"] == cx["id_caixa"] for c in r["caixas"])
    # Farmácia não lista nem mexe na caixa que ainda está no almoxarifado.
    r = client.get("/api/farmacia/caixas-consignado", headers=h).json()["dados"]
    assert all(c["id_caixa"] != cx["id_caixa"] for c in r["caixas"])
    client.post(f"/api/farmacia/caixas-consignado/{cx['id_caixa']}/adicionar", headers=h, data={"id_unidade": ids[0]})
    assert not db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],))
    # Almoxarifado só coloca item do próprio estoque.
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/adicionar", headers=h, data={"id_unidade": farm[0]})
    assert not db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],))
    for i in ids:
        client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/adicionar", headers=h, data={"id_unidade": i})
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],)) == 2
    # Dispensa para a Hemodinâmica.
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/enviar", headers=h, data={"farmacia": "HEMODINAMICA - PDT"})
    c = db.consultar_um("SELECT * FROM caixas WHERE id_caixa = ?", (cx["id_caixa"],))
    assert c["local"] == "transito" and c["farmacia"] == "HEMODINAMICA - PDT"
    assert {u["status"] for u in db.consultar("SELECT status FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],))} \
        == {"transito_farmacia"}
    # Em trânsito ninguém mexe no conteúdo.
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/retirar/{ids[0]}", headers=h, data={"motivo": "x"})
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],)) == 2
    # Farmácia vê chegando e dá ciência.
    r = client.get("/api/farmacia/caixas-consignado", headers=h).json()["dados"]
    assert any(c["id_caixa"] == cx["id_caixa"] for c in r["chegando"])
    client.post(f"/api/farmacia/caixas-consignado/{cx['id_caixa']}/receber", headers=h)
    c = db.consultar_um("SELECT * FROM caixas WHERE id_caixa = ?", (cx["id_caixa"],))
    assert c["local"] == "farmacia" and c["recebida_por"]
    assert {u["status"] for u in db.consultar("SELECT status, farmacia FROM unidades WHERE id_caixa = ?",
                                              (cx["id_caixa"],))} == {"em_estoque_farmacia"}
    tipos = {e["tipo"] for e in db.consultar("SELECT tipo FROM eventos WHERE id_unidade = ?", (ids[0],))}
    assert {"caixa_enviada_farmacia", "caixa_recebida_farmacia"} <= tipos
    # Agora a farmácia completa a caixa como já fazia.
    r = client.get("/api/farmacia/caixas-consignado", headers=h).json()["dados"]
    assert any(c["id_caixa"] == cx["id_caixa"] for c in r["caixas"])
    client.post(f"/api/farmacia/caixas-consignado/{cx['id_caixa']}/adicionar", headers=h, data={"id_unidade": farm[0]})
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (cx["id_caixa"],)) == 3
    ficha = client.get(f"/api/almoxarifado/caixas/{cx['id_caixa']}", headers=h).json()["dados"]
    assert ficha["somente_leitura"]


def test_cancelar_envio_volta_ao_almoxarifado(client, admin_headers):
    h = admin_headers
    ids = _cadastra(client, h, "LCXA2")
    client.post("/api/almoxarifado/caixas", headers=h, data={"nome": "Caixa cancela", "fornecedor": "ORTOVIDA"})
    cx = db.consultar_um("SELECT * FROM caixas WHERE nome = 'Caixa cancela'")
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/adicionar", headers=h, data={"id_unidade": ids[0]})
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/enviar", headers=h, data={"farmacia": "BLOCO CIRURGICO"})
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/cancelar-envio", headers=h, data={"motivo": "farmácia errada"})
    c = db.consultar_um("SELECT local FROM caixas WHERE id_caixa = ?", (cx["id_caixa"],))
    assert c["local"] == "almoxarifado"
    assert db.consultar_um("SELECT status FROM unidades WHERE id_unidade = ?", (ids[0],))["status"] == "em_estoque_recebimento"


def test_caixa_vazia_nao_sai(client, admin_headers):
    h = admin_headers
    client.post("/api/almoxarifado/caixas", headers=h, data={"nome": "Caixa vazia", "fornecedor": "ORTOVIDA"})
    cx = db.consultar_um("SELECT * FROM caixas WHERE nome = 'Caixa vazia'")
    client.post(f"/api/almoxarifado/caixas/{cx['id_caixa']}/enviar", headers=h, data={"farmacia": "BLOCO CIRURGICO"})
    assert db.consultar_um("SELECT local FROM caixas WHERE id_caixa = ?", (cx["id_caixa"],))["local"] == "almoxarifado"
