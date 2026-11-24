# tests/test_v18_31_pendente_ignora_canceladas.py
"""v18.31: solicitação cancelada (ou finalizada) não é pedido pendente.

Achado pela Camila (18/11/2026): pedir uma unidade, cancelar a solicitação com
motivo e consultar o resumo — `faltando` continuava 1, então o procedimento
seguia aparecendo no filtro "só com pedido pendente" da 18.30, mesmo com a
farmácia não tendo mais nada a atender.

O histórico da solicitação é preservado: o resumo continua trazendo as linhas e
o que foi atendido, agora dizendo também que está cancelada ou finalizada.
"""
from src.providers.implementations.opme.services import atendimentos, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso


def _atendimento(prontuario, sala):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


def _pendentes(client, headers):
    r = client.get("/api/sala-procedimento/atendimentos",
                   params={"data": hoje_iso(), "unidade": "BLOCO CIRURGICO", "mostrar": "pendente"},
                   headers=headers)
    assert r.status_code == 200
    return {a["id_atendimento"] for a in r.json()["dados"]["atendimentos"]}


def test_cancelada_sai_do_filtro_mas_fica_no_historico(client, admin_headers):
    ida = _atendimento("9950100", "97")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL CANCELADO", "sala1")[0]
    assert ida in _pendentes(client, admin_headers)

    ok, msg = solicitacoes.cancelar(ida, "sala1", "paciente não operou")
    assert ok, msg

    resumo = solicitacoes.resumo_lista([ida])[ida]
    assert resumo["cancelada"] is True
    assert resumo["pendente"] is False
    assert resumo["linhas"] == 1 and resumo["faltando"] == 1     # histórico preservado
    assert ida not in _pendentes(client, admin_headers)


def test_finalizada_tambem_sai_do_filtro(client, admin_headers):
    ida = _atendimento("9950200", "98")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL FINALIZADO", "sala1")[0]
    ok, msg = solicitacoes.finalizar(ida, "farm1", "fornecedor não entregou")
    assert ok, msg

    resumo = solicitacoes.resumo_lista([ida])[ida]
    assert resumo["finalizada"] is True and resumo["pendente"] is False
    assert ida not in _pendentes(client, admin_headers)


def test_pedido_vivo_continua_pendente(client, admin_headers):
    ida = _atendimento("9950300", "99")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL VIVO", "sala1")[0]
    resumo = solicitacoes.resumo_lista([ida])[ida]
    assert resumo["pendente"] is True and not resumo["cancelada"] and not resumo["finalizada"]
    assert ida in _pendentes(client, admin_headers)


def test_se_a_sala_pedir_de_novo_volta_a_pendente(client, admin_headers):
    """Cancelar e pedir outra vez reabre a solicitação — e ela volta ao filtro."""
    ida = _atendimento("9950400", "100")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL IDA E VOLTA", "sala1")[0]
    assert solicitacoes.cancelar(ida, "sala1", "trocou o procedimento")[0]
    assert ida not in _pendentes(client, admin_headers)

    assert solicitacoes.adicionar_avulso(ida, "87994", 2, "COIL NOVO PEDIDO", "sala1")[0]
    resumo = solicitacoes.resumo_lista([ida])[ida]
    assert resumo["cancelada"] is False and resumo["pendente"] is True
    assert ida in _pendentes(client, admin_headers)


def test_as_telas_mostram_cancelada_sem_cor_de_pendencia(client):
    for arq, marca in (("frontend/src/views/opme/SalaAtendimentos.vue", "pedido cancelado"),
                       ("frontend/src/views/opme/Procedimentos.vue", "cancelada"),
                       ("frontend/src/views/opme/FarmaciaAtendimentos.vue", "pedido cancelado")):
        tela = open(arq, encoding="utf-8").read()
        assert "cancelada" in tela and marca in tela, arq
