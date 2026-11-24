# tests/test_v18_18_material_depois_de_finalizar.py
"""v18.18: material extra pedido DEPOIS de a sala finalizar.

Caso real (HC-UFPE, 17/11/2026): a sala finalizou, o médico pediu mais um
material, a farmácia dispensou — e a sala não conseguia nem dar ciência do
recebimento nem finalizar de novo. Quando nada sobrava, era pior: a
finalização encerrava o atendimento na hora e a farmácia nem dispensar podia.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, EM_SALA, UTILIZADO
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque,
                                                         fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}


def _cad(cod, lote):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {lote}", "codigo_barras": cod, "codigo_aghu": "9400",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote,
                                      "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, lote))


def _atendimento(prontuario, sala):
    """Prontuário só com dígitos: `abrir` guarda apenas os números e reaproveita
    o atendimento quando prontuário/unidade/sala/especialidade/data batem."""
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL WHERE unidade = 'BLOCO CIRURGICO' "
                "AND sala = ? AND id_atendimento <> ?", (sala, ida))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    return ida


def _dispensar(ida, codigo):
    assert fluxo.bipar(operacao="dispensar_sala", codigo=codigo, usuario="farm1",
                       id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]


def test_finalizar_nao_encerra_mais_sozinho(client):
    """Sem sobra nenhuma, o atendimento continua aberto: quem fecha é a farmácia."""
    _cad("7891118000011", "FIN1")
    ida = _atendimento("9918100", "41")
    _dispensar(ida, "7891118000011")
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891118000011", usuario="sala1",
                       id_atendimento=ida)["ok"]

    ok, msg, encerrou = fechamento.finalizar_uso(ida, SALA)
    assert ok and not encerrou, msg
    assert atendimentos.buscar(ida)["status"] == "aberto"
    # e a farmácia fecha quando quiser
    ok, msg = fechamento.concluir(ida, SALA)
    assert ok, msg
    assert atendimentos.buscar(ida)["status"] == "encerrado"


def test_material_extra_depois_de_finalizar(client):
    _cad("7891118000028", "EX1")
    _cad("7891118000035", "EX2")
    ida = _atendimento("9918200", "42")
    _dispensar(ida, "7891118000028")
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891118000028", usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert fechamento.finalizar_uso(ida, SALA)[0]

    # o médico pede mais um: a farmácia AINDA consegue dispensar
    _dispensar(ida, "7891118000035")
    nova = dispensacoes.pendente_do_atendimento(ida)
    assert nova, "a farmácia precisa conseguir dispensar depois da finalização"

    # a sala dá ciência do recebimento normalmente
    ok, msg = dispensacoes.confirmar(id_dispensacao=nova["id_dispensacao"], logado=SALA)
    assert ok, msg
    assert db.escalar("SELECT status FROM unidades WHERE nLote = 'EX2'") == EM_SALA
    # e bipa o uso do extra
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891118000035", usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert db.escalar("SELECT status FROM unidades WHERE nLote = 'EX2'") == UTILIZADO


def test_finalizar_de_novo_exige_ciencia_do_que_chegou_depois(client):
    _cad("7891118000042", "EX3")
    _cad("7891118000059", "EX4")
    ida = _atendimento("9918300", "43")
    _dispensar(ida, "7891118000042")
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891118000042", usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert fechamento.finalizar_uso(ida, SALA)[0]

    _dispensar(ida, "7891118000059")          # extra, ainda sem ciência
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "ciência" in msg        # a ciência é obrigatória

    ok, msg, _ = fechamento.finalizar_uso(ida, SALA, ciencia_complemento=True)
    assert ok, msg
    # não foi usado: entra na lista de devolução da farmácia
    assert fechamento.tem_devolucao_pendente(ida)
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = 'EX4' AND status = ?", (EM_SALA,)) == 1


def test_sem_material_novo_nao_refinaliza(client):
    _cad("7891118000066", "EX5")
    ida = _atendimento("9918400", "44")
    _dispensar(ida, "7891118000066")
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891118000066", usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert fechamento.finalizar_uso(ida, SALA)[0]
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "não há material novo" in msg


def test_tela_de_concluir_continua_acessivel_com_material_novo(client, admin_headers):
    _cad("7891118000073", "EX6")
    _cad("7891118000080", "EX7")
    ida = _atendimento("9918500", "45")
    _dispensar(ida, "7891118000073")
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    assert fluxo.bipar(operacao="registrar_uso", codigo="7891118000073", usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert fechamento.finalizar_uso(ida, SALA)[0]

    # sem material novo, a tela redireciona (nada a fazer)
    r = client.get(f"/api/sala-procedimento/atendimento/{ida}/concluir", headers=admin_headers)
    assert r.json().get("redirecionar")

    _dispensar(ida, "7891118000080")
    r = client.get(f"/api/sala-procedimento/atendimento/{ida}/concluir", headers=admin_headers)
    assert r.status_code == 200 and not r.json().get("redirecionar")
    dados = r.json()["dados"]
    assert dados["ja_finalizado"] is True and len(dados["complemento"]) == 1
