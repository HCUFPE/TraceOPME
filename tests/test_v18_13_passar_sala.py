# tests/test_v18_13_passar_sala.py
"""v18.13: passar a sala para quem entrou na frente e sala que segue bipando até a farmácia concluir."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import (atendimentos, devolucoes, dispensacoes,
                                                         estoque, fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

ENF = {"username": "admin", "nome": "Administrador", "papel": "admin"}


def _cad(cod, lote, qtd=1):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": "8001",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
                                      "dVal": "2031-01-01", "quantidade": str(qtd),
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE nLote=?", (lote,))


def _atendimento(prontuario, sala, abrir_sala=True):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    if abrir_sala:
        assert atendimentos.abrir_sala(ida, "admin")[0]
    return ida


def _dispensar_e_confirmar(ida, codigo):
    r = fluxo.bipar(operacao="dispensar_sala", codigo=codigo, usuario="admin", id_atendimento=ida,
                    farmacia="BLOCO CIRURGICO")
    assert r["ok"], r
    d = dispensacoes.pendente_do_atendimento(ida)
    dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=ENF)


def test_passar_sala_nao_move_material(client):
    """Entrou Ana na frente de João: a sala vai para Ana, o material de João fica com João."""
    _cad("7891113000018", "TRC1")
    _cad("7891113000025", "TRC2")
    joao, ana = _atendimento("TRC100", "41"), _atendimento("TRC200", "41", abrir_sala=False)
    _dispensar_e_confirmar(joao, "7891113000018")
    _dispensar_e_confirmar(ana, "7891113000025")
    assert any(c["id_atendimento"] == ana for c in atendimentos.candidatos_troca(joao))

    ok, msg = atendimentos.passar_sala(joao, ana, "admin", "medico antecipou este paciente")
    assert ok, msg
    # cada um com o seu material, no mesmo lugar
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_atendimento = ?", (joao,)) == 1
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_atendimento = ?", (ana,)) == 1
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_atendimento = ? AND status = 'em_sala'", (joao,)) == 1
    # a vez na sala é de Ana
    assert atendimentos.buscar(ana)["sala_aberta_em"] and not atendimentos.buscar(joao)["sala_aberta_em"]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891113000025", usuario="admin", id_atendimento=ana)["ok"]
    # João não bipa uso enquanto não voltar para a sala
    r = fluxo.bipar(operacao="registrar_uso", codigo="7891113000018", usuario="admin", id_atendimento=joao)
    assert not r["ok"] and r.get("sala_fechada")
    # e a ciência de material de João não "rouba" a sala de Ana
    _cad("7891113000063", "TRC4")
    _dispensar_e_confirmar(joao, "7891113000063")
    assert not atendimentos.buscar(joao)["sala_aberta_em"]
    assert atendimentos.buscar(ana)["sala_aberta_em"]
    # João entra depois: a sala volta para ele pelo mesmo caminho
    # a ficha de João mostra quem está na sala (bloco "Assumir a sala")
    na_sala = atendimentos.quem_esta_na_sala(joao)
    assert na_sala and na_sala["id_atendimento"] == ana
    assert atendimentos.quem_esta_na_sala(ana) is None
    ok, msg = atendimentos.passar_sala(ana, joao, "admin", "ana saiu, joao entrou")
    assert ok, msg
    assert atendimentos.buscar(joao)["sala_aberta_em"] and not atendimentos.buscar(ana)["sala_aberta_em"]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891113000018", usuario="admin", id_atendimento=joao)["ok"]
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE id_atendimento = ? AND tipo = 'sala_assumida'", (joao,)) == 1


def test_passar_sala_recusa_errado(client):
    _cad("7891113000032", "TRC3")
    a1, a2 = _atendimento("TRC300", "42"), _atendimento("TRC400", "42", abrir_sala=False)
    _dispensar_e_confirmar(a1, "7891113000032")
    assert atendimentos.passar_sala(a1, a1, "admin", "motivo bom")[0] is False
    assert atendimentos.passar_sala(a1, a2, "admin", "x")[0] is False          # motivo curto
    ok, msg = atendimentos.passar_sala(a2, a1, "admin", "sala nao esta comigo")
    assert not ok and "não está aberta" in msg
    # abrir a sala de quem entrou na frente avisa como passar a vez
    ok, msg = atendimentos.abrir_sala(a2, "admin")
    assert not ok and "Entrou outro" in msg


def test_sala_segue_bipando_ate_a_farmacia_concluir(client):
    _cad("7891113000049", "SEG1", 2)
    ida = _atendimento("SEG100", "43")
    _dispensar_e_confirmar(ida, "7891113000049")
    _dispensar_e_confirmar(ida, "7891113000049")
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891113000049", usuario="admin", id_atendimento=ida)["ok"]

    ok, msg, encerrou = fechamento.finalizar_uso(ida, ENF)
    assert ok and not encerrou, msg
    # v18.13: continua bipando (antes dava "já foram finalizados")
    _cad("7891113000056", "SEG2")
    _dispensar_e_confirmar(ida, "7891113000056")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7891113000056", usuario="admin", id_atendimento=ida)
    assert r["ok"], r
    assert fluxo.resumo_uso(ida)["pode_excluir"] is True

    dev = devolucoes.pendente_do_atendimento(ida)
    devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=ENF)
    assert atendimentos.buscar(ida)["status"] != "aberto"      # a farmácia concluiu → sala fechada
    r = fluxo.bipar(operacao="registrar_uso", codigo="7891113000049", usuario="admin", id_atendimento=ida)
    assert not r["ok"] and "encerrado" in r["mensagem"], r
