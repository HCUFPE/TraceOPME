# tests/test_v18_33_finalizar_valida_estado.py
"""v18.33: `finalizar()` tem de olhar o estado antes de concluir.

Achado pela Camila (18/11/2026): dava para cancelar a solicitação e, depois,
finalizá-la — a mesma solicitação ficava com `cancelada_em` E `finalizada_em`
preenchidos. Também dava para finalizar duas vezes, trocando a justificativa
já registrada.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso


def _com_pedido(prontuario, sala, descricao="COIL"):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, descricao, "sala1")[0]
    return ida


def _estado(ida):
    return db.consultar_um("""SELECT COALESCE(cancelada_em,'') c, COALESCE(finalizada_em,'') f,
                                     COALESCE(motivo_faltas,'') m
                              FROM solicitacoes WHERE id_atendimento = ?""", (ida,))


def test_cancelada_nao_pode_ser_finalizada(client):
    ida = _com_pedido("9970100", "105")
    assert solicitacoes.cancelar(ida, "sala1", "paciente não operou")[0]

    ok, msg = solicitacoes.finalizar(ida, "farm1", "sem estoque")
    assert not ok
    assert "cancelada" in msg.lower()
    e = _estado(ida)
    assert e["c"] and not e["f"], "não pode ficar cancelada e finalizada ao mesmo tempo"


def test_nao_finaliza_duas_vezes_nem_troca_o_motivo(client):
    ida = _com_pedido("9970200", "106")
    ok, msg = solicitacoes.finalizar(ida, "farm1", "sem estoque")
    assert ok, msg
    primeiro = _estado(ida)
    assert primeiro["m"] == "sem estoque"

    ok, msg = solicitacoes.finalizar(ida, "farm1", "motivo trocado")
    assert not ok and "já" in msg.lower()
    depois = _estado(ida)
    assert depois["f"] == primeiro["f"] and depois["m"] == "sem estoque"


def test_cancelar_depois_de_finalizar_continua_barrado(client):
    """O contrário já era barrado — fica testado para não regredir."""
    ida = _com_pedido("9970300", "107")
    assert solicitacoes.finalizar(ida, "farm1", "sem estoque")[0]
    ok, msg = solicitacoes.cancelar(ida, "sala1", "desistiu")
    assert not ok and "finaliz" in msg.lower()
    e = _estado(ida)
    assert e["f"] and not e["c"]


def test_reaberta_pela_sala_pode_ser_finalizada_de_novo(client):
    """Depois da reabertura (v18.32), a farmácia finaliza normalmente."""
    ida = _com_pedido("9970400", "108")
    assert solicitacoes.finalizar(ida, "farm1", "sem estoque")[0]
    assert solicitacoes.adicionar_avulso(ida, "92529", 1, "FIO NOVO", "sala1")[0]
    assert not _estado(ida)["f"]
    ok, msg = solicitacoes.finalizar(ida, "farm1", "chegou só parte")
    assert ok, msg
    assert _estado(ida)["m"] == "chegou só parte"


def test_sem_solicitacao_continua_sem_erro(client):
    """Atendimento sem pedido: finalizar não é erro (o fluxo chama assim)."""
    ok, ida = atendimentos.abrir({"prontuario": "9970500", "unidade": "BLOCO CIRURGICO", "sala": "109",
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert solicitacoes.finalizar(ida, "farm1")[0]
