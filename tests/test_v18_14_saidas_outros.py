# tests/test_v18_14_saidas_outros.py
"""v18.14: dispensação de OPME para outros procedimentos (farmácia e almoxarifado)."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO,
                                                       SAIDA_OUTROS, operacoes_do_modulo)
from src.providers.implementations.opme.services import estoque, fluxo, saidas_outros
from src.providers.implementations.opme.utils import hoje_iso


def _cad(cod, lote, *, na_farmacia=False, qtd=1):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": "9100",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
                                      "dVal": "2031-01-01", "quantidade": str(qtd),
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    if na_farmacia:
        db.executar("UPDATE unidades SET status=?, farmacia='BLOCO CIRURGICO' WHERE nLote=?",
                    (EM_ESTOQUE_FARMACIA, lote))


def test_farmacia_dispensa_para_outro_procedimento(client):
    _cad("7891114000011", "OUT1", na_farmacia=True)
    r = fluxo.bipar(operacao="saida_outros", codigo="7891114000011", usuario="farm1",
                    farmacia="BLOCO CIRURGICO", motivo="Ambulatório — curativo complexo",
                    observacao="retirado por ENF. MARIA")
    assert r["ok"], r
    u = db.consultar_um("SELECT status, id_atendimento FROM unidades WHERE nLote = 'OUT1'")
    assert u["status"] == SAIDA_OUTROS and not u["id_atendimento"]
    # saiu do estoque: não aparece mais como disponível e não dá para bipar de novo
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote='OUT1' AND status=?",
                      (EM_ESTOQUE_FARMACIA,)) == 0
    r2 = fluxo.bipar(operacao="saida_outros", codigo="7891114000011", usuario="farm1",
                     farmacia="BLOCO CIRURGICO", motivo="de novo")
    assert not r2["ok"] and "saiu do estoque" in r2["mensagem"]


def test_motivo_destino_e_obrigatorio(client):
    _cad("7891114000028", "OUT2", na_farmacia=True)
    r = fluxo.bipar(operacao="saida_outros", codigo="7891114000028", usuario="farm1",
                    farmacia="BLOCO CIRURGICO", motivo="")
    assert not r["ok"] and "destino" in r["mensagem"].lower()
    assert db.escalar("SELECT status FROM unidades WHERE nLote='OUT2'") == EM_ESTOQUE_FARMACIA


def test_almoxarifado_dispensa_do_proprio_estoque(client):
    _cad("7891114000035", "OUT3")
    # a operação da farmácia não alcança o estoque do almoxarifado
    r = fluxo.bipar(operacao="saida_outros", codigo="7891114000035", usuario="farm1",
                    farmacia="BLOCO CIRURGICO", motivo="UTI")
    assert not r["ok"]
    r = fluxo.bipar(operacao="saida_outros_almox", codigo="7891114000035", usuario="almox1",
                    motivo="UTI", observacao="retirado por TEC. JOAO")
    assert r["ok"], r
    assert db.escalar("SELECT status FROM unidades WHERE nLote='OUT3'") == SAIDA_OUTROS


def test_lista_de_saidas_e_resumo(client):
    _cad("7891114000042", "OUT4", na_farmacia=True)
    _cad("7891114000059", "OUT5", na_farmacia=True)
    _cad("7891114000066", "OUT6")
    for cod, dest in (("7891114000042", "UTI"), ("7891114000059", "UTI")):
        assert fluxo.bipar(operacao="saida_outros", codigo=cod, usuario="farm1",
                           farmacia="BLOCO CIRURGICO", motivo=dest)["ok"]
    assert fluxo.bipar(operacao="saida_outros_almox", codigo="7891114000066", usuario="almox1",
                       motivo="Ensino e pesquisa")["ok"]

    hoje = hoje_iso()
    da_farmacia = saidas_outros.listar(hoje, hoje, destino="UTI", origem="farmacia")
    assert len(da_farmacia) == 2 and all(l["origem"] and not l["desfeita"] for l in da_farmacia)
    assert saidas_outros.resumo(da_farmacia) == [{"destino": "UTI", "itens": 2, "materiais": 1}]
    assert [l["nLote"] for l in da_farmacia] == ["OUT5", "OUT4"]      # mais recente primeiro

    do_almox = saidas_outros.listar(hoje, hoje, origem="almoxarifado", destino="Ensino")
    assert len(do_almox) == 1 and do_almox[0]["origem"] == "Almoxarifado"
    assert do_almox[0]["destino"] == "Ensino e pesquisa"
    # as duas origens juntas (a do almoxarifado entra na mesma lista) e nada fora do período
    assert len(saidas_outros.listar(hoje, hoje, destino="UTI")) >= 3
    assert saidas_outros.listar("2020-01-01", "2020-01-02") == []


def test_saida_desfeita_aparece_riscada(client):
    _cad("7891114000073", "OUT7", na_farmacia=True)
    assert fluxo.bipar(operacao="saida_outros", codigo="7891114000073", usuario="farm1",
                       farmacia="BLOCO CIRURGICO", motivo="Ambulatório")["ok"]
    db.executar("UPDATE unidades SET status = ? WHERE nLote = 'OUT7'", (EM_ESTOQUE_RECEBIMENTO,))
    linha = next(l for l in saidas_outros.listar(hoje_iso(), hoje_iso()) if l["nLote"] == "OUT7")
    assert linha["desfeita"] is True
    assert saidas_outros.resumo([linha]) == []


def test_desfazer_devolve_ao_estoque_de_origem(client):
    _cad("7891114000080", "OUT8", na_farmacia=True)
    _cad("7891114000097", "OUT9")
    assert fluxo.bipar(operacao="saida_outros", codigo="7891114000080", usuario="farm1",
                       farmacia="BLOCO CIRURGICO", motivo="Ambulatório")["ok"]
    assert fluxo.bipar(operacao="saida_outros_almox", codigo="7891114000097", usuario="almox1",
                       motivo="UTI")["ok"]
    da_farmacia = db.escalar("SELECT id_unidade FROM unidades WHERE nLote = 'OUT8'")
    do_almox = db.escalar("SELECT id_unidade FROM unidades WHERE nLote = 'OUT9'")

    assert saidas_outros.desfazer(da_farmacia, "farm1", "x")[0] is False       # motivo curto
    ok, msg = saidas_outros.desfazer(da_farmacia, "farm1", "bipado por engano")
    assert ok and "farmácia" in msg
    assert db.escalar("SELECT status FROM unidades WHERE nLote='OUT8'") == EM_ESTOQUE_FARMACIA
    ok, msg = saidas_outros.desfazer(do_almox, "almox1", "bipado por engano")
    assert ok and "almoxarifado" in msg
    assert db.escalar("SELECT status FROM unidades WHERE nLote='OUT9'") == EM_ESTOQUE_RECEBIMENTO
    # desfazer duas vezes não faz nada
    assert saidas_outros.desfazer(do_almox, "almox1", "de novo")[0] is False
    # e o item volta a poder ser dispensado normalmente
    assert fluxo.bipar(operacao="saida_outros_almox", codigo="7891114000097", usuario="almox1",
                       motivo="UTI")["ok"]


def test_operacoes_aparecem_nos_dois_modulos(client):
    assert "saida_outros" in [o.codigo for o in operacoes_do_modulo("farmacia")]
    assert "saida_outros_almox" in [o.codigo for o in operacoes_do_modulo("almoxarifado")]
    # nenhuma delas exige atendimento/paciente
    for codigo in saidas_outros.OPERACOES:
        op = next(o for o in operacoes_do_modulo("farmacia") + operacoes_do_modulo("almoxarifado")
                  if o.codigo == codigo)
        assert not op.exige_atendimento and not op.define_atendimento


def test_telas_respondem(client, admin_headers):
    for base in ("/farmacia", "/almoxarifado"):
        r = client.get(f"/api{base}/saidas-outros", headers=admin_headers)
        assert r.status_code == 200, (base, r.text[:200])
        assert r.json()["tela"] == "comum/saidas_outros.html"
    for operacao in saidas_outros.OPERACOES:
        r = client.get(f"/api/bipagem/{operacao}", headers=admin_headers)
        assert r.status_code == 200, (operacao, r.text[:200])
        dados = r.json()["dados"]
        assert dados["exige_motivo"] and dados["destinos_outros"]
