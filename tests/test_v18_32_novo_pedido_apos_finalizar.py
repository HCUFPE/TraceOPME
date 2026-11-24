# tests/test_v18_32_novo_pedido_apos_finalizar.py
"""v18.32: pedido novo depois de a farmácia finalizar a dispensa.

Achado pela Camila (18/11/2026): a farmácia finaliza a solicitação com "sem
estoque"; com o atendimento ainda aberto, a sala pede outro material. O pedido
era aceito, mas `em_aberto()` descarta solicitação com `finalizada_em` — então
o atendimento não voltava para a fila da farmácia. A sala achava que tinha
pedido; a farmácia não via nada.

Pedir de novo reabre a solicitação: a finalização anterior é desfeita e fica no
histórico (evento), como já acontecia com o cancelamento.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso

UNIDADE = "BLOCO CIRURGICO"


def _atendimento(prontuario, sala):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": UNIDADE, "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


def _na_fila(ida):
    return ida in {p["id_atendimento"] for p in solicitacoes.em_aberto(UNIDADE)}


def test_pedido_novo_depois_de_finalizar_volta_para_a_fila(client):
    ida = _atendimento("9960100", "101")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL PRIMEIRO", "sala1")[0]
    assert _na_fila(ida)

    ok, msg = solicitacoes.finalizar(ida, "farm1", "sem estoque")
    assert ok, msg
    assert not _na_fila(ida)                      # certo: nada a atender

    # a sala pede outro material, com o atendimento ainda aberto
    ok, msg = solicitacoes.adicionar_avulso(ida, "92529", 2, "FIO GUIA SEGUNDO", "sala1")
    assert ok, msg
    assert _na_fila(ida), "o pedido novo tem de voltar para a fila da farmácia"

    resumo = solicitacoes.resumo_lista([ida])[ida]
    assert resumo["finalizada"] is False and resumo["pendente"] is True


def test_os_itens_do_pedido_anterior_nao_somem(client):
    """Finalizar não apaga o que já foi pedido: o novo item entra junto."""
    ida = _atendimento("9960200", "102")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL ANTES", "sala1")[0]
    assert solicitacoes.finalizar(ida, "farm1", "sem estoque")[0]
    assert solicitacoes.adicionar_avulso(ida, "92529", 1, "FIO DEPOIS", "sala1")[0]

    descricoes = [l["descricao"] for l in solicitacoes.situacao(ida)["linhas"]]
    assert "COIL ANTES" in descricoes and "FIO DEPOIS" in descricoes


def test_a_reabertura_fica_no_historico(client):
    ida = _atendimento("9960300", "103")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL HIST", "sala1")[0]
    assert solicitacoes.finalizar(ida, "farm1", "sem estoque")[0]
    assert solicitacoes.adicionar_avulso(ida, "92529", 1, "FIO HIST", "sala1")[0]

    eventos = db.consultar("SELECT tipo, observacao FROM eventos WHERE id_atendimento = ? ORDER BY id_evento",
                           (ida,))
    assert any(e["tipo"] == "solicitacao_reaberta" for e in eventos), [e["tipo"] for e in eventos]


def test_sem_pedido_novo_a_finalizacao_continua_valendo(client):
    ida = _atendimento("9960400", "104")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL FIM", "sala1")[0]
    assert solicitacoes.finalizar(ida, "farm1", "sem estoque")[0]
    assert not _na_fila(ida)
    assert solicitacoes.resumo_lista([ida])[ida]["finalizada"] is True
