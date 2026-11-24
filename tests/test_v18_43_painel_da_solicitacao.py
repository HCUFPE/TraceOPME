# tests/test_v18_43_painel_da_solicitacao.py
"""v18.43: pedidos da sala na tela de dispensar, e descancelar procedimento.

Camila (20/11/2026), olhando a tela "Dispensar para a sala":
  1. "a medida que for sendo atendido, o item pode ir subindo? pq como essa
     lista é fixa, eu preciso ficar indo para baixo e para cima para ver se de
     fato foi atendido."
  2. "os itens solicitados que não tem código aghu também podem ser atendidos
     por algum material que foi bipado. então permitir associar."
  3. "alguns itens não vão ser atendidos porque falta no estoque. então ter a
     opção de marcar falta de estoque."
  4. "depois de eu atender uma solicitação e aparecer outra, será que não
     poderiam sair separadas para não confundir os atendimentos?"
  5. "se um procedimento for cancelado permitir descancelar, pois pode ter
     sido por engano."
"""
import pytest

from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso

FARM = "BLOCO CIRURGICO"
_n = [0]


def _atendimento():
    _n[0] += 1
    ok, ida = atendimentos.abrir({"prontuario": f"77{_n[0]:05d}", "paciente": "PACIENTE TESTE",
                                  "unidade": FARM, "sala": str(400 + _n[0]),
                                  "especialidade": "ORTOPEDIA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


def _material_na_farmacia(nome="MATERIAL BIPADO"):
    """Cadastra 1 unidade e deixa no estoque da farmácia. Devolve (codigo, aghu)."""
    _n[0] += 1
    cod, lote, aghu = f"77991{_n[0]:09d}", f"L43{_n[0]}", f"7430{_n[0]}"
    ok, m = estoque.cadastrar_manual({
        "xProd": nome, "codigo_barras": cod, "codigo_aghu": aghu, "fornecedor": "F",
        "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01", "quantidade": "1",
        "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, FARM, lote))
    return cod, aghu


def _formulario_com_linhas(minimo=2):
    for chave in solicitacoes.FORMULARIOS:
        ls = solicitacoes.linhas(chave)
        if len(ls) >= minimo:
            return chave, ls
    pytest.skip("nenhum formulário com linhas suficientes")


def _linha_sem_codigo():
    """Uma linha de formulário que a sala pede pelo nome (sem código AGHU)."""
    for chave in solicitacoes.FORMULARIOS:
        for l in solicitacoes.linhas(chave):
            if not l["codigos"]:
                return chave, l
    pytest.skip("nenhuma linha sem código AGHU")


# --------------------------------------------------------- 2) associar material
def test_linha_sem_aghu_pode_ser_associada_ao_material_bipado(client):
    ida = _atendimento()
    chave, l = _linha_sem_codigo()
    pedido = {str(l["linha"]): 1}
    if l["pede_especificacao"]:
        espec = {str(l["linha"]): "COBRA 05 F"}
    else:
        espec = {}
    ok, msg = solicitacoes.salvar_formulario(ida, chave, pedido, espec, "sala1")
    assert ok, msg

    cod, _ = _material_na_farmacia("CATETER COBRA 5F")
    r = fluxo.bipar(operacao="dispensar_sala", codigo=cod, usuario="farm1",
                    id_atendimento=ida, farmacia=FARM)
    assert r["ok"], r.get("mensagem")

    s = solicitacoes.situacao(ida)
    item = next(x for x in s["linhas"] if x["id_item"])
    assert item["sem_codigo"] and item["status"] == "faltando"
    assert s["nao_solicitados"], "o material bipado fica como não solicitado até associarem"

    ids = s["nao_solicitados"][0]["ids"]
    ok, msg = solicitacoes.vincular_outro_codigo(ida, item["id_item"], ids,
                                                 "a sala pediu pelo nome", "farm1")
    assert ok, msg
    depois = solicitacoes.situacao(ida)
    linha = next(x for x in depois["linhas"] if x["id_item"] == item["id_item"])
    assert linha["status"] == "atendido" and linha["dispensado"] == 1
    assert linha["vinculos"], "o material associado tem de aparecer na linha"
    assert not depois["nao_solicitados"], "deixa de ser 'bipado sem solicitação'"


# ------------------------------------------------------- 3) falta de estoque
def test_marcar_e_desfazer_falta_de_estoque(client):
    ida = _atendimento()
    chave, ls = _formulario_com_linhas(2)
    ok, msg = solicitacoes.salvar_formulario(ida, chave, {str(ls[0]["linha"]): 1,
                                                          str(ls[1]["linha"]): 1}, {}, "sala1")
    assert ok, msg
    item = solicitacoes.situacao(ida)["linhas"][0]

    assert solicitacoes.marcar_falta(ida, item["id_item"], "x", "farm1")[0] is False, \
        "motivo curto tem de ser recusado"

    ok, msg = solicitacoes.marcar_falta(ida, item["id_item"], "Sem estoque na farmácia", "farm1")
    assert ok, msg
    s = solicitacoes.situacao(ida)
    linha = next(l for l in s["linhas"] if l["id_item"] == item["id_item"])
    assert linha["status"] == "falta"
    assert linha["falta_motivo"] == "Sem estoque na farmácia" and linha["falta_por"] == "farm1"
    assert s["qtd_sem_estoque"] == 1
    assert s["qtd_a_atender"] == 1, "a linha em falta sai da fila do que ainda falta atender"

    ok, msg = solicitacoes.marcar_falta(ida, item["id_item"], "", "farm1", falta=False)
    assert ok, msg
    s = solicitacoes.situacao(ida)
    assert s["qtd_sem_estoque"] == 0 and s["qtd_a_atender"] == 2


def test_item_atendido_nao_vira_falta(client):
    ida = _atendimento()
    chave, l = _linha_sem_codigo()
    espec = {str(l["linha"]): "PIG 05F"} if l["pede_especificacao"] else {}
    assert solicitacoes.salvar_formulario(ida, chave, {str(l["linha"]): 1}, espec, "sala1")[0]
    item = solicitacoes.situacao(ida)["linhas"][0]
    assert solicitacoes.marcar_manual(ida, item["id_item"], "farm1")[0]
    ok, msg = solicitacoes.marcar_falta(ida, item["id_item"], "Sem estoque na farmácia", "farm1")
    assert not ok and "já está atendido" in msg


# ------------------------------------------------------------- 4) rodadas
def test_pedido_novo_depois_de_finalizar_fica_em_bloco_separado(client):
    ida = _atendimento()
    chave, ls = _formulario_com_linhas(2)
    assert solicitacoes.salvar_formulario(ida, chave, {str(ls[0]["linha"]): 1}, {}, "sala1")[0]
    s = solicitacoes.situacao(ida)
    assert len(s["pedidos"]) == 1 and s["pedidos"][0]["titulo"] == "Pedido"

    ok, msg = solicitacoes.finalizar(ida, "farm1", "sem estoque")
    assert ok, msg
    assert solicitacoes.salvar_formulario(ida, chave, {str(ls[0]["linha"]): 1,
                                                       str(ls[1]["linha"]): 2}, {}, "sala1")[0]
    s = solicitacoes.situacao(ida)
    assert len(s["pedidos"]) == 2, "o pedido novo tem de sair separado do anterior"
    assert [b["titulo"] for b in s["pedidos"]] == ["1º pedido", "2º pedido"]
    assert [l["descricao"] for l in s["pedidos"][1]["linhas"]] == [ls[1]["descricao"]]
    assert s["pedidos"][0]["qtd_linhas"] == 1 and s["pedidos"][1]["qtd_linhas"] == 1


# ------------------------------------------------------ 5) descancelar
def test_descancelar_procedimento(client):
    ida = _atendimento()
    chave, ls = _formulario_com_linhas(1)
    assert solicitacoes.salvar_formulario(ida, chave, {str(ls[0]["linha"]): 1}, {}, "sala1")[0]
    ok, msg = atendimentos.cancelar(ida, "sala1", "Paciente não compareceu / não internou")
    assert ok, msg
    assert atendimentos.buscar(ida)["status"] == "cancelado"
    assert solicitacoes.situacao(ida)["cancelada_em"]

    assert atendimentos.descancelar(ida, "sala1", "oops")[0] is False, "motivo curto é recusado"

    ok, msg = atendimentos.descancelar(ida, "sala1", "cancelei o paciente errado")
    assert ok, msg
    at = atendimentos.buscar(ida)
    assert at["status"] == "aberto" and not at["cancelado_em"] and not at["motivo_cancelamento"]
    assert not solicitacoes.situacao(ida)["cancelada_em"], "a solicitação volta a valer"
    assert db.escalar("""SELECT COUNT(*) FROM eventos WHERE id_atendimento = ?
                         AND tipo = 'atendimento_descancelado'""", (ida,)) == 1


def test_descancelar_so_vale_para_cancelado(client):
    ida = _atendimento()
    ok, msg = atendimentos.descancelar(ida, "sala1", "quero abrir de novo")
    assert not ok and "não está cancelado" in msg


def test_descancelar_pela_tela(client, admin_headers):
    ida = _atendimento()
    assert atendimentos.cancelar(ida, "sala1", "Paciente não compareceu / não internou")[0]
    r = client.post(f"/api/sala-procedimento/atendimento/{ida}/descancelar",
                    data={"motivo": "cancelado por engano"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert atendimentos.buscar(ida)["status"] == "aberto"
