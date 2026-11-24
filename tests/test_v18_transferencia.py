# tests/test_v18_transferencia.py
"""v18: transferência de material entre as farmácias (Bloco ↔ Hemodinâmica)."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import estoque, remessas

BLOCO, HEMO = "BLOCO CIRURGICO", "HEMODINAMICA - PDT"


def _no_bloco(cod, qtd=3):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": "7070",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": "LT", "dVal": "2031-01-01",
                                      "quantidade": str(qtd), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia=? WHERE codigo_barras=?", (BLOCO, cod))


def _st(cod):
    return sorted((r["status"], r["farmacia"]) for r in
                  db.consultar("SELECT status, farmacia FROM unidades WHERE codigo_barras=?", (cod,)))


def test_transferencia_com_ciencia(client, admin_headers):
    h = admin_headers
    _no_bloco("TRF0001")
    ok, id_t = remessas.abrir(BLOCO, "admin", remessas.TRANSFERENCIA)
    assert ok and id_t.startswith("TRF")
    rem = remessas.buscar(id_t)
    assert rem["farmacia"] == HEMO and rem["farmacia_origem"] == BLOCO
    r = client.post(f"/api/farmacia/transferencia/{id_t}/bipar", headers=h, json={"codigo": "TRF0001", "quantidade": 2}).json()
    assert r["ok"], r
    assert _st("TRF0001").count(("transito_farmacia", HEMO)) == 2
    # não aparece no "receber" do almoxarifado → farmácia, só na transferência
    client.post(f"/api/farmacia/transferencia/{id_t}/finalizar", headers=h)
    assert remessas.contar_a_receber(HEMO, remessas.TRANSFERENCIA) == 1
    assert remessas.contar_a_receber(HEMO) == 0
    tela = client.get("/api/farmacia/recebimentos?todas=1", headers=h).json()["dados"]
    assert any(e["id_remessa"] == id_t and e["sentido"] == "farmacia_farmacia" for e in tela["enviadas"])
    # a Hemodinâmica recebe 1 e o outro fica pendente
    itens = remessas.buscar(id_t)["pendentes"]
    client.post(f"/api/farmacia/recebimento/{id_t}/conferir", headers=h,
                data={"modo": "lista", "recebido": str(itens[0]["id_item"])})
    st = _st("TRF0001")
    assert ("em_estoque_farmacia", HEMO) in st and ("em_estoque_farmacia", BLOCO) in st
    pend = remessas.pendencias(sentido=remessas.TRANSFERENCIA, farmacia_origem=BLOCO)
    assert len(pend) == 1
    client.post(f"/api/farmacia/transferencia/item/{pend[0]['id_item']}/tratar", headers=h, data={"acao": "voltou_origem"})
    assert _st("TRF0001").count(("em_estoque_farmacia", BLOCO)) == 2


def test_transferencia_cancelada_volta(client, admin_headers):
    h = admin_headers
    _no_bloco("TRF0002", 1)
    ok, id_t = remessas.abrir(BLOCO, "admin", remessas.TRANSFERENCIA)
    client.post(f"/api/farmacia/transferencia/{id_t}/bipar", headers=h, json={"codigo": "TRF0002"})
    client.post(f"/api/farmacia/transferencia/{id_t}/finalizar", headers=h)
    client.post(f"/api/farmacia/transferencia/{id_t}/cancelar", headers=h, data={"motivo": "farmácia errada"})
    assert remessas.buscar(id_t)["status"] == "cancelada"
    assert _st("TRF0002") == [("em_estoque_farmacia", BLOCO)]
    # da Hemodinâmica não dá para bipar o que está no Bloco
    ok, id_h = remessas.abrir(HEMO, "admin", remessas.TRANSFERENCIA)
    r = remessas.bipar(id_h, "TRF0002", "admin")
    assert not r["ok"]
