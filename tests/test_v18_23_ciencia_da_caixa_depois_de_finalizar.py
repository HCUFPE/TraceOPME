# tests/test_v18_23_ciencia_da_caixa_depois_de_finalizar.py
"""v18.23: ciência da entrega da caixa ao paciente depois da finalização.

Caso real (HC-UFPE, 18/11/2026, prontuário 22302152): o atendimento não
encerrava — "Antes de encerrar, dê ciência da entrega da caixa ao paciente:
COIL EMBOLIZANTE..." — mas a única tela com o botão de ciência (finalizar
registro de uso) redirecionava, porque o uso já estava finalizado. A sala
ficava sem caminho. Agora a tela continua aberta enquanto faltar ciência, e a
ficha do prontuário também tem o botão.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import (atendimentos, dispensacoes,
                                                         entrega_paciente, estoque, fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
AGHU = "87994"                                   # COIL EMBOLIZANTE: caixa vai para o paciente


def _cenario(prontuario, sala):
    entrega_paciente.marcar(AGHU, "caixa para o paciente", "admin")
    codigo = f"78911900{sala}0001"
    ok, m = estoque.cadastrar_manual({"xProd": "COIL EMBOLIZANTE TAM. 10mm", "codigo_barras": codigo,
                                      "codigo_aghu": AGHU, "fornecedor": "F", "marca_fabricante": "M",
                                      "nLote": f"CX{sala}", "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, f"CX{sala}"))
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL WHERE unidade = 'BLOCO CIRURGICO' "
                "AND sala = ? AND id_atendimento <> ?", (sala, ida))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    assert fluxo.bipar(operacao="dispensar_sala", codigo=codigo, usuario="farm1",
                       id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo=codigo, usuario="sala1", id_atendimento=ida)["ok"]
    return ida


def test_sem_ciencia_o_atendimento_nao_encerra(client):
    ida = _cenario("9924100", "61")
    # finalizar o uso exige a ciência...
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "entrega da caixa" in msg


def test_a_tela_de_finalizar_continua_aberta_para_dar_a_ciencia(client, admin_headers):
    """Mesmo com o uso já finalizado, a tela não expulsa enquanto faltar ciência."""
    ida = _cenario("9924200", "62")
    unidade = entrega_paciente.do_atendimento(ida)[0]["id_unidade"]
    assert entrega_paciente.registrar_ciencia(unidade, "sala1")[0]
    assert fechamento.finalizar_uso(ida, SALA)[0]

    # a ciência é desfeita por um novo bip de uso (re-registro): volta a faltar
    db.executar("DELETE FROM eventos WHERE id_unidade = ? AND tipo = 'ciencia_entrega_paciente'",
                (unidade,))
    r = client.get(f"/api/sala-procedimento/atendimento/{ida}/concluir", headers=admin_headers)
    assert r.status_code == 200 and not r.json().get("redirecionar")
    d = r.json()["dados"]
    assert d["ja_finalizado"] is True
    assert [e["id_unidade"] for e in d["entregas"]] == [unidade]
    assert not d["entregas"][0]["ciencia_por"]


def test_a_ficha_da_ciencia_e_o_atendimento_encerra(client, admin_headers):
    """O botão da ficha usa a mesma rota: dá ciência e destrava o encerramento."""
    ida = _cenario("9924300", "63")
    unidade = entrega_paciente.do_atendimento(ida)[0]["id_unidade"]
    r = client.post(f"/api/sala-procedimento/atendimento/{ida}/ciencia/{unidade}",
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert entrega_paciente.do_atendimento(ida)[0]["ciencia_por"]
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert ok, msg
    ok, msg = fechamento.concluir(ida, SALA)
    assert ok, msg
    assert atendimentos.buscar(ida)["status"] == "encerrado"


def test_a_ficha_traz_as_entregas_com_a_situacao(client, admin_headers):
    ida = _cenario("9924400", "64")
    r = client.get(f"/api/sala-procedimento/atendimento/{ida}", headers=admin_headers)
    assert r.status_code == 200
    entregas = r.json()["dados"]["entregas"]
    assert len(entregas) == 1 and entregas[0]["codigo_aghu"] == AGHU
    assert not entregas[0]["ciencia_por"]
