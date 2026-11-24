# tests/test_v18_20_sem_destino_depois_de_finalizar.py
"""Item "sem destino" quando a sala já finalizou (HC-UFPE, 17/11/2026).

Caso real: Hemodinâmica — Sala 01, prontuário 22302152. Foram 24 itens para o
paciente, 11 bipados como usados, 12 na lista de não utilizados e 1 ficou
"sem destino" (nem bipado, nem na lista). A farmácia abriu a conferência e
não tem onde marcar esse item; a sala achava que não podia mais fazer nada
porque o uso já estava finalizado.

Os dois caminhos têm de continuar abertos depois da finalização:
  a) foi usado  -> a sala bipa o uso no prontuário (v18.18);
  b) voltou     -> a sala finaliza de novo e o item entra na lista da farmácia.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, EM_SALA, UTILIZADO
from src.providers.implementations.opme.services import (atendimentos, devolucoes, dispensacoes,
                                                         estoque, fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
def _codigos(sala):
    return [f"78911{sala}00{n:04d}" for n in range(1, 5)]


def _cad(cod, lote):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {lote}", "codigo_barras": cod, "codigo_aghu": "9011",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
                                      "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, lote))


def _cenario(prontuario, sala):
    """4 itens: 1 usado, 2 devolvidos na conferência bipando, 1 sem destino."""
    codigos = _codigos(sala)
    for n, c in enumerate(codigos, 1):
        _cad(c, f"SD{sala}{n}")
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL WHERE unidade = 'BLOCO CIRURGICO' "
                "AND sala = ? AND id_atendimento <> ?", (sala, ida))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    for c in codigos:
        assert fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1",
                           id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo=codigos[0], usuario="sala1", id_atendimento=ida)["ok"]
    # conferência bipando: só 2 dos 3 que sobraram são bipados; o 4º fica sem destino
    resto = fechamento.sobras(ida)
    por_lote = {i["nLote"]: i["id_unidade"] for i in resto["itens"]}
    bipados = {f"u:{por_lote[f'SD{sala}{n}']}" for n in (2, 3)}
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA, devolver=bipados)
    assert ok, msg
    assert "continuam com o paciente" in msg
    return ida, por_lote[f"SD{sala}4"], codigos


def _balanco(ida):
    dev = devolucoes.pendente_do_atendimento(ida)
    return devolucoes.balanco(dev["id_devolucao"])["resumo"]


def test_a_farmacia_ve_o_item_como_sem_destino(client):
    ida, sem_destino, codigos = _cenario("9920100", "51")
    bal = _balanco(ida)
    assert bal["usado"] == 1 and bal["voltando"] == 2 and bal["sem_destino"] == 1
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (sem_destino,)) == EM_SALA


def test_foi_usado_a_sala_bipa_mesmo_com_o_uso_finalizado(client):
    """Caminho (a): o uso já estava finalizado e a bipagem continua aberta."""
    ida, sem_destino, codigos = _cenario("9920200", "52")
    assert fechamento.finalizado(atendimentos.buscar(ida))
    r = fluxo.bipar(operacao="registrar_uso", codigo=codigos[3], usuario="sala1", id_atendimento=ida)
    assert r["ok"], r.get("mensagem")
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (sem_destino,)) == UTILIZADO
    bal = _balanco(ida)
    assert bal["usado"] == 2 and bal["sem_destino"] == 0


def test_voltou_a_sala_finaliza_de_novo_e_o_item_entra_na_lista(client):
    """Caminho (b): o item volta fisicamente e entra na mesma lista da farmácia."""
    ida, sem_destino, codigos = _cenario("9920300", "53")
    assert fechamento.sobras(ida)["total"] == 1
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert ok, msg
    bal = _balanco(ida)
    assert bal["voltando"] == 3 and bal["sem_destino"] == 0
    # e a farmácia conclui normalmente
    dev = devolucoes.pendente_do_atendimento(ida)
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin",
                                   responsavel=SALA)
    assert ok, msg
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?",
                      (sem_destino,)) == EM_ESTOQUE_FARMACIA


def test_tela_de_finalizar_continua_acessivel_so_com_a_sobra(client, admin_headers):
    ida, _, _c = _cenario("9920400", "54")
    r = client.get(f"/api/sala-procedimento/atendimento/{ida}/concluir", headers=admin_headers)
    assert r.status_code == 200 and not r.json().get("redirecionar")
    d = r.json()["dados"]
    assert d["ja_finalizado"] is True and d["sobras"]["total"] == 1 and d["complemento"] == []


# ---------------------------------------------------------------- v18.22
def test_farmacia_recebe_de_volta_o_item_sem_destino(client):
    """Caminho (c): o material chegou na farmácia e ela mesma inclui na lista."""
    ida, sem_destino, _c = _cenario("9920500", "55")
    dev = devolucoes.pendente_do_atendimento(ida)
    assert devolucoes.balanco(dev["id_devolucao"])["resumo"]["sem_destino"] == 1

    ok, msg = devolucoes.incluir_sem_destino(dev["id_devolucao"], sem_destino, SALA)
    assert ok, msg
    bal = devolucoes.balanco(dev["id_devolucao"])["resumo"]
    assert bal["voltando"] == 3 and bal["sem_destino"] == 0
    # incluir duas vezes não duplica
    ok2, msg2 = devolucoes.incluir_sem_destino(dev["id_devolucao"], sem_destino, SALA)
    assert not ok2 and "já está na lista" in msg2
    # e a ciência leva o item de volta ao estoque da farmácia
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin",
                                   responsavel=SALA)
    assert ok, msg
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?",
                      (sem_destino,)) == EM_ESTOQUE_FARMACIA


def test_nao_inclui_material_de_outro_procedimento_nem_ja_usado(client):
    ida, sem_destino, codigos = _cenario("9920600", "56")
    dev = devolucoes.pendente_do_atendimento(ida)
    outro = db.escalar("SELECT id_unidade FROM unidades WHERE id_atendimento IS NULL "
                       "OR id_atendimento <> ? LIMIT 1", (ida,))
    ok, msg = devolucoes.incluir_sem_destino(dev["id_devolucao"], outro, SALA)
    assert not ok and "não é deste procedimento" in msg
    # já usado no paciente: não entra na lista de não utilizados
    usado = db.escalar("SELECT id_unidade FROM unidades WHERE id_atendimento = ? AND status = ?",
                       (ida, UTILIZADO))
    ok, msg = devolucoes.incluir_sem_destino(dev["id_devolucao"], usado, SALA)
    assert not ok and "não está mais com o paciente" in msg


def test_a_tela_da_farmacia_responde_com_a_inclusao(client, admin_headers):
    ida, sem_destino, _c = _cenario("9920700", "57")
    dev = devolucoes.pendente_do_atendimento(ida)
    r = client.post(f"/api/devolucoes/{dev['id_devolucao']}/incluir-sem-destino",
                    data={"id_unidade": sem_destino}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert devolucoes.balanco(dev["id_devolucao"])["resumo"]["sem_destino"] == 0
