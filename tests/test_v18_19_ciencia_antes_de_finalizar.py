# tests/test_v18_19_ciencia_antes_de_finalizar.py
"""v18.19: na tela de finalizar, as pendências de ciência vêm primeiro.

Cenário descrito pelo HC-UFPE (17/11/2026): 10 materiais dispensados e com
ciência da sala; no meio do procedimento a farmácia dispensa mais 2, sem
ciência; um deles é usado e o outro não. Ao finalizar, a sala vê primeiro as
pendências de ciência, depois o que foi bipado e depois o que volta.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, UTILIZADO
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque,
                                                         fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
CODIGOS = [f"789113000{n:04d}" for n in range(1, 13)]


def _cad(cod, lote):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {lote}", "codigo_barras": cod, "codigo_aghu": "9700",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
                                      "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, lote))


def _cenario():
    """10 com ciência + 2 depois sem ciência (um usado, um não). Devolve o atendimento."""
    for n, c in enumerate(CODIGOS, 1):
        _cad(c, f"CEN{n}")
    ok, ida = atendimentos.abrir({"prontuario": "9921100", "unidade": "BLOCO CIRURGICO", "sala": "48",
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert atendimentos.abrir_sala(ida, "admin")[0]
    for c in CODIGOS[:10]:
        assert fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1",
                           id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    for c in CODIGOS[:6]:                      # usa 6 dos 10
        assert fluxo.bipar(operacao="registrar_uso", codigo=c, usuario="sala1", id_atendimento=ida)["ok"]
    for c in CODIGOS[10:]:                     # mais 2, sem ciência
        assert fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1",
                           id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]
    assert fluxo.bipar(operacao="registrar_uso", codigo=CODIGOS[10], usuario="sala1",
                       id_atendimento=ida)["ok"]      # um extra é usado, sem ciência
    return ida


def test_bipar_o_extra_nao_depende_da_ciencia(client):
    ida = _cenario()
    assert db.escalar("SELECT status FROM unidades WHERE nLote = 'CEN11'") == UTILIZADO


def test_pendencias_de_ciencia_dizem_o_que_aconteceu_com_cada_uma(client):
    ida = _cenario()
    comp = dispensacoes.complemento_pendente(ida)
    assert len(comp) == 2
    por_lote = {i["nLote"]: i for i in comp}
    assert por_lote["CEN11"]["status_unidade"] == UTILIZADO
    assert "já bipado" in por_lote["CEN11"]["destino"]
    assert "volta para a farmácia" in por_lote["CEN12"]["destino"]


def test_finalizar_exige_a_ciencia_e_depois_separa_o_que_volta(client):
    ida = _cenario()
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "mais 2 item(ns)" in msg

    ok, msg, _ = fechamento.finalizar_uso(ida, SALA, ciencia_complemento=True)
    assert ok, msg
    # 7 usados (6 + o extra) e 5 voltando (4 dos 10 + o extra não usado)
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_atendimento = ? AND status = ?",
                      (ida, UTILIZADO)) == 7
    from src.providers.implementations.opme.services import devolucoes
    dev = devolucoes.pendente_do_atendimento(ida)
    bal = devolucoes.balanco(dev["id_devolucao"])
    assert bal["resumo"]["usado"] == 7 and bal["resumo"]["voltando"] == 5
    assert bal["resumo"]["sem_destino"] == 0


def test_tela_de_finalizar_traz_as_pendencias(client, admin_headers):
    ida = _cenario()
    r = client.get(f"/api/sala-procedimento/atendimento/{ida}/concluir", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert len(d["complemento"]) == 2            # bloco 1 da tela
    assert len(d["usados"]) == 7                 # bloco 2
    assert d["sobras"]["total"] == 5             # bloco 3
