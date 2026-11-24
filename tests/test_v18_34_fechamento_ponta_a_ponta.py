# tests/test_v18_34_fechamento_ponta_a_ponta.py
"""Bateria do fechamento da sala, ponta a ponta (pedida pela Camila, 18/11/2026).

24 cenários do ciclo completo: dispensar → ciência → usar → finalizar →
devolver → farmácia conferir → encerrar. Inclui material recebido DEPOIS da
finalização, material que volta para a farmácia, item sem destino, caixa ao
paciente, troca de paciente, cancelamento e as recusas que precisam continuar
existindo.
"""
import pytest
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import (EM_ESTOQUE_FARMACIA, EM_SALA, TRANSITO_SALA,
                                                       UTILIZADO)
from src.providers.implementations.opme.services import (atendimentos, devolucoes, dispensacoes,
                                                         entrega_paciente, estoque, fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
FARM = "BLOCO CIRURGICO"
_n = [0]


def novo_material(aghu="90001", quantidade=1, caixa=False):
    _n[0] += 1
    cod = f"78999{_n[0]:09d}"
    lote = f"SND{_n[0]}"
    ok, m = estoque.cadastrar_manual({
        "xProd": f"MATERIAL SONDA {_n[0]}", "codigo_barras": cod, "codigo_aghu": aghu,
        "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
        "quantidade": str(quantidade), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, FARM, lote))
    return cod, lote


def novo_atendimento():
    _n[0] += 1
    sala = str(300 + _n[0])
    ok, ida = atendimentos.abrir({"prontuario": f"99{_n[0]:05d}", "unidade": FARM, "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert atendimentos.abrir_sala(ida, "admin")[0]
    return ida


def dispensar(ida, cod):
    r = fluxo.bipar(operacao="dispensar_sala", codigo=cod, usuario="farm1",
                    id_atendimento=ida, farmacia=FARM)
    assert r["ok"], r.get("mensagem")


def ciencia(ida):
    d = dispensacoes.pendente_do_atendimento(ida)
    assert d, "sem dispensação pendente"
    ok, m = dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)
    assert ok, m


def usar(ida, cod):
    r = fluxo.bipar(operacao="registrar_uso", codigo=cod, usuario="sala1", id_atendimento=ida)
    assert r["ok"], r.get("mensagem")
    return r


def status(lote):
    return db.escalar("SELECT status FROM unidades WHERE nLote = ?", (lote,))


CENARIOS = []


def cenario(nome):
    def reg(fn):
        CENARIOS.append((nome, fn))
        return fn
    return reg


# ---------------------------------------------------------------- cenários
@cenario("1. usa tudo, finaliza, farmácia conclui")
def c1():
    ida = novo_atendimento()
    cod, lote = novo_material()
    dispensar(ida, cod); ciencia(ida); usar(ida, cod)
    ok, msg, encerrou = fechamento.finalizar_uso(ida, SALA)
    assert ok, msg
    assert not encerrou, "desde a v18.18 quem encerra é a farmácia"
    ok, msg = fechamento.concluir(ida, SALA)
    assert ok, msg
    assert atendimentos.buscar(ida)["status"] == "encerrado"
    assert status(lote) == UTILIZADO


@cenario("2. sobra volta para a farmácia e o estoque é recomposto")
def c2():
    ida = novo_atendimento()
    c1_, l1 = novo_material()
    c2_, l2 = novo_material()
    dispensar(ida, c1_); dispensar(ida, c2_); ciencia(ida); usar(ida, c1_)
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert ok, msg
    dev = devolucoes.pendente_do_atendimento(ida)
    assert dev, "tinha de abrir lista de não utilizados"
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=SALA)
    assert ok, msg
    assert status(l2) == EM_ESTOQUE_FARMACIA
    assert db.escalar("SELECT farmacia FROM unidades WHERE nLote = ?", (l2,)) == FARM
    at = atendimentos.buscar(ida)
    if at["status"] == "aberto":                 # ainda não encerrou sozinho
        ok, msg = fechamento.concluir(ida, SALA)
        assert ok, msg
        at = atendimentos.buscar(ida)
    assert at["status"] == "encerrado", at["status"]


@cenario("3. material dispensado DEPOIS de finalizar: ciência + uso + refinalizar")
def c3():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    dispensar(ida, c2_)
    nova = dispensacoes.pendente_do_atendimento(ida)
    assert nova, "a farmácia tem de conseguir dispensar depois da finalização"
    ciencia(ida)
    usar(ida, c2_)
    assert status(l2) == UTILIZADO
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "não há material novo" in msg, msg     # nada pendente
    ok, msg = fechamento.concluir(ida, SALA)                 # a farmácia fecha
    assert ok, msg


@cenario("4. material novo depois de finalizar e NÃO usado: vai para a devolução")
def c4():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    dispensar(ida, c2_)
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "ciência" in msg, f"devia exigir ciência: {msg}"
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA, ciencia_complemento=True)
    assert ok, msg
    dev = devolucoes.pendente_do_atendimento(ida)
    assert dev and any(i["nLote"] == l2 for i in devolucoes.itens(dev["id_devolucao"]))


@cenario("5. conferência bipando: o não bipado fica sem destino")
def c5():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material(); c3_, l3 = novo_material()
    for c in (c1_, c2_, c3_):
        dispensar(ida, c)
    ciencia(ida); usar(ida, c1_)
    resto = fechamento.sobras(ida)
    por_lote = {i["nLote"]: i["id_unidade"] for i in resto["itens"]}
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA, devolver={f"u:{por_lote[l2]}"})
    assert ok, msg
    dev = devolucoes.pendente_do_atendimento(ida)
    bal = devolucoes.balanco(dev["id_devolucao"])["resumo"]
    assert (bal["usado"], bal["voltando"], bal["sem_destino"]) == (1, 1, 1), bal


@cenario("6. sem destino: farmácia inclui na lista e dá ciência")
def c6():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material(); c3_, l3 = novo_material()
    for c in (c1_, c2_, c3_):
        dispensar(ida, c)
    ciencia(ida); usar(ida, c1_)
    resto = fechamento.sobras(ida)
    por_lote = {i["nLote"]: i["id_unidade"] for i in resto["itens"]}
    # bipa só o l2; o l3 fica sem destino
    assert fechamento.finalizar_uso(ida, SALA, devolver={f"u:{por_lote[l2]}"})[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    ok, msg = devolucoes.incluir_sem_destino(dev["id_devolucao"], por_lote[l3], SALA)
    assert ok, msg
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=SALA)
    assert ok, msg
    assert status(l2) == EM_ESTOQUE_FARMACIA and status(l3) == EM_ESTOQUE_FARMACIA


@cenario("7. caixa ao paciente: ciência obrigatória para finalizar")
def c7():
    entrega_paciente.marcar("87994", "caixa para o paciente", "admin")
    ida = novo_atendimento()
    cod, lote = novo_material(aghu="87994")
    dispensar(ida, cod); ciencia(ida); usar(ida, cod)
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "entrega da caixa" in msg, msg
    unidade = entrega_paciente.do_atendimento(ida)[0]["id_unidade"]
    assert entrega_paciente.registrar_ciencia(unidade, "sala1")[0]
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert ok, msg


@cenario("8. refinalizar sem material novo é recusado")
def c8():
    ida = novo_atendimento()
    cod, lote = novo_material()
    dispensar(ida, cod); ciencia(ida); usar(ida, cod)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "não há material novo" in msg, msg


@cenario("9. depois de encerrado, não dá para bipar uso nem dispensar")
def c9():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    assert fechamento.concluir(ida, SALA)[0]
    r = fluxo.bipar(operacao="registrar_uso", codigo=c2_, usuario="sala1", id_atendimento=ida)
    assert not r["ok"], "atendimento encerrado não pode registrar uso"
    r2 = fluxo.bipar(operacao="dispensar_sala", codigo=c2_, usuario="farm1",
                     id_atendimento=ida, farmacia=FARM)
    assert not r2["ok"], "atendimento encerrado não pode receber dispensação"


@cenario("10. concluir com devolução pendente é recusado")
def c10():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); dispensar(ida, c2_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    ok, msg = fechamento.concluir(ida, SALA)
    assert not ok, "a farmácia ainda não conferiu a devolução"


@cenario("11. confirmar a devolução duas vezes")
def c11():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); dispensar(ida, c2_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    assert devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=SALA)[0]
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=SALA)
    assert not ok, "não pode confirmar a mesma lista duas vezes"


@cenario("12. material em trânsito (sem ciência) na hora de finalizar")
def c12():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); ciencia(ida); usar(ida, c1_)
    dispensar(ida, c2_)                      # fica em trânsito, sem ciência
    assert status(l2) == TRANSITO_SALA
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA, ciencia_complemento=True)
    assert ok, msg
    assert status(l2) in (EM_SALA, EM_ESTOQUE_FARMACIA), status(l2)
    dev = devolucoes.pendente_do_atendimento(ida)
    assert dev and any(i["nLote"] == l2 for i in devolucoes.itens(dev["id_devolucao"])), \
        "o que chegou depois e não foi usado tem de voltar"


@cenario("13. balanço fecha: usados + voltando + sem destino = dispensados")
def c13():
    ida = novo_atendimento()
    lotes = []
    for _ in range(4):
        c, l = novo_material(); lotes.append((c, l)); dispensar(ida, c)
    ciencia(ida)
    usar(ida, lotes[0][0]); usar(ida, lotes[1][0])
    resto = fechamento.sobras(ida)
    por_lote = {i["nLote"]: i["id_unidade"] for i in resto["itens"]}
    assert fechamento.finalizar_uso(ida, SALA, devolver={f"u:{por_lote[lotes[2][1]]}"})[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    r = devolucoes.balanco(dev["id_devolucao"])["resumo"]
    assert r["usado"] + r["voltando"] + r["sem_destino"] == 4, r


@cenario("14. troca de paciente não leva material")
def c14():
    ida = novo_atendimento()
    cod, lote = novo_material()
    dispensar(ida, cod); ciencia(ida)
    outro = novo_atendimento()      # abre em outra sala
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL WHERE id_atendimento = ?", (outro,))
    ok, msg = atendimentos.passar_sala(ida, outro, "admin", "médico trocou a ordem")
    assert ok, msg
    assert db.escalar("SELECT id_atendimento FROM unidades WHERE nLote = ?", (lote,)) == ida, \
        "o material tem de continuar com o paciente de origem"


@cenario("15. procedimento cancelado com material na sala")
def c15():
    ida = novo_atendimento()
    cod, lote = novo_material()
    dispensar(ida, cod); ciencia(ida)
    ok, msg = atendimentos.cancelar(ida, "admin", "Paciente sem condição clínica", "")
    assert ok, msg
    assert status(lote) in (EM_ESTOQUE_FARMACIA, EM_SALA), status(lote)


# ------------------------------------------------ segunda rodada: bordas
@cenario("16. material devolvido por engano volta para o mesmo paciente")
def c16():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); dispensar(ida, c2_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    assert devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=SALA)[0]
    assert status(l2) == EM_ESTOQUE_FARMACIA
    at = atendimentos.buscar(ida)
    assert at["status"] == "encerrado"
    # o médico pediu o material de volta: o atendimento está encerrado
    r = fluxo.bipar(operacao="dispensar_sala", codigo=c2_, usuario="farm1",
                    id_atendimento=ida, farmacia=FARM)
    assert not r["ok"], "encerrado não recebe"
    assert "encerr" in (r.get("mensagem") or "").lower(), r.get("mensagem")


@cenario("17. farmácia tira item da lista de não utilizados")
def c17():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); dispensar(ida, c2_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    itens = devolucoes.itens(dev["id_devolucao"])
    ok, msg, _ = devolucoes.remover_item(itens[0]["id_item"], "admin", "não chegou")
    assert ok, msg
    assert status(l2) == EM_SALA, status(l2)
    sobra = fechamento.sobras(ida)
    assert sobra["total"] == 1, "o item tirado volta a ser pendência da sala"


@cenario("18. uso no paciente errado: passa, mas avisa e deixa rastro")
def c18():
    """Na sala isso acontece de verdade, então o bipe não trava — v18.34 passou a
    registrar a saída na ficha do paciente de origem e nos dois históricos."""
    a1 = novo_atendimento(); a2 = novo_atendimento()
    cod, lote = novo_material()
    dispensar(a1, cod); ciencia(a1)
    r = fluxo.bipar(operacao="registrar_uso", codigo=cod, usuario="sala1", id_atendimento=a2)
    assert r["ok"]
    assert any("outro paciente" in a for a in r["alertas"]), r["alertas"]
    rastro = atendimentos.materiais_usados_em_outro(a1)
    assert [x["nLote"] for x in rastro] == [lote]


@cenario("19. dois pacientes na mesma sala: finalizar um não mexe no outro")
def c19():
    a1 = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(a1, c1_); ciencia(a1); usar(a1, c1_)
    a2 = novo_atendimento()
    dispensar(a2, c2_); ciencia(a2)
    assert fechamento.finalizar_uso(a1, SALA)[0]
    assert status(l2) == EM_SALA
    assert not fechamento.finalizado(atendimentos.buscar(a2))


@cenario("20. finalizar com dispensação em trânsito exige a ciência")
def c20():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); ciencia(ida); usar(ida, c1_)
    dispensar(ida, c2_)                       # em trânsito
    ok, msg, _ = fechamento.finalizar_uso(ida, SALA)
    assert not ok and "ciência" in msg, msg


@cenario("21. concluir com item sem destino é recusado")
def c21():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material(); c3_, l3 = novo_material()
    for c in (c1_, c2_, c3_):
        dispensar(ida, c)
    ciencia(ida); usar(ida, c1_)
    por_lote = {i["nLote"]: i["id_unidade"] for i in fechamento.sobras(ida)["itens"]}
    assert fechamento.finalizar_uso(ida, SALA, devolver={f"u:{por_lote[l2]}"})[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    assert devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="admin", responsavel=SALA)[0]
    ok, msg = fechamento.concluir(ida, SALA)
    assert not ok, "o item sem destino ainda está com o paciente"


@cenario("22. devolução com material de outro paciente: aceita com alerta")
def c22():
    a1 = novo_atendimento(); a2 = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material(); c3_, l3 = novo_material()
    dispensar(a1, c1_); dispensar(a1, c2_); ciencia(a1); usar(a1, c1_)
    dispensar(a2, c3_); ciencia(a2)
    assert fechamento.finalizar_uso(a1, SALA)[0]
    r = devolucoes.bipar(codigo=c3_, id_atendimento=a1, usuario="farm1", devolvido_por="sala1")
    assert r.get("ok"), r
    assert any("OUTRO paciente" in a for a in (r.get("alertas") or [])), r.get("alertas")


@cenario("23. uso finalizado some da fila de 'a concluir' depois da farmácia")
def c23():
    ida = novo_atendimento()
    cod, lote = novo_material()
    dispensar(ida, cod); ciencia(ida); usar(ida, cod)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    fila = {l["id_atendimento"] for l in fechamento.a_concluir(FARM)}
    assert ida in fila, "tem de aparecer para a farmácia concluir"
    assert fechamento.concluir(ida, SALA)[0]
    fila2 = {l["id_atendimento"] for l in fechamento.a_concluir(FARM)}
    assert ida not in fila2


@cenario("24. material usado não pode entrar na lista de não utilizados")
def c24():
    ida = novo_atendimento()
    c1_, l1 = novo_material(); c2_, l2 = novo_material()
    dispensar(ida, c1_); dispensar(ida, c2_); ciencia(ida); usar(ida, c1_)
    assert fechamento.finalizar_uso(ida, SALA)[0]
    dev = devolucoes.pendente_do_atendimento(ida)
    usado = db.escalar("SELECT id_unidade FROM unidades WHERE nLote = ?", (l1,))
    ok, msg = devolucoes.incluir_sem_destino(dev["id_devolucao"], usado, SALA)
    assert not ok and "não está mais com o paciente" in msg, msg


@pytest.mark.parametrize("nome,fn", CENARIOS, ids=[c[0] for c in CENARIOS])
def test_fechamento(client, nome, fn):
    fn()
