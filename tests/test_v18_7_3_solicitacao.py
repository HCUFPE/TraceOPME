# tests/test_v18_7_3_solicitacao.py
"""v18.7.3: a sala cancela a solicitação de OPME; o alerta de pedidos em aberto só aparece na farmácia."""
from unittest.mock import patch

from src.helpers.web_helper import render
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso


def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


def _com_solicitacao():
    ok, a = _abrir_at({"prontuario": "773301", "unidade": "BLOCO CIRURGICO", "sala": "05", "especialidade": "X",
                                "data_procedimento": hoje_iso()}, "admin")
    assert ok
    ok, msg = solicitacoes.adicionar_avulso(a, "401557", 2, "CATETER TESTE", "enf.ana")
    assert ok, msg
    return a


def test_sala_cancela_a_solicitacao(client, admin_headers):
    a = _com_solicitacao()
    assert any(x["id_atendimento"] == a for x in solicitacoes.em_aberto("BLOCO CIRURGICO"))
    assert solicitacoes.situacao(a)["pode_cancelar"]
    assert not solicitacoes.cancelar(a, "enf.ana", "")[0]          # motivo obrigatório
    r = client.post(f"/api/sala-procedimento/atendimento/{a}/solicitacao/cancelar", headers=admin_headers,
                    data={"motivo": "Procedimento mudou"})
    assert r.status_code == 200
    s = solicitacoes.situacao(a)
    assert s["cancelada_em"] and s["motivo_cancelamento"] == "Procedimento mudou" and not s["pode_cancelar"]
    assert not any(x["id_atendimento"] == a for x in solicitacoes.em_aberto("BLOCO CIRURGICO"))
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='solicitacao_cancelada' AND id_atendimento=?", (a,)) == 1
    assert not solicitacoes.cancelar(a, "enf.ana", "de novo")[0]    # já cancelada
    # a sala volta a pedir: a solicitação reabre e a farmácia vê de novo
    assert solicitacoes.adicionar_avulso(a, "24870", 1, "INTRODUTOR", "enf.ana")[0]
    s2 = solicitacoes.situacao(a)
    assert not s2["cancelada_em"]
    # v18.8.2: só o item novo — o cancelado não volta
    assert [l["descricao"] for l in s2["linhas"]] == ["INTRODUTOR"], s2["linhas"]
    assert "CATETER TESTE" in db.escalar("SELECT observacao FROM eventos WHERE tipo='solicitacao_cancelada' AND id_atendimento=?", (a,))
    assert any(x["id_atendimento"] == a for x in solicitacoes.em_aberto("BLOCO CIRURGICO"))


def test_alerta_de_pedidos_so_nas_telas_da_farmacia():
    class R:
        usuario = {"username": "f", "papel": "farmacia"}
        session = {"unidade_farmacia": "BLOCO CIRURGICO"}
    with patch("src.providers.implementations.opme.services.solicitacoes.contar_em_aberto", return_value=2):
        for tela in ("sala_procedimento/atendimentos.html", "sala_procedimento/hub.html", "procedimentos/lista.html",
                     "consultas/prontuario.html", "monitoramento/central.html", "qg/painel.html", "painel.html"):
            assert "pedidos_opme_abertos" not in render(R(), tela, {}).dados, tela
        for tela in ("farmacia/hub.html", "farmacia/solicitacoes.html", "dispensacoes/confirmar.html"):
            assert render(R(), tela, {}).dados["pedidos_opme_abertos"] == 2, tela
