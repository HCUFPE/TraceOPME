# tests/test_v18_37_corrigir_peca_do_uso.py
"""v18.37: trocar a peça registrada num uso, quando o bipe pegou a errada.

Caso real (HC-UFPE, 18/11/2026): a farmácia dispensou uma unidade, a sala deu
ciência, e o bipe do uso consumiu outra unidade do mesmo material parada em
outro estoque — "uso sem dispensação" — deixando a dispensada presa na sala.
Corrigir isso exigia três telas na ordem certa; agora é uma operação só.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO,
                                                       EM_SALA, UTILIZADO)
from src.providers.implementations.opme.services import (atendimentos, correcoes_uso, devolucoes,
                                                         dispensacoes, estoque, fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
FARM = "BLOCO CIRURGICO"
_n = [0]


def _cenario():
    """1 peça dispensada e na sala + 1 peça do mesmo material usada por engano."""
    _n[0] += 1
    cod, aghu = f"78996{_n[0]:09d}", f"9252{_n[0]}"
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA HIDROFILICO", "codigo_barras": cod, "codigo_aghu": aghu,
        "fornecedor": "APT", "marca_fabricante": "APT", "nLote": f"LOTE-SALA-{_n[0]}",
        "dVal": "2027-12-04", "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA HIDROFILICO", "codigo_barras": cod, "codigo_aghu": aghu,
        "fornecedor": "APT", "marca_fabricante": "APT", "nLote": f"LOTE-ALMOX-{_n[0]}",
        "dVal": "2027-12-04", "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    da_sala = db.escalar("SELECT id_unidade FROM unidades WHERE nLote = ?", (f"LOTE-SALA-{_n[0]}",))
    do_almox = db.escalar("SELECT id_unidade FROM unidades WHERE nLote = ?", (f"LOTE-ALMOX-{_n[0]}",))
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE id_unidade = ?",
                (EM_ESTOQUE_FARMACIA, FARM, da_sala))
    db.executar("UPDATE unidades SET status = ? WHERE id_unidade = ?",
                (EM_ESTOQUE_RECEBIMENTO, do_almox))

    ok, ida = atendimentos.abrir({"prontuario": f"777{_n[0]:04d}", "unidade": FARM,
                                  "sala": str(600 + _n[0]), "especialidade": "ORTOPEDIA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert atendimentos.abrir_sala(ida, "admin")[0]
    assert fluxo.bipar(operacao="dispensar_sala", codigo=cod, usuario="farm1",
                       id_atendimento=ida, farmacia=FARM)["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    # o engano: registra o uso na unidade do almoxarifado
    db.executar("UPDATE unidades SET status = ?, id_atendimento = ? WHERE id_unidade = ?",
                (UTILIZADO, ida, do_almox))
    with db.transacao() as conn:
        db.registrar_evento(conn, tipo="saida_sem_dispensacao", id_unidade=do_almox,
                            id_atendimento=ida, usuario="sala1",
                            observacao="Usado na sala sem dispensação prévia")
        db.registrar_evento(conn, tipo="registrar_uso", id_unidade=do_almox, id_atendimento=ida,
                            usuario="sala1", status_anterior=EM_ESTOQUE_RECEBIMENTO,
                            status_novo=UTILIZADO)
        from src.providers.implementations.opme.services import usos_sem_dispensacao
        usos_sem_dispensacao.registrar(conn, id_unidade=do_almox, id_atendimento=ida, usuario="sala1")
    return ida, da_sala, do_almox


def test_a_tela_mostra_a_troca_possivel(client):
    ida, da_sala, do_almox = _cenario()
    pend = correcoes_uso.pendencias(ida)
    assert len(pend) == 1
    assert pend[0]["id_unidade"] == do_almox
    assert [t["id_unidade"] for t in pend[0]["trocas"]] == [da_sala]
    assert "Almoxarifado" in pend[0]["volta_para"] or "lmox" in pend[0]["volta_para"]


def test_a_troca_conserta_os_dois_lados(client):
    ida, da_sala, do_almox = _cenario()
    ok, msg = correcoes_uso.trocar(do_almox, da_sala, "admin",
                                   "o bipe pegou peca de outro estoque; a usada foi a dispensada")
    assert ok, msg
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (da_sala,)) == UTILIZADO
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?",
                      (do_almox,)) == EM_ESTOQUE_RECEBIMENTO
    assert not db.escalar("SELECT COALESCE(id_atendimento, '') FROM unidades WHERE id_unidade = ?", (do_almox,))
    assert fechamento.sobras(ida)["total"] == 0
    assert correcoes_uso.pendencias(ida) == []


def test_o_historico_guarda_as_duas_pontas(client):
    ida, da_sala, do_almox = _cenario()
    assert correcoes_uso.trocar(do_almox, da_sala, "admin", "correcao do registro de uso")[0]
    corrigido = db.consultar_um("""SELECT tipo, COALESCE(observacao,'') o FROM eventos
                                   WHERE id_unidade = ? AND tipo = 'uso_corrigido'""", (do_almox,))
    assert corrigido and da_sala in corrigido["o"]
    novo = db.consultar_um("""SELECT COALESCE(observacao,'') o FROM eventos
                              WHERE id_unidade = ? AND tipo = 'registrar_uso'
                              ORDER BY id_evento DESC LIMIT 1""", (da_sala,))
    assert do_almox in novo["o"] and "Correção do registro" in novo["o"]
    # a pendência de "uso sem dispensação" some
    from src.providers.implementations.opme.services import usos_sem_dispensacao
    assert do_almox not in [p["id_unidade"] for p in usos_sem_dispensacao.pendentes()]


def test_sai_da_lista_de_nao_utilizados(client):
    """Se a sala já tinha finalizado, a peça certa estava na lista da farmácia."""
    ida, da_sala, do_almox = _cenario()
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert ok, msg
    dev = devolucoes.pendente_do_atendimento(ida)
    assert any(i["id_unidade"] == da_sala for i in devolucoes.itens(dev["id_devolucao"]))

    assert correcoes_uso.trocar(do_almox, da_sala, "admin", "a peca usada foi a dispensada")[0]
    pendentes = [i["id_unidade"] for i in devolucoes.itens(dev["id_devolucao"])
                 if i["situacao"] == "pendente"]
    assert da_sala not in pendentes
    bal = devolucoes.balanco(dev["id_devolucao"])["resumo"]
    assert bal["sem_destino"] == 0


def test_recusa_o_que_nao_deve_passar(client):
    ida, da_sala, do_almox = _cenario()
    ok, msg = correcoes_uso.trocar(do_almox, da_sala, "admin", "curto")
    assert not ok and "motivo" in msg.lower()
    ok, msg = correcoes_uso.trocar(da_sala, do_almox, "admin", "invertido de proposito aqui")
    assert not ok and "não está como utilizada" in msg

    outra_ida, outra_sala, _o = _cenario()
    ok, msg = correcoes_uso.trocar(do_almox, outra_sala, "admin", "pecas de procedimentos diferentes")
    assert not ok and "mesmo procedimento" in msg


def test_pela_tela(client, admin_headers):
    ida, da_sala, do_almox = _cenario()
    r = client.get("/api/sala-procedimento/correcao-uso", params={"atendimento": ida},
                   headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert [p["id_unidade"] for p in d["pendencias"]] == [do_almox]

    r = client.post(f"/api/sala-procedimento/correcao-uso/{do_almox}",
                    data={"id_na_sala": da_sala, "motivo": "o bipe pegou a peca errada do estoque"},
                    headers=admin_headers)
    assert r.status_code == 200
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (da_sala,)) == UTILIZADO

    ficha = client.get(f"/api/sala-procedimento/atendimento/{ida}", headers=admin_headers)
    assert ficha.json()["dados"]["usos_a_corrigir"] == 0
