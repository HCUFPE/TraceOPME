# tests/test_v18_43_2_o_bipado_inteiro_e_o_codigo.py
"""v18.43.2: o texto bipado inteiro é o código — não só o produto dentro dele.

Camila (20/11/2026, 21:39): "porque esse item tem uma quantidade no
almoxarifado e na hora de dispensar aparece várias opções? ele está se
baseando apenas no 7898716350358. não deveria ser assim. o que eu bipei deve
ser procurado. (...) código de barras é tudo o que eu bipo."

Ela tem 5 próteses do AGHU 92766, cada uma cadastrada com a SUA etiqueta
(lote e número de série próprios). Ao bipar a etiqueta de uma, a tela do envio
abria as 5 para escolher — porque a 18.43.1 passou a achar o material pelo
produto de dentro da etiqueta, mas não restringia às unidades que têm
exatamente aquele código.

Regra agora, em todos os caminhos de bipagem (envio, dispensação, devolução,
caixa de consignado): se alguma unidade tem EXATAMENTE o texto bipado como
código de barras, a busca é essa — e só essa.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo, remessas
from src.providers.implementations.opme.utils import hoje_iso

FARM = "HEMODINAMICA - PDT"
# cada cenário usa o seu GTIN: etiqueta repetida em materiais diferentes é
# outra história (aí escolher é o certo), e não é o que se testa aqui.
GTINS = {"92799": "07898716352758", "92798": "07898716352765",
         "92797": "07898716352772", "92796": "07898716352789"}
# (lote, validade, série) — como no almoxarifado dela: 5 lotes, 1 unidade cada
PECAS = [("061025", "2029-10-06", "561100"), ("260126", "2030-01-26", "561193"),
         ("190226", "2030-02-19", "561250"), ("020326", "2030-03-02", "561300"),
         ("010626", "2030-06-01", "561400")]


def _etiqueta(aghu, lote, serie):
    # a série carrega o AGHU: peças de materiais diferentes não repetem série
    return f"(01){GTINS[aghu][1:]}(17)300126(10){lote}(21){aghu}{serie}(11)260126"


def _cadastrar_as_cinco(aghu="92799"):
    for lote, dval, serie in PECAS:
        ok, m = estoque.cadastrar_manual({
            "xProd": "PROTESE VALVAR CARDIACA, BIOLOGICA, AORTICA, TAM. 27",
            "codigo_barras": GTINS[aghu], "codigo_aghu": aghu, "fornecedor": "BRAILE",
            "marca_fabricante": "BRAILE", "nLote": lote, "dVal": dval, "quantidade": "1",
            "tipo_entrada": "aquisicao_propria"}, "almox")
        assert ok, m
        # o cadastro real guardou a etiqueta inteira no campo do código
        db.executar("UPDATE unidades SET codigo_barras = ?, numero_serie = ? "
                    "WHERE codigo_aghu = ? AND nLote = ?",
                    (_etiqueta(aghu, lote, serie), f"{aghu}{serie}", aghu, lote))
    return aghu


def test_envio_pega_a_peca_bipada_e_nao_abre_os_cinco_lotes(client):
    aghu = _cadastrar_as_cinco("92799")
    ok, id_rem = remessas.abrir(FARM, "almox")
    assert ok, id_rem
    r = remessas.bipar(id_rem, _etiqueta(aghu, "260126", "561193"), "almox", ciencia_validade=True)
    assert r["ok"], r.get("mensagem") or r.get("titulo")
    assert not r.get("escolher"), "não pode mais abrir a lista de lotes"
    assert "260126" in r["mensagem"], r["mensagem"]
    # e foi a peça certa que saiu do almoxarifado
    status = {l["nLote"]: l["status"] for l in db.consultar(
        "SELECT nLote, status FROM unidades WHERE codigo_aghu = ?", (aghu,))}
    assert status["260126"] != "em_estoque_recebimento"
    assert all(status[l] == "em_estoque_recebimento" for l, _v, _s in PECAS if l != "260126")


def test_cada_etiqueta_pega_a_sua_peca(client):
    aghu = _cadastrar_as_cinco("92798")
    for lote, _dval, serie in PECAS:
        ok, id_rem = remessas.abrir(FARM, f"almox{lote}")
        assert ok, id_rem
        r = remessas.bipar(id_rem, _etiqueta(aghu, lote, serie), f"almox{lote}", ciencia_validade=True)
        assert r["ok"] and not r.get("escolher"), r.get("mensagem")
        assert lote in r["mensagem"], f"bipou {lote} e veio: {r['mensagem']}"


def test_dispensar_para_a_sala_tambem(client):
    aghu = _cadastrar_as_cinco("92797")
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE codigo_aghu = ?",
                (EM_ESTOQUE_FARMACIA, FARM, aghu))
    ok, ida = atendimentos.abrir({"prontuario": "92797001", "paciente": "PACIENTE TESTE",
                                  "unidade": "HEMODINAMICA - PDT", "sala": "01",
                                  "especialidade": "HEMODINAMICA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    r = fluxo.bipar(operacao="dispensar_sala", codigo=_etiqueta(aghu, "190226", "561250"),
                    usuario="farm1", id_atendimento=ida, farmacia=FARM, ciencia_validade=True)
    assert r["ok"], r.get("mensagem")
    usada = db.consultar_um("SELECT nLote FROM unidades WHERE id_atendimento = ?", (ida,))
    assert usada and usada["nLote"] == "190226", "tem de ser a peça bipada"


def test_bipar_so_o_produto_continua_abrindo_os_lotes(client):
    """Quem bipa só o código do produto (sem etiqueta) continua escolhendo —
    aí o sistema realmente não sabe qual peça é."""
    aghu = _cadastrar_as_cinco("92796")
    ok, id_rem = remessas.abrir(FARM, "almoxP")
    assert ok, id_rem
    r = remessas.bipar(id_rem, GTINS[aghu], "almoxP")
    assert not r["ok"] and r.get("escolher"), "sem a etiqueta, escolher é o certo"
    assert len(r["opcoes"]) >= 5
