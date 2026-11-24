# tests/test_v18_43_1_codigo_nao_e_etiqueta.py
"""v18.43.1: código cadastrado não é lido como etiqueta GS1.

Camila (20/11/2026), enviando material do almoxarifado para a Farmácia da
Hemodinâmica, bipando o código do SET DE MANGUEIRAS (AGHU 403331):

    "O lote da etiqueta (706;26) NÃO foi encontrado no estoque do
     almoxarifado. Confira a embalagem. Se o material for mesmo um destes
     lotes, escolha:"  → e logo abaixo, o próprio material, lote 1070626.

O código é "10706;26". Começa com "10", que em GS1 é o identificador de LOTE,
então o sistema o lia como etiqueta e concluía que o lote era "706;26". A
18.41 já fazia o material ser ENCONTRADO (por isso ele aparecia na lista), mas
a comparação do lote continuava valendo e a tela pedia confirmação a cada bipe.

Agora: se o texto bipado está gravado como código de barras de alguma unidade,
ele é um código, não uma etiqueta. A leitura GS1 das etiquetas de verdade não
muda.
"""
from src.providers.implementations.opme import busca, db
from src.providers.implementations.opme.services import estoque, remessas

COD = "10776;26"   # mesmo formato do caso real (10706;26), único neste teste
FARM = "HEMODINAMICA - PDT"


def _cadastrar(cod, aghu, lote, nome, q=3, val="2028-06-30"):
    ok, m = estoque.cadastrar_manual({
        "xProd": nome, "codigo_barras": cod, "codigo_aghu": aghu, "fornecedor": "F",
        "marca_fabricante": "M", "nLote": lote, "dVal": val, "quantidade": str(q),
        "tipo_entrada": "aquisicao_propria"}, "almox")
    assert ok, m


def test_o_caso_do_set_de_mangueiras(client):
    _cadastrar(COD, "433101", "1077626", "SET DE MANGUEIRAS FLEXIVEIS P/ HISTEROSCOPIA")
    ok, id_rem = remessas.abrir(FARM, "almox")
    assert ok, id_rem
    r = remessas.bipar(id_rem, COD, "almox")
    assert r["ok"], r.get("mensagem")
    assert not r.get("escolher"), "não pode mais pedir para escolher o lote"
    assert "1077626" in r["mensagem"]


def test_codigo_cadastrado_nao_vira_etiqueta(client):
    _cadastrar("10806;26", "433102", "1080626", "OUTRO SET", q=1)
    assert busca.interpretar("10806;26") is None
    assert busca.e_codigo_cadastrado("10806;26")
    assert not busca.e_codigo_cadastrado("10806;99")


def test_etiqueta_de_verdade_continua_sendo_lida(client):
    """O que não está cadastrado como código continua sendo lido como etiqueta."""
    et = "1727101810MK19A1"
    assert not busca.e_codigo_cadastrado(et)
    lido = busca.interpretar(et)
    assert lido and lido["lote"] == "MK19A1" and lido["validade"] == "2027-10-18"


def test_aviso_de_lote_errado_continua_valendo(client):
    """A proteção que motivou a mensagem não se perde: etiqueta com lote que
    não existe no estoque continua pedindo confirmação."""
    _cadastrar("07894311000013", "433103", "LOTECERTO431", "MATERIAL COM ETIQUETA", q=2,
               val="2029-05-20")
    ok, id_rem = remessas.abrir(FARM, "almox")
    assert ok, id_rem
    r = remessas.bipar(id_rem, "010789431100001310LOTEERRADO431", "almox")
    assert not r["ok"] and r.get("escolher"), "lote diferente tem de pedir confirmação"
    assert "LOTEERRADO431" in r["mensagem"]


def test_etiqueta_com_o_lote_certo_passa_direto(client):
    _cadastrar("07894311000020", "433104", "LOTEOK431", "MATERIAL ETIQUETA OK", q=2,
               val="2029-05-20")
    ok, id_rem = remessas.abrir(FARM, "almox")
    assert ok, id_rem
    r = remessas.bipar(id_rem, "010789431100002010LOTEOK431", "almox")
    assert r["ok"] and not r.get("escolher"), r.get("mensagem")


def test_a_busca_acha_pelo_codigo(client):
    _cadastrar("10906;26", "433105", "1090626", "SET PARA BUSCA", q=2)
    achadas = [u for u in estoque.buscar_unidades("10906;26", "ativos")
               if u["codigo_aghu"] == "433105"]
    assert len(achadas) == 2


# ------------------------------------------------- etiqueta inteira no cadastro
def test_valvula_com_a_etiqueta_no_lugar_do_codigo(client):
    """Camila, 20/11/2026 21:11: "esse também não está reconhecendo e é
    exatamente o código que bipei" — MATERIAL NÃO CADASTRADO ao bipar
    (01)7898716350358(17)300126(10)260126(21)561193(11)260126.

    O cadastro dessas próteses guardou a etiqueta inteira no campo do código.
    `gtin()` — a forma de comparar código em todas as telas — passa a ler o
    GTIN de dentro da etiqueta, então a bipagem acha o material sem precisar
    corrigir o cadastro.
    """
    etiqueta = "(01)7898716350358(17)300126(10)260126(21)561193(11)260126"
    _cadastrar("07898716350358", "92766", "260126", "PROTESE VALVULAR AORTICA", q=2,
               val="2030-01-26")
    db.executar("UPDATE unidades SET codigo_barras = ? WHERE codigo_aghu = '92766'", (etiqueta,))

    from src.providers.implementations.opme import gs1
    assert gs1.gtin(etiqueta) == "07898716350358"

    ok, id_rem = remessas.abrir(FARM, "almox")
    assert ok, id_rem
    r = remessas.bipar(id_rem, etiqueta, "almox")
    assert r["ok"], r.get("titulo") or r.get("mensagem")

    # e a etiqueta de OUTRA peça do mesmo lote (número de série diferente) também
    r2 = remessas.bipar(id_rem, etiqueta.replace("(21)561193", "(21)999999"), "almox")
    assert r2["ok"], r2.get("titulo") or r2.get("mensagem")


def test_gtin_nao_mexe_no_que_nao_e_etiqueta(client):
    from src.providers.implementations.opme import gs1
    assert gs1.gtin("10706;26") == "10706;26"
    assert gs1.gtin("92529(LOTE1)") == "92529(LOTE1)"
    assert gs1.gtin("1727101810MK19A1212089") == "1727101810MK19A1212089"
    assert gs1.gtin("7898716350358") == "07898716350358"
    assert gs1.gtin("") == "" and gs1.gtin(None) == ""
