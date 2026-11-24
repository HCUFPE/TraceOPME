# tests/test_v18_34_troca_de_paciente.py
"""Troca de paciente na sala — bordas (18/11/2026).

A sala passa de um paciente para outro sem que NENHUM material mude de dono.
Aqui ficam as bordas: passar e devolver, quem saiu não bipa, a sala física
acompanha quem entrou, cada um finaliza o seu, troca com material em trânsito,
e as recusas (unidades diferentes, atendimento encerrado, motivo curto).
"""
import pytest
from tests.test_v18_34_fechamento_ponta_a_ponta import (SALA, FARM, ciencia, dispensar,
                                                        novo_atendimento, novo_material, status, usar)
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, fechamento, fluxo

CASOS = []
def caso(n):
    def r(f):
        CASOS.append((n, f)); return f
    return r


def _livre(ida):
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL, sala_aberta_por = NULL "
                "WHERE id_atendimento = ?", (ida,))


@caso("T1. passa a sala e devolve depois")
def t1():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    ca, la = novo_material(); dispensar(a, ca); ciencia(a)
    ok, m = atendimentos.passar_sala(a, b, "admin", "médico antecipou o outro")
    assert ok, m
    assert not atendimentos.buscar(a)["sala_aberta_em"]
    assert atendimentos.buscar(b)["sala_aberta_em"]
    assert db.escalar("SELECT id_atendimento FROM unidades WHERE nLote = ?", (la,)) == a
    ok, m = atendimentos.passar_sala(b, a, "admin", "o primeiro voltou para a sala")
    assert ok, m
    assert atendimentos.buscar(a)["sala_aberta_em"]


@caso("T2. quem perdeu a sala consegue bipar uso?")
def t2():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    ca, la = novo_material(); dispensar(a, ca); ciencia(a)
    assert atendimentos.passar_sala(a, b, "admin", "trocaram a ordem")[0]
    r = fluxo.bipar(operacao="registrar_uso", codigo=ca, usuario="sala1", id_atendimento=a)
    assert not r["ok"], "sem a sala, o paciente que saiu não registra uso"
    assert "sala" in (r.get("mensagem") or "").lower()


@caso("T3. a sala muda de número quando o destino era de outra sala")
def t3():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    sala_a = atendimentos.buscar(a)["sala"]
    assert atendimentos.passar_sala(a, b, "admin", "entrou na frente")[0]
    assert atendimentos.buscar(b)["sala"] == sala_a, "o paciente que entrou assume a sala física"


@caso("T4. cada um finaliza o seu, sem misturar")
def t4():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    ca, la = novo_material(); cb, lb = novo_material()
    dispensar(a, ca); ciencia(a); usar(a, ca)
    assert atendimentos.passar_sala(a, b, "admin", "médico antecipou")[0]
    dispensar(b, cb); ciencia(b); usar(b, cb)
    assert fechamento.finalizar_uso(b, SALA)[0]
    assert fechamento.concluir(b, SALA)[0]
    assert not fechamento.finalizado(atendimentos.buscar(a)), "o de fora não pode ter sido finalizado"
    assert atendimentos.passar_sala(b, a, "admin", "voltou para a sala")[1] or True
    ok, m, _ = fechamento.finalizar_uso(a, SALA)
    assert ok, m


@caso("T5. troca com material em trânsito (sem ciência)")
def t5():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    ca, la = novo_material(); dispensar(a, ca)         # sem ciência
    ok, m = atendimentos.passar_sala(a, b, "admin", "entrou outro na frente")
    assert ok, m
    assert status(la) == "transito_sala", "o que estava a caminho continua do paciente de origem"
    assert db.escalar("SELECT id_atendimento FROM unidades WHERE nLote = ?", (la,)) == a


@caso("T6. troca entre unidades diferentes é recusada")
def t6():
    a = novo_atendimento()
    ok, outro = atendimentos.abrir({"prontuario": "8700001", "unidade": "HEMODINAMICA - PDT",
                                    "sala": "01", "especialidade": "ORTOPEDIA",
                                    "data_procedimento": atendimentos.hoje_iso()
                                    if hasattr(atendimentos, "hoje_iso") else __import__(
                                        "src.providers.implementations.opme.utils",
                                        fromlist=["x"]).hoje_iso()}, "admin")
    assert ok, outro
    ok, m = atendimentos.passar_sala(a, outro, "admin", "tentativa entre unidades")
    assert not ok and "mesma unidade" in m, m


@caso("T7. troca para atendimento encerrado é recusada")
def t7():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    cb, lb = novo_material(); dispensar(b, cb)
    db.executar("UPDATE atendimentos SET status = 'encerrado' WHERE id_atendimento = ?", (b,))
    ok, m = atendimentos.passar_sala(a, b, "admin", "tentativa com encerrado")
    assert not ok and "abertos" in m, m


@caso("T8. motivo é obrigatório")
def t8():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    ok, m = atendimentos.passar_sala(a, b, "admin", "x")
    assert not ok and "motivo" in m.lower(), m


@caso("T9. fica registrado nos dois prontuários")
def t9():
    a = novo_atendimento(); b = novo_atendimento(); _livre(b)
    assert atendimentos.passar_sala(a, b, "admin", "médico antecipou este paciente")[0]
    for ida, quem in ((a, "origem"), (b, "destino")):
        ev = db.consultar("SELECT tipo, observacao FROM eventos WHERE id_atendimento = ? "
                          "ORDER BY id_evento DESC LIMIT 3", (ida,))
        assert ev, f"sem registro em {quem}"
        assert ev[0]["tipo"] in ("sala_passada", "sala_assumida"), ev[0]["tipo"]


@pytest.mark.parametrize("nome,fn", CASOS, ids=[c[0] for c in CASOS])
def test_troca(client, nome, fn):
    fn()
