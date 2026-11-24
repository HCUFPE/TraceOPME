# tests/test_v18_28_folha_de_separacao.py
"""v18.28: a farmácia imprime o pedido para separar o material.

Pedido da Camila (18/11/2026): "pode dar a opção de imprimir o pedido caso a
farmácia queira imprimir para melhor separar o material?". A folha traz o
cabeçalho do procedimento, a lista pedida com quantidade e quanto já foi
dispensado, a observação da sala e espaço para anotar lote/validade.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso

TELA = "farmacia/solicitacao_imprimir.html"


def _atendimento(prontuario="9930100", sala="81"):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso(),
                                  "hora_inicio": "07:30"}, "admin")
    assert ok, ida
    return ida


def _pedido(ida, itens, observacao=""):
    for it in itens:
        ok, msg = solicitacoes.adicionar_avulso(ida, it["codigos"], it["quantidade"],
                                                it["descricao"], "kleciane.moraes")
        assert ok, msg
    if observacao:
        from src.providers.implementations.opme import db as _db
        _db.executar("UPDATE solicitacoes SET observacao = ? WHERE id_atendimento = ?",
                     (observacao, ida))


def test_a_folha_traz_o_cabecalho_e_a_lista(client, admin_headers):
    ida = _atendimento()
    _pedido(ida, [{"codigos": "87994", "descricao": "COIL EMBOLIZANTE TAM. 10mm", "quantidade": 4},
                  {"codigos": "92529", "descricao": "FIO GUIA HIDROFILICO 0,35", "quantidade": 2}],
            observacao="Separar antes das 7h.")
    r = client.get(f"/api/farmacia/atendimento/{ida}/solicitacao/imprimir", headers=admin_headers)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["tela"] == TELA
    d = corpo["dados"]
    assert d["atendimento"]["prontuario"] == "9930100"
    assert d["atendimento"]["sala"] == "81"
    assert d["impresso_em"]
    linhas = d["sol"]["linhas"]
    assert [l["codigos"] for l in linhas] == ["87994", "92529"]
    assert [l["quantidade"] for l in linhas] == [4, 2]
    assert all(l["dispensado"] == 0 for l in linhas)
    assert d["sol"]["observacao"] == "Separar antes das 7h."
    assert d["sol"]["qtd_faltando"] == 2 and d["sol"]["qtd_linhas"] == 2


def test_a_folha_mostra_o_que_ja_foi_dispensado(client, admin_headers):
    ida = _atendimento("9930200", "82")
    _pedido(ida, [{"codigos": "87994", "descricao": "COIL EMBOLIZANTE TAM. 10mm", "quantidade": 2}])
    ok, m = estoque.cadastrar_manual({"xProd": "COIL EMBOLIZANTE TAM. 10mm",
                                      "codigo_barras": "7891180000011", "codigo_aghu": "87994",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": "FS1",
                                      "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = 'FS1'",
                (EM_ESTOQUE_FARMACIA,))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    assert fluxo.bipar(operacao="dispensar_sala", codigo="7891180000011", usuario="farm1",
                       id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]

    d = client.get(f"/api/farmacia/atendimento/{ida}/solicitacao/imprimir",
                   headers=admin_headers).json()["dados"]
    linha = d["sol"]["linhas"][0]
    assert linha["quantidade"] == 2 and linha["dispensado"] == 1
    assert linha["status"] == "parcial"


def test_procedimento_sem_pedido_abre_a_folha_vazia(client, admin_headers):
    ida = _atendimento("9930300", "83")
    r = client.get(f"/api/farmacia/atendimento/{ida}/solicitacao/imprimir", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert d["sol"]["linhas"] == [] and d["sol"]["existe"] is False
    assert d["atendimento"]["prontuario"] == "9930300"


def test_a_tela_esta_registrada_no_frontend():
    telas = open("frontend/src/views/opme/telas.ts", encoding="utf-8").read()
    assert f"'{TELA}'" in telas and "FarmaciaSolicitacaoImprimir.vue" in telas
    lista = open("frontend/src/views/opme/FarmaciaSolicitacoes.vue", encoding="utf-8").read()
    assert "solicitacao/imprimir" in lista          # botão na listagem
    painel = open("frontend/src/components/opme/SolicitacaoPainel.vue", encoding="utf-8").read()
    assert "solicitacao/imprimir" in painel         # e na tela de atender
