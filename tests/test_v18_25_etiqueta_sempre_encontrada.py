# tests/test_v18_25_etiqueta_sempre_encontrada.py
"""v18.25: a etiqueta do produto tem de achar o material cadastrado.

Camila (18/11/2026): "está dando muitos erros de não identificar a etiqueta,
apesar de ter sido registrado. eu estou bipando exatamente a etiqueta do
produto, quando a entrada é manual."

Duas famílias de caso, testadas de ponta a ponta (cadastro manual → busca):

A) a etiqueta chega de jeitos diferentes do leitor (ordem dos campos, com e sem
   separador, Caps Lock, Enter, espaços, série, quantidade, hífen no lote...);
B) o cadastro manual NÃO guardou o GTIN da etiqueta — guardou o EAN da caixa, o
   código AGHU, outro GTIN, ou o campo Lote recebeu a etiqueta inteira / o
   rótulo "LOTE:" junto. Aqui a busca passa a achar pelo lote + validade.
"""
import pytest

from src.providers.implementations.opme import gs1
from src.providers.implementations.opme.services import estoque

GS = "\x1d"

# (nome, molde com {g} no lugar do GTIN, lote impresso, validade impressa)
LEITURAS = [
    ("GTIN + validade + lote", "01{g}172806241039671573", "39671573", "24/06/2028"),
    ("lote e validade colados, 21 caracteres", "01{g}10SP1125031400517280316", "SP11250314005", "16/03/2028"),
    ("lote e validade colados, 20 caracteres", "01{g}10SP102412050317271204", "SP1024120503", "04/12/2027"),
    ("com separador FNC1", "01{g}10SP11250314005" + GS + "17280316", "SP11250314005", "16/03/2028"),
    ("prefixo de simbologia ]d2", "]d201{g}10SP1125031400517280316", "SP11250314005", "16/03/2028"),
    ("Caps Lock ligado no leitor", "01{g}10sp1125031400517280316", "SP11250314005", "16/03/2028"),
    ("número de série com separador", "01{g}10LOT2025A" + GS + "21SER0001", "LOT2025A", ""),
    ("número de série colado no lote", "01{g}10LOT2025A21SER0001", "LOT2025A", ""),
    ("data de fabricação antes do lote", "01{g}1125010110LOTE77", "LOTE77", ""),
    ("quantidade (30) depois do lote", "01{g}10LOTE88" + GS + "3005", "LOTE88", ""),
    ("lote numérico terminando em data", "01{g}17280812109686013291009", "9686013291009", "12/08/2028"),
    ("lote com hífen", "01{g}10000083-25-0117280930", "000083-25-01", "30/09/2028"),
    ("lote com barra", "01{g}10AB/2025" + GS + "17280316", "AB/2025", "16/03/2028"),
    ("Enter no fim da leitura", "01{g}10SP1125031400517280316\r\n", "SP11250314005", "16/03/2028"),
    ("espaços no meio", "01{g} 10SP11250314005 17280316", "SP11250314005", "16/03/2028"),
    ("lote digitado em minúsculas", "01{g}10SP1125031400517280316", "sp11250314005", "16/03/2028"),
    ("lote com zero à esquerda", "01{g}10007788" + GS + "17280316", "007788", "16/03/2028"),
    ("AI 240 depois do lote", "01{g}10LOTE99" + GS + "240ABC123", "LOTE99", ""),
    ("só o GTIN no código de barras", "01{g}", "QUALQUER", ""),
]


def _gtin(semente: int) -> str:
    return f"789{semente:011d}"


def _cadastrar(aghu, codigo_barras, lote, validade, descricao="MATERIAL"):
    ok, msg = estoque.cadastrar_manual({
        "xProd": descricao, "codigo_barras": codigo_barras, "codigo_aghu": str(aghu),
        "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
        "dVal": validade or "2030-01-01", "quantidade": "2",
        "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, msg


@pytest.mark.parametrize("nome,molde,lote,validade", LEITURAS,
                         ids=[c[0] for c in LEITURAS])
def test_a_etiqueta_bipada_acha_o_que_foi_cadastrado(client, nome, molde, lote, validade):
    aghu = 930000 + LEITURAS.index((nome, molde, lote, validade))
    g = _gtin(aghu)
    etiqueta = molde.format(g=g)
    _cadastrar(aghu, etiqueta, lote, validade, f"MATERIAL {nome}")
    achadas = [a for a in estoque.buscar_unidades(etiqueta, "ativos")
               if a["codigo_aghu"] == str(aghu)]
    assert len(achadas) == 2, f"{nome}: achou {len(achadas)} de 2"


# ---------------------------------------------------------------------------
# B) cadastro manual sem o GTIN da etiqueta: NÃO acha — e é assim que tem de ser
#
# Decisão da Camila (18/11/2026): quando o código de barras da etiqueta não é o
# do cadastro, os códigos são de fato diferentes. Achar o material por lote e
# validade mascararia um cadastro errado e confundiria quem está bipando. A
# tela diz que não encontrou; o conserto é corrigir o cadastro.
# ---------------------------------------------------------------------------
LOTE, VALIDADE = "SP11250314005", "2028-03-16"
CADASTROS = [
    ("código de barras é outro GTIN", "07891111111118", LOTE),
    ("código AGHU no lugar do GTIN", "99123", LOTE),
    ("EAN-13 da caixa, sem o dígito do GTIN", "7891111111118", LOTE),
]


@pytest.mark.parametrize("nome,codigo,lote", CADASTROS, ids=[c[0] for c in CADASTROS])
def test_nao_acha_quando_o_codigo_cadastrado_e_outro(client, nome, codigo, lote):
    aghu = 940000 + [c[0] for c in CADASTROS].index(nome)
    _cadastrar(aghu, codigo, lote, VALIDADE, f"OUTRO {nome}")
    etiqueta = f"01{_gtin(aghu)}10SP1125031400517280316"
    achadas = [a for a in estoque.buscar_unidades(etiqueta, "ativos")
               if a["codigo_aghu"] == str(aghu)]
    assert achadas == [], f"{nome}: o código é outro, não pode achar"


def test_o_campo_lote_e_limpo_no_cadastro(client):
    """A etiqueta bipada no campo Lote vira só o lote — e traz a validade."""
    assert gs1.lote_limpo("LOTE: SP11250314005") == "SP11250314005"
    assert gs1.lote_limpo("0107891111111118" + "10SP1125031400517280316") == "SP11250314005"
    for intocado in ("LOT2025A", "LOTE99", "L1234", "9686013291005"):
        assert gs1.lote_limpo(intocado) == intocado

    limpo = estoque.limpar_lote_do_formulario(
        {"nLote": "0107891111111118" + "10SP1125031400517280316", "dVal": ""})
    assert limpo["nLote"] == "SP11250314005" and limpo["dVal"] == "2028-03-16"


def test_a_tela_de_consultas_diz_que_nao_encontrou(client, admin_headers):
    aghu = 943000
    _cadastrar(aghu, "07899000000023", "SP44556677", "2029-07-07", "NAO ENCONTRA")
    etiqueta = f"01{_gtin(aghu)}10SP4455667717290707"
    r = client.get("/api/consultas/itens", params={"busca": etiqueta}, headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert [i for i in d["itens"] if i["codigo_aghu"] == str(aghu)] == []
