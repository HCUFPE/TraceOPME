# tests/test_v18_43_4_codigo_maiuscula_minuscula.py
"""v18.43.4: código de barras compara sem diferenciar maiúscula de minúscula.

Camila (23/11/2026): bipou `172807111075825071214X` para dispensar e a tela
disse "JÁ REGISTRADO — este item já foi registrado como utilizado em um
paciente (1 unidade nessa situação)", apesar de o rastreio mostrar 6 unidades
do mesmo lote em estoque na farmácia.

No banco dela, o CATETER MIKAELSON (AGHU 24350), lote 75825071214X:
  - 6 unidades cadastradas com código "...75825071214x"  (x minúsculo)
  - 1 unidade, já utilizada,  com código "...75825071214X"  (X maiúsculo)

A comparação de códigos (`gtin`, usada por todas as consultas de bipagem)
diferenciava o caixa quando o código não é numérico. Bipando com X maiúsculo,
só a unidade utilizada casava.
"""
import pytest

from src.providers.implementations.opme import db, gs1
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, UTILIZADO
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo
from src.providers.implementations.opme.utils import hoje_iso

FARM = "HEMODINAMICA - PDT"
LOTE = "75825071214Z"
MINUSCULO = "172807111075825071214z"
MAIUSCULO = "172807111075825071214Z"


def test_gtin_normaliza_o_caixa():
    assert gs1.gtin(MINUSCULO) == gs1.gtin(MAIUSCULO)
    assert gs1.gtin("abc-123") == "ABC-123"
    # o que é número continua como era
    assert gs1.gtin("7898705760038") == "07898705760038"
    assert gs1.gtin("") == "" and gs1.gtin(None) == ""


@pytest.fixture
def cenario(client):
    """6 unidades com x minúsculo na farmácia + 1 utilizada com X maiúsculo."""
    ok, m = estoque.cadastrar_manual({
        "xProd": "CATETER ANGIOGRAFICO MIKAELSON", "codigo_barras": MINUSCULO,
        "codigo_aghu": "243500", "fornecedor": "F", "marca_fabricante": "M",
        "nLote": LOTE, "dVal": "2028-07-11", "quantidade": "6",
        "tipo_entrada": "aquisicao_propria"}, "almox")
    assert ok, m
    db.executar("UPDATE unidades SET codigo_barras = ?, status = ?, farmacia = ? "
                "WHERE codigo_aghu = '243500'", (MINUSCULO, EM_ESTOQUE_FARMACIA, FARM))
    ok, m = estoque.cadastrar_manual({
        "xProd": "CATETER DIAGNOSTICO 5F, TIPO MIKAELSON, 80CM", "codigo_barras": MAIUSCULO,
        "codigo_aghu": "243501", "fornecedor": "F", "marca_fabricante": "M",
        "nLote": LOTE, "dVal": "2028-07-11", "quantidade": "1",
        "tipo_entrada": "aquisicao_propria"}, "almox")
    assert ok, m
    db.executar("UPDATE unidades SET codigo_barras = ?, status = ?, farmacia = ? "
                "WHERE codigo_aghu = '243501'", (MAIUSCULO, UTILIZADO, FARM))
    ok, ida = atendimentos.abrir({"prontuario": "24350001", "paciente": "PACIENTE TESTE",
                                  "unidade": FARM, "sala": "07", "especialidade": "HEMODINAMICA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


@pytest.mark.parametrize("bipado", [MAIUSCULO, MINUSCULO], ids=["X maiúsculo", "x minúsculo"])
def test_dispensa_acha_as_disponiveis(client, cenario, bipado):
    r = fluxo.bipar(operacao="dispensar_sala", codigo=bipado, usuario="farm1",
                    id_atendimento=cenario, farmacia=FARM, ciencia_validade=True)
    assert r["ok"], r.get("mensagem")
    assert "MIKAELSON" in r["mensagem"]
    usada = db.consultar_um("SELECT codigo_aghu FROM unidades WHERE id_atendimento = ?", (cenario,))
    assert usada["codigo_aghu"] == "243500", "tem de pegar uma das 6 disponíveis"


def test_a_busca_junta_as_duas_grafias(client, cenario):
    """As duas grafias trazem exatamente as mesmas unidades."""
    def ids(termo):
        return {u["id_unidade"] for u in estoque.buscar_unidades(termo, "ativos")
                if u["codigo_aghu"] in ("243500", "243501")}
    assert ids(MAIUSCULO) == ids(MINUSCULO) != set()


def test_a_utilizada_continua_protegida(client, cenario):
    """Se SÓ houver unidade utilizada, o aviso de 'já registrado' continua."""
    db.executar("UPDATE unidades SET status = ? WHERE codigo_aghu = '243500'", (UTILIZADO,))
    r = fluxo.bipar(operacao="dispensar_sala", codigo=MAIUSCULO, usuario="farm1",
                    id_atendimento=cenario, farmacia=FARM)
    assert not r["ok"] and "utilizado" in r["mensagem"].lower()
