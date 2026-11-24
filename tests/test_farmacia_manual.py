# tests/test_farmacia_manual.py
"""Cadastro manual feito pela farmácia entra direto no estoque dela (nov/2026)."""
from src.providers.implementations.opme import db


def _base(**extra):
    return {"xProd": "PARAFUSO", "codigo_barras": "7899999000111", "codigo_aghu": "123", "fornecedor": "F",
            "marca_fabricante": "M", "nLote": "LFARM", "dVal": "2031-01-01", "quantidade": "2",
            "tipo_entrada": "aquisicao_propria"} | extra


def test_farmacia_cadastra_no_proprio_estoque(client, admin_headers):
    r = client.get("/api/farmacia/manual", headers=admin_headers)
    assert r.json()["dados"]["base"] == "/farmacia" and "HEMODINAMICA - PDT" in r.json()["dados"]["farmacias"]
    r = client.post("/api/farmacia/manual", headers=admin_headers, data=_base(farmacia="HEMODINAMICA - PDT"))
    assert r.status_code == 200
    linhas = db.consultar("SELECT status, farmacia FROM unidades WHERE nLote = 'LFARM'")
    assert len(linhas) == 2 and all(l["status"] == "em_estoque_farmacia" and l["farmacia"] == "HEMODINAMICA - PDT"
                                    for l in linhas)
    ev = db.consultar_um("SELECT observacao FROM eventos WHERE tipo = 'entrada_manual' ORDER BY id_evento DESC")
    assert "Hemodinâmica" in ev["observacao"]


def test_farmacia_exige_escolher_o_estoque(client, admin_headers):
    r = client.post("/api/farmacia/manual", headers=admin_headers, data=_base(nLote="LSEM"))
    assert r.json()["dados"]["erro"].startswith("Escolha a farmácia")
    assert not db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = 'LSEM'")


def test_almoxarifado_continua_no_almoxarifado(client, admin_headers):
    client.post("/api/almoxarifado/manual", headers=admin_headers, data=_base(nLote="LALM"))
    assert {l["status"] for l in db.consultar("SELECT status FROM unidades WHERE nLote = 'LALM'")} == {"em_estoque_recebimento"}


def test_cadastro_manual_recusa_validade_vencida(client, admin_headers):
    for base, extra in (("almoxarifado", {}), ("farmacia", {"farmacia": "BLOCO CIRURGICO"})):
        r = client.post(f"/api/{base}/manual", headers=admin_headers, data=_base(nLote=f"LVENC{base}", dVal="2020-01-01", **extra))
        assert "já passou" in r.json()["dados"]["erro"]
        assert not db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = ?", (f"LVENC{base}",))
