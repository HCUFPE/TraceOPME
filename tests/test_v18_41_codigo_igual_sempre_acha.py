# tests/test_v18_41_codigo_igual_sempre_acha.py
"""v18.41: o texto bipado, igual ao gravado, sempre acha o material.

Camila (20/11/2026): "porque esse não é identificado: 10706;26. pq é
exatamente o que está aparecendo na bipagem dos itens."

O código "10706;26" (SET DE MANGUEIRAS, AGHU 403331) começa com "10", que em
GS1 é o identificador de LOTE. O sistema lia a etiqueta, concluía que o lote
era "706;26" e procurava por esse lote — mas o cadastro tem o lote "1070626".
Resultado: 0 unidades, mesmo o código bipado sendo idêntico ao gravado.

Agora a igualdade literal do código entra sempre na busca, junto da leitura da
etiqueta. Não é busca por semelhança: só acha o que tem exatamente aquele
código.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import estoque, fluxo
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA

FARM = "BLOCO CIRURGICO"


def _cadastrar(cod, aghu, lote, val, nome, q=3):
    ok, m = estoque.cadastrar_manual({
        "xProd": nome, "codigo_barras": cod, "codigo_aghu": aghu, "fornecedor": "F",
        "marca_fabricante": "M", "nLote": lote, "dVal": val, "quantidade": str(q),
        "tipo_entrada": "aquisicao_propria"}, "almox")
    assert ok, m


def _acha(termo, aghu):
    return [a for a in estoque.buscar_unidades(termo, "ativos") if a["codigo_aghu"] == aghu]


def test_o_caso_do_set_de_mangueiras(client):
    _cadastrar("10706;26", "403331", "1070626", "2028-06-30", "SET DE MANGUEIRAS HISTEROSCOPIA")
    # o cadastro grava o código como foi bipado
    assert db.escalar("SELECT codigo_barras FROM unidades WHERE codigo_aghu='403331'") == "10706;26"
    achadas = _acha("10706;26", "403331")
    assert len(achadas) == 3, "bipar o mesmo código tem de achar as 3 unidades"


def test_nao_acha_codigo_parecido(client):
    """Igualdade literal: não pode trazer material de código vizinho."""
    _cadastrar("10706;27", "403332", "1070627", "2028-06-30", "SET VIZINHO")
    assert _acha("10706;26", "403332") == []
    assert len(_acha("10706;27", "403332")) == 3


def test_a_bipagem_do_fluxo_tambem_acha(client):
    _cadastrar("10806;26", "403333", "1080626", "2028-06-30", "SET NO FLUXO", q=1)
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE codigo_aghu = '403333'",
                (EM_ESTOQUE_FARMACIA, FARM))
    elegiveis = fluxo.buscar_elegiveis("saida_outros", "10806;26", farmacia=FARM)
    assert [e for e in elegiveis if e["aghu"] == "403333"], "o bipe no fluxo tem de achar"


def test_etiqueta_normal_continua_igual(client):
    """A leitura da etiqueta GS1 não muda: o lote continua mandando."""
    _cadastrar("07891111111118", "403334", "SP11250314005", "2028-03-16", "MATERIAL NORMAL")
    assert len(_acha("010789111111111810SP1125031400517280316", "403334")) == 3
    # o GTIN sozinho também, como sempre
    assert len(_acha("07891111111118", "403334")) == 3
    # e a etiqueta de outro produto não traz este material
    assert _acha("010789222222222510SP1125031400517280316", "403334") == []
