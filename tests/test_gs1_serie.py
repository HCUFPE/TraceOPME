# tests/test_gs1_serie.py
"""Etiqueta com quantidade (30) seguida de série (21), sem lote (nov/2026).

0107899330204645 17300415 3001 21S0000002545 → GTIN, validade, qtd 01, série.
Antes a quantidade era lida como "0" e a série se perdia, e a busca mostrava
todas as unidades do GTIN.
"""
from src.providers.implementations.opme import gs1

ETIQUETA = "010789933020464517300415300121S0000002545"


def test_le_quantidade_e_serie():
    e = gs1.interpretar(ETIQUETA)
    assert e["gtin"] == "07899330204645" and e["validade"] == "2030-04-15"
    assert e["serie"] == "S0000002545" and e["lote"] == ""


def test_serie_acha_unidade_cadastrada_com_numero_no_lote():
    linhas = [{"nLote": "4114053", "numero_serie": "", "dVal": "2030-04-15"},
              {"nLote": "0000002545", "numero_serie": "", "dVal": "2030-04-15"},
              {"nLote": "0000002546", "numero_serie": "", "dVal": "2030-04-15"}]
    filtradas, aviso = gs1.filtrar(linhas, gs1.interpretar(ETIQUETA))
    assert [l["nLote"] for l in filtradas] == ["0000002545"] and not aviso


def test_quantidade_seguida_de_lote_continua_igual():
    e = gs1.interpretar("01007630007265911728123130051 0C08240A1".replace(" ", ""))
    assert e["lote"] == "C08240A1"


def test_lote_com_campo_91_grudado():
    """(10)21680129 (91)048 sem separador: o cadastro guardou 21680129048 (nov/2026)."""
    linhas = [{"nLote": "21680129048", "numero_serie": "", "dVal": "2029-08-07"},
              {"nLote": "21680129049", "numero_serie": "", "dVal": "2029-08-07"}]
    for final, lote in (("048", "21680129048"), ("049", "21680129049")):
        e = gs1.interpretar(f"0106939963821688172908071021680129" + "91" + final)
        filtradas, aviso = gs1.filtrar(linhas, e)
        assert [l["nLote"] for l in filtradas] == [lote] and not aviso


def test_lote_exato_tem_preferencia():
    linhas = [{"nLote": "ABC91", "numero_serie": "", "dVal": ""}, {"nLote": "ABC", "numero_serie": "", "dVal": ""}]
    e = gs1.interpretar("010693996382168810ABC91")
    assert [l["nLote"] for l in gs1.filtrar(linhas, e)[0]] == ["ABC91"]
