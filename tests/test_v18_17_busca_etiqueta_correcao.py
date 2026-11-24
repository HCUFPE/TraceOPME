# tests/test_v18_17_busca_etiqueta_correcao.py
"""v18.17: bipar a etiqueta GS1 em "Corrigir cadastro" tem de trazer a unidade da etiqueta.

Caso real (HC-UFPE, 17/11/2026): a etiqueta
`0100886333004515` + `17281218` + `1011551894` (GTIN, validade, lote) não "achava"
o item. Achava — mas a tela abria com os grupos de OUTROS lotes do mesmo produto
em cima e a unidade do lote bipado escondida dentro de "Ou corrija uma unidade
por vez".
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_RECEBIMENTO
from src.providers.implementations.opme.services import estoque

GTIN = "00886333004515"
ETIQUETA = "0100886333004515172812181011551894"      # GTIN + val. 18/12/2028 + lote 11551894


def _cad(lote, validade, quantidade, fornecedor="ECOMED"):
    ok, m = estoque.cadastrar_manual({
        "xProd": "CONJUNTO ACESSO PERCUTANEO", "codigo_barras": GTIN, "codigo_aghu": "87446",
        "fornecedor": fornecedor, "marca_fabricante": "ARGON", "nLote": lote,
        "dVal": validade, "quantidade": str(quantidade), "tipo_entrada": "aquisicao_propria",
    }, "admin")
    assert ok, m


_JA_CADASTRADO: list = []


def _cenario():
    """Cadastra uma vez só — os testes do arquivo compartilham o mesmo banco."""
    if _JA_CADASTRADO:
        return
    _JA_CADASTRADO.append(True)
    _cad("11500789", "2028-09-28", 4)          # grupo de 4
    _cad("11628440", "2030-06-27", 2)          # grupo de 2
    _cad("11551894", "2028-12-18", 1, "ARGO")  # a unidade da etiqueta, sozinha


def test_etiqueta_traz_a_unidade_do_lote_bipado(client):
    _cenario()
    achado = estoque.para_correcao(ETIQUETA)

    # a etiqueta foi entendida
    assert achado["etiqueta"]["gtin"] == GTIN
    assert achado["etiqueta"]["lote"] == "11551894"
    # a unidade da etiqueta é a que aparece — e só ela
    assert [i["nLote"] for i in achado["itens"]] == ["11551894"]
    # e nenhum grupo de outro lote rouba o topo da tela
    assert achado["grupos"] == []
    assert achado["aviso"] == ""


def test_etiqueta_de_lote_com_grupo_mostra_o_grupo_certo(client):
    _cenario()
    achado = estoque.para_correcao("0100886333004515172809281011500789")
    assert [g["nLote"] for g in achado["grupos"]] == ["11500789"]
    assert [g["quantidade"] for g in achado["grupos"]] == [4]
    assert {i["nLote"] for i in achado["itens"]} == {"11500789"}


def test_lote_da_etiqueta_nao_cadastrado_nao_esconde_nada(client):
    """O cadastro é que está errado: a tela mostra tudo do produto e avisa."""
    _cenario()
    # validade 31/12/2099 e lote 9999999: nada confere
    achado = estoque.para_correcao("0100886333004515179912311019999999")
    assert achado["aviso"] and "não confere" in achado["aviso"]
    assert {i["nLote"] for i in achado["itens"]} == {"11500789", "11628440", "11551894"}
    assert {g["nLote"] for g in achado["grupos"]} == {"11500789", "11628440"}


def test_busca_por_lote_e_por_codigo_continuam_funcionando(client):
    _cenario()
    assert [i["nLote"] for i in estoque.para_correcao("11551894")["itens"]] == ["11551894"]
    assert len(estoque.para_correcao("87446")["itens"]) == 7          # código AGHU
    assert len(estoque.para_correcao(GTIN)["itens"]) == 7             # GTIN digitado
    assert len(estoque.para_correcao("886333004515")["itens"]) == 7   # sem os zeros da frente


def test_tela_de_correcao_responde_com_a_etiqueta(client, admin_headers):
    _cenario()
    r = client.get(f"/api/almoxarifado/correcoes?busca={ETIQUETA}", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert d["etiqueta"]["lote"] == "11551894"
    assert len(d["itens"]) == 1 and not d["grupos"]


def test_itens_rastreados_acham_pela_etiqueta(client):
    _cenario()
    linhas = estoque.buscar_unidades(ETIQUETA, "ativos")
    assert [l["nLote"] for l in linhas] == ["11551894"]
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE status = ?", (EM_ESTOQUE_RECEBIMENTO,)) >= 7


def test_mesmo_lote_vira_um_cartao_so(client):
    """Mesmo produto/lote/validade cadastrado com fornecedores diferentes = 1 cartão."""
    gtin2 = "17898660490411"
    for fornecedor, marca, fab, quantas in (("Gabisa Medical", "Gabisa Medical International S.A", "", 9),
                                            ("GMI", "GMI", "2025-10-31", 3),
                                            ("GMI", "GMI", "", 2)):
        ok, m = estoque.cadastrar_manual({
            "xProd": "CATETER CENTRAL", "codigo_barras": gtin2, "codigo_aghu": "401557",
            "fornecedor": fornecedor, "marca_fabricante": marca, "nLote": "GB2413",
            "dFab": fab, "dVal": "2030-11-30", "quantidade": str(quantas),
            "tipo_entrada": "aquisicao_propria"}, "admin")
        assert ok, m

    grupos = estoque.grupos_para_correcao(gtin2)
    assert len(grupos) == 1                      # antes eram 3 cartões iguais na tela
    g = grupos[0]
    assert g["quantidade"] == 14 and len(g["ids"]) == 14
    assert g["nLote"] == "GB2413" and g["dVal"] == "2030-11-30"
    # o que diverge vem vazio, com a lista do que está cadastrado
    assert g["fornecedor"] == "" and g["marca_fabricante"] == ""
    assert g["misto"]["fornecedor"] == [{"valor": "Gabisa Medical", "quantidade": 9},
                                        {"valor": "GMI", "quantidade": 5}]
    assert [m["quantidade"] for m in g["misto"]["dFab"]] == [11, 3]
    # e o que é igual continua preenchido
    assert "codigo_aghu" not in g["misto"] and g["codigo_aghu"] == "401557"


def test_lotes_diferentes_continuam_em_cartoes_diferentes(client):
    _cenario()
    grupos = {g["nLote"]: g["quantidade"] for g in estoque.grupos_para_correcao(GTIN)}
    assert grupos == {"11500789": 4, "11628440": 2}


def test_etiqueta_com_validade_colada_no_lote(client, admin_headers):
    """`10 SP1124082036` + `17 270904` sem separador chega grudado no leitor."""
    from src.providers.implementations.opme import gs1
    lido = gs1.interpretar("010694945040369310SP112408203617270904")
    assert lido["lote"] == "SP112408203617270904"      # leitura crua
    assert lido["lote_curto"] == "SP1124082036"        # leitura alternativa
    assert lido["validade_do_lote"] == "2027-09-04"

    ok, m = estoque.cadastrar_manual({
        "xProd": "CATETER DIAGNOSTICO 5F", "codigo_barras": "06949450403693", "codigo_aghu": "87435",
        "fornecedor": "APT", "marca_fabricante": "APT", "nLote": "SP1124082036",
        "dVal": "2027-09-04", "quantidade": "3", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    # a unidade certa é achada, e a tela NÃO diz "código de barras não encontrado"
    linhas = estoque.buscar_unidades("010694945040369310SP112408203617270904", "ativos")
    assert len(linhas) == 3 and {l["nLote"] for l in linhas} == {"SP1124082036"}
    r = client.get("/api/consultas/itens?busca=010694945040369310SP112408203617270904",
                   headers=admin_headers)
    assert r.status_code == 200
    assert not r.json()["dados"]["lote_nao_encontrado"]


def test_lote_que_termina_em_numeros_de_data_continua_inteiro(client):
    """Regressão: 9686013291005 é o lote inteiro, não "96860" + data."""
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA", "codigo_barras": "07891234567895", "codigo_aghu": "77001",
        "fornecedor": "F", "marca_fabricante": "M", "nLote": "9686013291005",
        "dVal": "2028-08-11", "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    assert estoque.buscar_unidades("17280811109686013291005")


def test_caps_lock_nao_atrapalha(client):
    """Leitor com Caps Lock ligado: letras invertidas na etiqueta e no prefixo."""
    from src.providers.implementations.opme import gs1
    ok, m = estoque.cadastrar_manual({
        "xProd": "CATETER CAPS", "codigo_barras": "06949450403693", "codigo_aghu": "87435",
        "fornecedor": "APT", "marca_fabricante": "APT", "nLote": "SP1124082036",
        "dVal": "2027-09-04", "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    etiqueta = "010694945040369310SP112408203617270904"
    for lido in (etiqueta, etiqueta.swapcase(), "]C1" + etiqueta, "]c1" + etiqueta.swapcase()):
        assert gs1.interpretar(lido), lido
        assert estoque.buscar_unidades(lido, "ativos"), lido
