# tests/test_v18_24_lote_longo_na_etiqueta.py
"""v18.24: lote + validade colados passando de 20 caracteres.

Caso real (HC-UFPE, 18/11/2026): a etiqueta
`01 06949450404315` + `10 SP11250314005` + `17 280316` chega do leitor sem
separador como `010694945040431510SP1125031400517280316`. O trecho depois do
AI 10 tem 21 caracteres; o leitor do sistema cortava em 20 (tamanho máximo do
AI 10), perdia o último dígito e a segunda leitura do lote não fechava. Sem
lote, a busca caía no GTIN e pegava unidades de qualquer lote — inclusive já
utilizadas, daí o "JÁ REGISTRADO" numa farmácia que tinha o material.
"""
from src.providers.implementations.opme import db, gs1
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, UTILIZADO
from src.providers.implementations.opme.services import estoque, fluxo

GTIN = "06949450404315"
ETIQUETA = "010694945040431510SP1125031400517280316"
HEMO = "HEMODINAMICA - PDT"


def _cad(lote, validade, quantidade):
    ok, m = estoque.cadastrar_manual({
        "xProd": "CATETER GUIA", "codigo_barras": GTIN, "codigo_aghu": "92530",
        "fornecedor": "APT MEDICAL", "marca_fabricante": "APT", "nLote": lote,
        "dVal": validade, "quantidade": str(quantidade), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


def test_o_lote_de_21_caracteres_e_lido_inteiro(client):
    lido = gs1.interpretar(ETIQUETA)
    assert lido["gtin"] == GTIN
    assert lido["lote"] == "SP1125031400517280316"      # leitura crua, sem corte
    assert lido["lote_curto"] == "SP11250314005"        # o lote de verdade
    assert lido["validade_do_lote"] == "2028-03-16"


def test_a_etiqueta_acha_a_unidade_certa_e_nao_as_de_outro_lote(client):
    _cad("SP11250314005", "2028-03-16", 2)       # o lote da etiqueta
    _cad("SP11250100001", "2028-01-10", 3)       # outro lote do mesmo produto
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote IN "
                "('SP11250314005','SP11250100001')", (EM_ESTOQUE_FARMACIA, HEMO))
    linhas = estoque.buscar_unidades(ETIQUETA, "ativos")
    assert len(linhas) == 2 and {l["nLote"] for l in linhas} == {"SP11250314005"}


def test_unidade_ja_utilizada_de_outro_lote_nao_bloqueia_o_bip(client):
    """Era a causa do "JÁ REGISTRADO": o GTIN trazia a unidade usada de outro lote."""
    _cad("SP11250314777", "2028-03-16", 1)       # lote da etiqueta (outra remessa)
    _cad("SP11250999999", "2028-02-02", 1)       # outro lote, este já utilizado
    db.executar("UPDATE unidades SET status = ? WHERE nLote = 'SP11250999999'", (UTILIZADO,))
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote = 'SP11250314777'",
                (EM_ESTOQUE_FARMACIA, HEMO))
    etiqueta = "010694945040431510SP1125031477717280316"
    linhas = estoque.buscar_unidades(etiqueta, "ativos")
    assert {l["nLote"] for l in linhas} == {"SP11250314777"}


def test_a_recusa_do_bip_diz_qual_lote_foi_utilizado(client):
    _cad("SP11250888888", "2028-03-16", 1)
    db.executar("UPDATE unidades SET status = ? WHERE nLote = 'SP11250888888'", (UTILIZADO,))
    from src.providers.implementations.opme.services import atendimentos
    from src.providers.implementations.opme.utils import hoje_iso
    ok, ida = atendimentos.abrir({"prontuario": "9925100", "unidade": HEMO, "sala": "02",
                                  "especialidade": "RADIOLOGIA INTERVENCIONISTA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    r = fluxo.bipar(operacao="dispensar_sala", codigo="010694945040431510SP1125088888817280316", usuario="farm1",
                    id_atendimento=ida, farmacia=HEMO)
    assert not r["ok"]
    assert "SP11250888888" in r["mensagem"] and "1 unidade(s)" in r["mensagem"]


def test_etiquetas_ja_cobertas_continuam_iguais(client):
    """Regressão das leituras que já funcionavam (v18.17)."""
    curto = gs1.interpretar("010694945040369310SP112408203617270904")
    assert curto["lote_curto"] == "SP1124082036" and curto["validade_do_lote"] == "2027-09-04"
    inteiro = gs1.interpretar("17280811109686013291005")
    assert inteiro["lote"] == "9686013291005" and inteiro["validade"] == "2028-08-11"
