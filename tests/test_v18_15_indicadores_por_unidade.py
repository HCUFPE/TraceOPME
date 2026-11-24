# tests/test_v18_15_indicadores_por_unidade.py
"""v18.15: indicadores separados por unidade (Bloco Cirúrgico x Hemodinâmica)."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque,
                                                         fluxo, indicadores as calc)
from src.providers.implementations.opme.utils import hoje_iso

ENF = {"username": "admin", "nome": "Administrador", "papel": "admin"}
BLOCO, HEMO = "BLOCO CIRURGICO", "HEMODINAMICA - PDT"


def _cad(cod, lote, farmacia):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {lote}", "codigo_barras": cod, "codigo_aghu": "9200",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
                                      "dVal": "2031-01-01", "quantidade": "1", "vUnCom": "100",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status=?, farmacia=?, vUnCom=100 WHERE nLote=?",
                (EM_ESTOQUE_FARMACIA, farmacia, lote))


def _usar(cod, unidade, prontuario, sala):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": unidade, "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    # a sala pode ter ficado aberta por outro teste da suíte: libera antes
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL WHERE unidade = ? AND sala = ? "
                "AND id_atendimento <> ?", (unidade, sala, ida))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    farmacia = BLOCO if unidade == BLOCO else HEMO
    assert fluxo.bipar(operacao="dispensar_sala", codigo=cod, usuario="admin",
                       id_atendimento=ida, farmacia=farmacia)["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=ENF)
    assert fluxo.bipar(operacao="registrar_uso", codigo=cod, usuario="admin", id_atendimento=ida)["ok"]
    return ida


def test_chave_unidade_e_opcoes(client):
    assert calc.chave_unidade("bloco cirurgico") == BLOCO
    assert calc.chave_unidade("HEMODINAMICA - PDT") == HEMO
    assert calc.chave_unidade("") == "" and calc.chave_unidade("UTI") == ""     # inválida = todas
    assert [u["chave"] for u in calc.unidades_disponiveis()] == [BLOCO, HEMO]
    assert calc.rotulo_do_filtro("") == "Bloco Cirúrgico e Hemodinâmica"
    assert calc.rotulo_do_filtro(HEMO) == "Hemodinâmica"


def test_consumo_separado_por_unidade(client):
    hoje_antes = hoje_iso()
    antes_b_consumo = calc.calcular_valores(hoje_antes, hoje_antes, BLOCO)["valor_consumido"]
    antes_h_consumo = calc.calcular_valores(hoje_antes, hoje_antes, HEMO)["valor_consumido"]
    _cad("7891115000014", "IND1", BLOCO)
    _cad("7891115000021", "IND2", BLOCO)
    _cad("7891115000038", "IND3", HEMO)
    _usar("7891115000014", BLOCO, "IND100", "41")
    _usar("7891115000021", BLOCO, "IND200", "42")
    _usar("7891115000038", HEMO, "IND300", "01")

    hoje = hoje_iso()
    tudo = calc.calcular_valores(hoje, hoje)
    bloco = calc.calcular_valores(hoje, hoje, BLOCO)
    hemo = calc.calcular_valores(hoje, hoje, HEMO)

    # o consumo de cada unidade entra só na dela (deltas sobre o que a suíte já tinha)
    assert bloco["valor_consumido"] - antes_b_consumo == 200
    assert hemo["valor_consumido"] - antes_h_consumo == 100
    assert bloco["valor_consumido"] + hemo["valor_consumido"] <= tudo["valor_consumido"]

    # estoque parado também separa: o que entra numa farmácia não soma na outra
    antes_b, antes_h = bloco["valor_estoque_total"], hemo["valor_estoque_total"]
    _cad("7891115000052", "IND5", BLOCO)
    _cad("7891115000069", "IND6", BLOCO)
    _cad("7891115000076", "IND7", HEMO)
    depois_b = calc.calcular_valores(hoje, hoje, BLOCO)["valor_estoque_total"]
    depois_h = calc.calcular_valores(hoje, hoje, HEMO)["valor_estoque_total"]
    assert depois_b - antes_b == 200 and depois_h - antes_h == 100


def test_montar_e_exportar_respeitam_a_unidade(client):
    _cad("7891115000045", "IND4", HEMO)
    _usar("7891115000045", HEMO, "IND400", "02")
    hoje = hoje_iso()
    por_codigo = {i["codigo"]: i for i in calc.montar(hoje, hoje, unidade=HEMO)}
    assert por_codigo["valor_consumido"]["valor"] >= 100
    linhas = calc.exportar(hoje, hoje, HEMO)
    assert linhas and all(l["local"] == "Hemodinâmica" for l in linhas)
    assert all(l["local"] == "Bloco Cirúrgico e Hemodinâmica" for l in calc.exportar(hoje, hoje))


def test_detalhamentos_aceitam_a_unidade(client):
    hoje = hoje_iso()
    for chamada in (
        lambda u: calc.tempos_por_etapa(hoje, hoje, u),
        lambda u: calc.gargalos_abertos(u),
        lambda u: calc.produtividade(hoje, hoje, u),
        lambda u: calc.cancelamentos(hoje, hoje, u),
        lambda u: calc.aproveitamento_por_especialidade(hoje, hoje, u),
        lambda u: calc.produtos_mais_devolvidos(hoje, hoje, unidade=u),
        lambda u: calc.vencimentos_por_faixa(u),
        lambda u: calc.baixas_por_motivo(hoje, hoje, u),
        lambda u: calc.consumo_por("especialidade", hoje, hoje, unidade=u),
        lambda u: calc.evolucao_mensal(12, u),
        lambda u: calc.cobertura_por_produto(hoje, hoje, unidade=u),
        lambda u: calc.divergencias_por_fornecedor(hoje, hoje, u),
        lambda u: calc.problemas_na_sala(hoje, hoje, u),
        lambda u: calc.completude_por_campo(u),
        lambda u: calc.itens_sem_conferencia_sala(hoje, hoje, u),
        lambda u: calc.pendentes_ciencia_farmacia(u),
        lambda u: calc.utilizacao_dispensado(hoje, hoje, u),
    ):
        for unidade in ("", BLOCO, HEMO):
            chamada(unidade)      # nenhuma pode quebrar com o filtro


def test_telas_abrem_com_a_unidade(client, admin_headers):
    for caminho in ("", "/fluxo", "/desperdicio", "/financeiro", "/qualidade"):
        for unidade in ("", BLOCO, HEMO):
            r = client.get(f"/api/indicadores{caminho}?unidade={unidade}", headers=admin_headers)
            assert r.status_code == 200, (caminho, unidade, r.text[:200])
            dados = r.json()["dados"]
            assert dados["unidade"] == unidade
            assert [u["chave"] for u in dados["unidades"]] == [BLOCO, HEMO]
    # CSV separado traz a unidade no nome do arquivo
    r = client.get(f"/api/indicadores/exportar?unidade={HEMO}", headers=admin_headers)
    assert r.status_code == 200 and "hemodinamica" in r.headers["content-disposition"]
