# tests/test_v18_23_lote_da_etiqueta_fora_da_farmacia.py
"""v18.23: etiqueta cujo LOTE não está no estoque desta farmácia.

Caso real (HC-UFPE, 18/11/2026): a Farmácia da Hemodinâmica buscou a etiqueta
`010694945042379010SP102412050317271204` (GTIN 06949450423790, lote SP1024120503)
e a tela respondeu "10 unidade(s) em estoque" — mas as 10 eram do lote
SP1024022104. O lote da etiqueta estava todo no almoxarifado, e por isso o bip
da dispensação recusava, com razão. A tela é que estava enganando.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo
from src.providers.implementations.opme.utils import hoje_iso

GTIN = "06949450423790"
ETIQUETA = "010694945042379010SP102412050317271204"      # lote SP1024120503, val. 04/12/2027
HEMO = "HEMODINAMICA - PDT"


def _cad(lote, validade, quantidade):
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA HIDROFILICO DE 0,35 COM 145CM", "codigo_barras": GTIN,
        "codigo_aghu": "92529", "fornecedor": "APT MEDICAL", "marca_fabricante": "HYDROPHILIC",
        "nLote": lote, "dVal": validade, "quantidade": str(quantidade),
        "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


_PRONTO: list = []


def _cenario():
    if _PRONTO:
        return
    _PRONTO.append(True)
    _cad("SP1024022104", "2027-02-20", 10)       # na farmácia da hemodinâmica
    _cad("SP1024120503", "2027-12-04", 70)       # o lote da etiqueta: no almoxarifado
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote = 'SP1024022104'",
                (EM_ESTOQUE_FARMACIA, HEMO))


def test_a_etiqueta_e_lida_com_o_lote_certo(client):
    from src.providers.implementations.opme import gs1
    lido = gs1.interpretar(ETIQUETA)
    assert lido["gtin"] == GTIN
    assert lido["lote_curto"] == "SP1024120503" and lido["validade_do_lote"] == "2027-12-04"


def test_estoque_avisa_que_o_lote_da_etiqueta_nao_esta_aqui(client):
    _cenario()
    achado = estoque.estoque_consolidado_detalhado(EM_ESTOQUE_FARMACIA, ETIQUETA, HEMO)
    assert achado["aviso"] and "SP1024120503" in achado["aviso"]
    # as linhas continuam (outros lotes do mesmo produto), mas identificadas
    assert [l["nLote"] for l in achado["linhas"]] == ["SP1024022104"]
    # "onde" conta só o lote da etiqueta: as 70 unidades estão no almoxarifado
    onde = {o["status"]: o["quantidade"] for o in achado["onde"]}
    assert onde == {EM_ESTOQUE_RECEBIMENTO: 70}


def test_sem_aviso_quando_o_lote_esta_mesmo_aqui(client):
    _cenario()
    etiqueta_daqui = "010694945042379010SP10240221041727022 0".replace(" ", "")
    achado = estoque.estoque_consolidado_detalhado(EM_ESTOQUE_FARMACIA, etiqueta_daqui, HEMO)
    assert achado["aviso"] == ""
    achado_lote = estoque.estoque_consolidado_detalhado(EM_ESTOQUE_FARMACIA, "SP1024022104", HEMO)
    assert achado_lote["aviso"] == "" and achado_lote["linhas"]


def test_o_bip_da_dispensacao_diz_qual_lote_esta_no_almoxarifado(client):
    _cenario()
    ok, ida = atendimentos.abrir({"prontuario": "9923100", "unidade": HEMO, "sala": "01",
                                  "especialidade": "RADIOLOGIA INTERVENCIONISTA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    r = fluxo.bipar(operacao="dispensar_sala", codigo=ETIQUETA, usuario="farm1",
                    id_atendimento=ida, farmacia=HEMO)
    assert not r["ok"]
    assert "ALMOXARIFADO" in r["mensagem"]
    assert "SP1024120503" in r["mensagem"] and "70 unidade(s)" in r["mensagem"]


def test_a_tela_do_estoque_entrega_o_aviso(client, admin_headers):
    _cenario()
    r = client.get("/api/farmacia/estoque", params={"farmacia": HEMO, "busca": ETIQUETA}, headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert "SP1024120503" in d["aviso_lote"]
    assert any(o["quantidade"] == 70 for o in d["onde_esta"])
