# tests/test_v18_4_7_master_consignado.py
"""v18.4.7: código master sem ponto; código consignado vem do AGHU."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import consignado_aghu, estoque, materiais


def test_codigo_master_ignora_o_ponto(client):
    assert materiais._codigo_master("1.234") == "1234"
    assert materiais._codigo_master("22.") == "22"
    assert materiais._codigo_master("22.0") == "22"
    assert materiais._codigo_master(" 361 ") == "361"
    csv = ("Código Master;Código AGHU;Nome Material;Valor Unitário\n"
           "1.022;7022;ACIDO TESTE 100 MG;0,04\n420.;7400303;CALCITRIOL TESTE;1,14\n").encode("utf-8")
    ok, msg, _ = materiais.importar_planilha(csv, "mastertools.csv", "admin")
    assert ok, msg
    assert materiais.codigo_master("7022") == "1022"
    assert materiais.codigo_master("7400303") == "420"
    # valor já gravado com ponto é limpo na leitura
    db.executar("UPDATE materiais_mestre SET codigo_master='3.333' WHERE codigo_aghu='7022'")
    assert materiais.codigo_master("7022") == "3333"


def _cad(aghu, lote, fornecedor="SELLMED PRODUTOS MEDICOS", consig=""):
    return estoque.cadastrar_manual({"xProd": f"CATETER {lote}", "codigo_barras": f"78999{lote[-4:]}0001",
                                     "codigo_aghu": aghu, "fornecedor": fornecedor, "marca_fabricante": "M",
                                     "nLote": lote, "dVal": "2031-01-01", "quantidade": "1",
                                     "tipo_entrada": "consignado", "codigo_consignado": consig}, "admin")


def test_consignado_vem_do_aghu(client):
    ok, msg = _cad("91365", "LCG1001")   # v18.11.4: sem a relação, usa o próprio AGHU (não trava)
    assert ok, msg
    assert db.escalar("SELECT codigo_consignado FROM unidades WHERE nLote='LCG1001'") == "91365"
    assert consignado_aghu.salvar("53610008", "91365", "admin", "SELLMED")[0]
    ok, msg = _cad("91365", "LCG1002")
    assert ok, msg
    assert db.escalar("SELECT codigo_consignado FROM unidades WHERE nLote='LCG1002'") == "53610008"
    # dois códigos para o mesmo AGHU: usa o do fornecedor da nota
    assert consignado_aghu.salvar("77770001", "91365", "admin", "OUTRA EMPRESA")[0]
    ok, msg = _cad("91365", "LCG1003", fornecedor="OUTRA EMPRESA LTDA")
    assert ok, msg
    assert db.escalar("SELECT codigo_consignado FROM unidades WHERE nLote='LCG1003'") == "77770001"
    ok, msg = _cad("91365", "LCG1004", fornecedor="TERCEIRA")
    assert not ok and "mais de um código" in msg
    ok, msg = _cad("91365", "LCG1005", fornecedor="TERCEIRA", consig="77770001")
    assert ok, msg
    r = client.get("/api/almoxarifado/consignado-aghu?aghu=91365",
                   headers={"Authorization": "Bearer " + client.post("/api/login", data={"username": "admin", "password": "admin"}).json()["access_token"]})
    assert r.status_code == 200
