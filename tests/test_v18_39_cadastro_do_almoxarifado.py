# tests/test_v18_39_cadastro_do_almoxarifado.py
"""v18.39: o campo "código de barras" recebendo a etiqueta inteira.

Conferindo o cadastro do almoxarifado de 19/11/2026 (banco enviado pela
Camila), 16 unidades ficaram com uma etiqueta no lugar do código do material:

  1727101810MK19A1212089   (12 un) — validade 18/10/2027 + lote MK19A1
  1728121510PTA2512026     ( 2 un) — validade 15/12/2028 + lote PTA2512026
  1727031910202503052      ( 1 un) — validade 19/03/2027 + lote 202503052
  (01)7898716350396(17)300402(10)020426(21)562550(11)260402 (1 un), que ainda
  gravou o lote truncado ("02042" em vez de "020426")

Nenhuma dessas unidades é achada bipando a etiqueta real do produto. A última
nem era reconhecida como GS1, porque o fabricante imprime "(01)" com 13
dígitos.
"""
from src.providers.implementations.opme import db, gs1
from src.providers.implementations.opme.services import estoque

VALVULA = "(01)7898716350396(17)300402(10)020426(21)562550(11)260402"


def test_gtin_com_13_digitos_e_entendido(client):
    lido = gs1.interpretar(VALVULA)
    assert lido and lido["gtin"] == "07898716350396"
    assert lido["lote"] == "020426" and lido["serie"] == "562550"
    assert lido["validade"] == "2030-04-02"


def test_etiqueta_no_campo_do_codigo_vira_gtin_e_preenche_o_resto(client):
    limpo = estoque.limpar_codigo_do_formulario(
        {"codigo_barras": VALVULA, "nLote": "", "dVal": "", "numero_serie": ""})
    assert limpo["codigo_barras"] == "07898716350396"
    assert limpo["nLote"] == "020426"            # antes ficava "02042"
    assert limpo["dVal"] == "2030-04-02"
    assert limpo["numero_serie"] == "562550"


def test_o_que_a_pessoa_digitou_tem_prioridade(client):
    limpo = estoque.limpar_codigo_do_formulario(
        {"codigo_barras": VALVULA, "nLote": "MEU-LOTE", "dVal": "2029-01-01"})
    assert limpo["nLote"] == "MEU-LOTE" and limpo["dVal"] == "2029-01-01"


def test_codigo_normal_nao_e_mexido(client):
    for codigo in ("06949450423790", "7891234567895", "92529(LOTE1)", "REF-123"):
        limpo = estoque.limpar_codigo_do_formulario({"codigo_barras": codigo, "nLote": "L"})
        assert limpo["codigo_barras"] == codigo, codigo


def test_etiqueta_sem_gtin_fica_como_codigo_mesmo(client):
    """`17...10...` só tem validade e lote — e é isso que a embalagem tem.

    Decisão da Camila (20/11/2026): aceitar o código como foi bipado. Bipá-lo
    de novo acha o material pelo lote e pela validade, e exigir outro código
    só daria trabalho de gerar etiqueta.
    """
    limpo = estoque.limpar_codigo_do_formulario(
        {"codigo_barras": "1727101810MK19A1212089", "nLote": "", "dVal": ""})
    assert limpo["codigo_barras"] == "1727101810MK19A1212089"
    assert limpo["nLote"] == "MK19A1" and limpo["dVal"] == "2027-10-18"

    ok, msg = estoque.cadastrar_manual({
        "xProd": "CARGA PARA GRAMPEADOR", "codigo_barras": "1727101810MK19A1212089",
        "codigo_aghu": "102731", "fornecedor": "F", "marca_fabricante": "M",
        "nLote": "", "dVal": "", "quantidade": "12",
        "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, msg
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = 'MK19A1'") == 12


def test_a_etiqueta_sem_gtin_e_achada_de_novo_pelo_lote(client):
    """O que importa: bipar a mesma etiqueta encontra o material."""
    etiqueta = "1728121510PTA2512026"
    ok, msg = estoque.cadastrar_manual({
        "xProd": "FIO DE SUTURA", "codigo_barras": etiqueta, "codigo_aghu": "102732",
        "fornecedor": "F", "marca_fabricante": "M", "nLote": "", "dVal": "",
        "quantidade": "2", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, msg
    achadas = [a for a in estoque.buscar_unidades(etiqueta, "ativos")
               if a["codigo_aghu"] == "102732"]
    assert len(achadas) == 2, "a etiqueta bipada tem de achar o material"
    assert achadas[0]["nLote"] == "PTA2512026"


def test_aviso_de_etiqueta_sem_identificador(client):
    avisos = estoque.avisos_do_cadastro({"codigo_barras": "1727101810MK19A1212089",
                                         "codigo_aghu": "102733", "nLote": "MK19A1"})
    assert any("sem o identificador do produto" in a for a in avisos)


def test_aviso_de_gtin_de_caixa(client):
    avisos = estoque.avisos_do_cadastro({"codigo_barras": "14026704725325",
                                         "codigo_aghu": "90698", "nLote": "73H2501032"})
    assert any("CAIXA" in a and "04026704725325" in a for a in avisos)
    assert estoque.avisos_do_cadastro({"codigo_barras": "04026704725325",
                                       "codigo_aghu": "90698", "nLote": "X"}) == []


def test_aviso_de_lote_ja_cadastrado(client):
    """O caso da prótese cadastrada três vezes no mesmo dia."""
    dados = {"xProd": "PROTESE VALVULAR BIOLOGICA MITRAL 29", "codigo_barras": "07898716350396",
             "codigo_aghu": "84946", "fornecedor": "F", "marca_fabricante": "M",
             "nLote": "020426", "dVal": "2030-04-02", "quantidade": "1",
             "tipo_entrada": "aquisicao_propria"}
    assert estoque.avisos_do_cadastro(dados) == []
    ok, msg = estoque.cadastrar_manual(dict(dados), "talita.rafaela")
    assert ok, msg
    avisos = estoque.avisos_do_cadastro(dados)
    assert any("Já existem 1 unidade(s)" in a and "020426" in a for a in avisos)


def test_a_tela_mostra_o_aviso_depois_de_salvar(client, admin_headers):
    r = client.post("/api/almoxarifado/manual", data={
        "xProd": "CLIP USO CIRURGICO", "codigo_barras": "14026704725325", "codigo_aghu": "90698",
        "fornecedor": "F", "marca_fabricante": "M", "nLote": "73H2501032", "dVal": "2030-09-07",
        "quantidade": "2", "tipo_entrada": "aquisicao_propria"}, headers=admin_headers)
    assert r.status_code == 200
    assert "CAIXA" in r.text
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = '73H2501032'") == 2
