# tests/test_v18_etiqueta_partes.py
"""v18 (item 14): cadastrado pela etiqueta GS1 completa, o material é achado
bipando só a etiqueta do GTIN ou só a etiqueta de validade/lote."""
import pytest

from src.providers.implementations.opme import db, gs1
from src.providers.implementations.opme.services import estoque, remessas

COMPLETA = "(01)06942180396860(17)280811(10)96860132(91)005"
SO_GTIN = ["0106942180396860", "(01)06942180396860", "]C10106942180396860"]
SO_LOTE = ["(17)280811(10)96860132(91)005", "172808111096860132\x1d91005", "17280811109686013291005"]


def test_interpreta_cada_etiqueta():
    for c in SO_GTIN:
        assert gs1.interpretar(c)["gtin"] == "06942180396860", c
    for c in SO_LOTE:
        e = gs1.interpretar(c)
        assert e["validade"] == "2028-08-11" and not e["gtin"], c


@pytest.mark.parametrize("lido", SO_GTIN + SO_LOTE)
def test_acha_pela_parte_da_etiqueta(client, lido):
    if db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = '96860132' AND status = 'em_estoque_recebimento'"):
        ok, m = True, ""
    else:
        ok, m = estoque.cadastrar_manual({"xProd": "FIREFIGHTER NC 2.50X10", "codigo_barras": COMPLETA, "codigo_aghu": "5555",
                                      "fornecedor": "MICROPORT", "marca_fabricante": "MicroPort", "nLote": "96860132",
                                      "dVal": "2028-08-11", "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    # busca das telas (Consultas, estoque...)
    assert estoque.buscar_unidades(lido), lido
    # bipagem do envio almoxarifado → farmácia
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    r = remessas.bipar(id_r, lido, "admin")
    assert r["ok"], (lido, r)
    remessas.cancelar(id_r, "admin", "teste")
