# tests/test_v18_26_caso_fio_guia_87578.py
"""Caso real (HC-UFPE, 18/11/2026): FIO GUIA HIDROFÍLICO 0,35 — AGHU 87578.

A farmácia da Hemodinâmica bipou `010694945040140810SP102502270817280302` e a
tela respondeu "0 unidade(s) em estoque"; buscando por 87578 apareciam as 9
unidades, lote SP1025022708, validade 02/03/2028.

Decisão da Camila: o código de barras da etiqueta é de fato DIFERENTE do que
está no cadastro — então a tela deve continuar dizendo que não encontrou. O
conserto é corrigir o cadastro, não o sistema adivinhar pelo lote.

O que precisa estar certo, e é o que se testa aqui:
  1. a leitura da etiqueta: `SP1025022708` + validade `280302` chegam grudados
     e ainda podiam ser lidos como lote + quantidade "302" — fica o corte que
     revela a validade;
  2. com o cadastro certo, a etiqueta acha pelo próprio código de barras;
  3. com o cadastro errado, não acha (e a correção de cadastro é o caminho).
"""
from src.providers.implementations.opme import db, gs1
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import estoque

ETIQUETA = "010694945040140810SP102502270817280302"
HEMO = "HEMODINAMICA - PDT"
LOTE, VALIDADE = "SP1025022708", "2028-03-02"


def _cadastrar(aghu, codigo, quantidade="9"):
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA HIDROFILICO DE 0,35", "codigo_barras": codigo, "codigo_aghu": str(aghu),
        "fornecedor": "APT MEDICAL", "marca_fabricante": "BLACKEEL", "nLote": LOTE,
        "dVal": VALIDADE, "quantidade": quantidade, "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE codigo_aghu = ?",
                (EM_ESTOQUE_FARMACIA, HEMO, str(aghu)))


def test_a_etiqueta_revela_lote_e_validade(client):
    """`SP102502270817280302` = lote SP1025022708 + validade 02/03/2028."""
    lido = gs1.interpretar(ETIQUETA)
    assert lido["gtin"] == "06949450401408"
    assert lido["lote_curto"] == LOTE
    assert lido["validade_do_lote"] == VALIDADE


def test_com_o_cadastro_certo_a_etiqueta_acha(client):
    _cadastrar("875799", "06949450401408")
    achadas = [a for a in estoque.buscar_unidades(ETIQUETA, "ativos")
               if a["codigo_aghu"] == "875799"]
    assert len(achadas) == 9


def test_a_tela_do_estoque_da_farmacia_lista_as_9(client, admin_headers):
    _cadastrar("875798", "06949450401408")
    r = client.get("/api/farmacia/estoque", params={"farmacia": HEMO, "busca": ETIQUETA},
                   headers=admin_headers)
    assert r.status_code == 200
    linhas = [l for l in r.json()["dados"]["linhas"] if l["codigo_aghu"] == "875798"]
    assert linhas and linhas[0]["quantidade"] == 9
    assert not r.json()["dados"]["aviso_lote"]


def test_com_o_codigo_errado_no_cadastro_nao_acha(client):
    """Códigos diferentes são materiais diferentes — nada de achar pelo lote."""
    for n, codigo in enumerate(["06949450401405", "16949450401405", "87578"], 1):
        aghu = f"8757{n}"
        _cadastrar(aghu, codigo)
        achadas = [a for a in estoque.buscar_unidades(ETIQUETA, "ativos")
                   if a["codigo_aghu"] == aghu]
        assert achadas == [], codigo


def test_corrigido_o_cadastro_a_etiqueta_passa_a_achar(client):
    """O caminho de conserto: trocar o código de barras e bipar de novo."""
    _cadastrar("875797", "06949450401405")
    assert [a for a in estoque.buscar_unidades(ETIQUETA, "ativos")
            if a["codigo_aghu"] == "875797"] == []
    db.executar("UPDATE unidades SET codigo_barras = ? WHERE codigo_aghu = '875797'",
                ("06949450401408",))
    achadas = [a for a in estoque.buscar_unidades(ETIQUETA, "ativos")
               if a["codigo_aghu"] == "875797"]
    assert len(achadas) == 9


def test_a_busca_pelo_aghu_continua_achando(client):
    _cadastrar("875796", "06949450401405")
    assert len([a for a in estoque.buscar_unidades("875796", "ativos")]) == 9
