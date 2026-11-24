# tests/test_v18_devolucao_fornecedor.py
"""v18: devolução ao fornecedor com número, romaneio por devolução e cancelamento."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import devolucoes_fornecedor as dvf, estoque


def _cad(cod, forn, lote, qtd=2):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": "9091",
                                      "fornecedor": forn, "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
                                      "quantidade": str(qtd), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


def _bipar(client, h, cod):
    return client.post("/api/bipar", headers=h, json={"operacao": "devolver_fornecedor", "codigo": cod,
                                                       "motivo": "defeito"}).json()


def test_devolucao_com_numero(client, admin_headers):
    h = admin_headers
    _cad("DVF0001", "ORTOVIDA", "L1")
    _cad("DVF0002", "CARDIOMED", "L2", qtd=1)
    r1 = _bipar(client, h, "DVF0001")
    assert r1["ok"], r1
    r2 = _bipar(client, h, "DVF0001")
    r3 = _bipar(client, h, "DVF0002")
    assert r1["devolucao_fornecedor"] == r2["devolucao_fornecedor"] != r3["devolucao_fornecedor"]
    abertas = {d["fornecedor"]: d for d in r3["devolucoes_abertas"]}
    assert abertas["ORTOVIDA"]["qtd_itens"] == 2 and abertas["CARDIOMED"]["qtd_itens"] == 1
    dev = abertas["ORTOVIDA"]["id_devolucao"]
    assert dev.startswith("DEV-")
    # finalizar e baixar o romaneio da devolução
    client.post(f"/api/almoxarifado/devolucao-fornecedor/{dev}/finalizar", headers=h)
    assert dvf.buscar(dev)["status"] == "finalizada"
    pdf = client.get(f"/api/almoxarifado/devolucao-fornecedor/{dev}/pdf", headers=h)
    assert pdf.content[:4] == b"%PDF"
    lista = client.get("/api/almoxarifado/romaneios-fornecedor", headers=h).json()["dados"]["devolucoes"]
    assert any(d["id_devolucao"] == dev and d["qtd_itens"] == 2 for d in lista)
    # tirar um item: volta ao estoque
    item = dvf.itens(dev, so_ativos=True)[0]
    client.post(f"/api/almoxarifado/devolucao-fornecedor/{dev}/cancelar-item", headers=h,
                data={"id_unidade": item["id_unidade"], "motivo": "bipado errado"})
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (item["id_unidade"],)) == "em_estoque_recebimento"
    assert dvf.buscar(dev)["qtd_itens"] == 1
    # cancelar a devolução inteira
    client.post(f"/api/almoxarifado/devolucao-fornecedor/{dev}/cancelar", headers=h, data={"motivo": "fornecedor não retirou"})
    assert dvf.buscar(dev)["status"] == "cancelada"
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_barras='DVF0001' AND status='em_estoque_recebimento'") == 2
    # desfazer na bipagem tira o item da devolução aberta
    outra = r3["devolucao_fornecedor"]
    client.post("/api/desfazer", headers=h, json={"id_unidade": dvf.itens(outra, True)[0]["id_unidade"]})
    assert dvf.buscar(outra)["qtd_itens"] == 0


def test_legado_agrupado(client):
    _cad("DVF0099", "LEGADO SA", "LG", qtd=1)
    u = db.consultar_um("SELECT id_unidade FROM unidades WHERE codigo_barras='DVF0099'")["id_unidade"]
    with db.transacao() as conn:
        conn.execute("UPDATE unidades SET status='devolvido_fornecedor' WHERE id_unidade=?", (u,))
        db.registrar_evento(conn, tipo="devolver_fornecedor", id_unidade=u, status_anterior="em_estoque_recebimento",
                            status_novo="devolvido_fornecedor", usuario="antigo")
    lista = dvf.listar(fornecedor="LEGADO SA")
    assert len(lista) == 1 and lista[0]["legado"] == 1 and lista[0]["qtd_itens"] == 1
