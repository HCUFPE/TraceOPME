# tests/test_v18_25_ordens_da_etiqueta.py
"""A etiqueta não precisa vir na ordem (01)(10)(17).

Pergunta da Camila (18/11/2026): "tem etiquetas que não seguem essa sequência
(01)...(10)...(17) — tá funcionando normal?". Este arquivo é a resposta por
teste: ordens trocadas, campos de tamanho variável colados sem separador, e
etiquetas que nem são GS1.
"""
import pytest

from src.providers.implementations.opme.services import estoque

GS = "\x1d"
LOTE, VAL17, VALISO = "SP11250314005", "280316", "2028-03-16"

ORDENS = [
    ("01 10 17 colado", "01{g}10" + LOTE + "17" + VAL17, LOTE),
    ("01 17 10", "01{g}17" + VAL17 + "10" + LOTE, LOTE),
    ("01 10 17 com FNC1", "01{g}10" + LOTE + GS + "17" + VAL17, LOTE),
    ("17 01 10", "17" + VAL17 + "01{g}10" + LOTE, LOTE),
    ("10 01 17", "10" + LOTE + GS + "01{g}17" + VAL17, LOTE),
    ("10 17 01", "10" + LOTE + GS + "17" + VAL17 + "01{g}", LOTE),
    ("01 21 10 17", "01{g}21SER77" + GS + "10" + LOTE + GS + "17" + VAL17, LOTE),
    ("01 11 17 10", "01{g}11250101" + "17" + VAL17 + "10" + LOTE, LOTE),
    ("01 17 11 10", "01{g}17" + VAL17 + "11250101" + "10" + LOTE, LOTE),
    ("01 30 10 17", "01{g}3002" + GS + "10" + LOTE + GS + "17" + VAL17, LOTE),
    ("01 240 10 17", "01{g}240REF9" + GS + "10" + LOTE + GS + "17" + VAL17, LOTE),
    ("01 10 21 17", "01{g}10" + LOTE + GS + "21SER77" + GS + "17" + VAL17, LOTE),
    ("só 10 17, sem GTIN", "10" + LOTE + GS + "17" + VAL17, LOTE),
    ("só 17 10, sem GTIN", "17" + VAL17 + "10" + LOTE, LOTE),
    ("parênteses legíveis", "(01){g}(17)" + VAL17 + "(10)" + LOTE, LOTE),
    ("parênteses, lote antes", "(01){g}(10)" + LOTE + "(17)" + VAL17, LOTE),
    ("01 13 10 (embalagem)", "01{g}13250101" + "10" + LOTE, LOTE),
    ("02 37 10 (agrupado)", "02{g}3710" + GS + "10" + LOTE + GS + "17" + VAL17, LOTE),
    # campos de tamanho variável COLADOS, sem separador: o caso difícil
    ("10 + 21 colados", "01{g}10" + LOTE + "21SER77", LOTE),
    ("10 + 11 colados", "01{g}10" + LOTE + "11250101", LOTE),
    ("10 + 15 colados", "01{g}10" + LOTE + "15" + VAL17, LOTE),
    ("10 + 30 colados", "01{g}10" + LOTE + "3002", LOTE),
    ("10 + 240 colados", "01{g}10" + LOTE + "240REF9", LOTE),
    ("10 + 17 + 21 colados", "01{g}10" + LOTE + "17" + VAL17 + "21SER77", LOTE),
    ("21 antes do 10, colados", "01{g}21SER77" + "10" + LOTE, LOTE),
    ("lote só de dígitos + 17", "01{g}10" + "9988776655" + "17" + VAL17, "9988776655"),
    ("lote curto + 17", "01{g}10" + "AB12" + "17" + VAL17, "AB12"),
    ("lote com '17' no meio", "01{g}10" + "SP17280316X9" + "17" + VAL17, "SP17280316X9"),
]


def _cadastrar(aghu, codigo, lote, validade=VALISO):
    ok, msg = estoque.cadastrar_manual({
        "xProd": f"ORDEM {aghu}", "codigo_barras": codigo, "codigo_aghu": str(aghu),
        "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": validade,
        "quantidade": "2", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, msg


@pytest.mark.parametrize("nome,molde,lote", ORDENS, ids=[o[0] for o in ORDENS])
def test_a_ordem_dos_campos_nao_importa(client, nome, molde, lote):
    aghu = 970000 + [o[0] for o in ORDENS].index(nome)
    g = f"789{aghu:011d}"
    _cadastrar(aghu, g, lote)
    etiqueta = molde.format(g=g)
    achadas = [a for a in estoque.buscar_unidades(etiqueta, "ativos")
               if a["codigo_aghu"] == str(aghu)]
    assert len(achadas) == 2, f"{nome}: achou {len(achadas)} de 2"


NAO_GS1 = [
    ("EAN-13 simples", "7891234567895", "7891234567895"),
    ("cadastrado com zero à frente", "7891234567896", "07891234567896"),
    ("Code128 com letras", "ABC-12345-X", "ABC-12345-X"),
    ("código do fabricante", "REF99887", "REF99887"),
    ("com espaços do leitor", "  7891234567897  ", "7891234567897"),
    ("UPC de 12 dígitos", "012345678905", "012345678905"),
    ("cadastrado 13, bipado 14", "07891234567899", "7891234567899"),
    ("cadastrado 14, bipado 13", "7891234567881", "07891234567881"),
]


@pytest.mark.parametrize("nome,bipado,cadastrado", NAO_GS1, ids=[c[0] for c in NAO_GS1])
def test_etiqueta_que_nao_e_gs1(client, nome, bipado, cadastrado):
    aghu = 990000 + [c[0] for c in NAO_GS1].index(nome)
    _cadastrar(aghu, cadastrado, f"L{aghu}")
    achadas = [a for a in estoque.buscar_unidades(bipado, "ativos")
               if a["codigo_aghu"] == str(aghu)]
    assert len(achadas) == 2, f"{nome}: achou {len(achadas)} de 2"
