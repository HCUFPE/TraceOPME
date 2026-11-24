# tests/test_v18_38_pedido_depois_de_vinculo.py
"""v18.38: mexer no pedido depois de a farmácia ter vinculado material.

Erro relatado (HC-UFPE, 19/11/2026):
    sqlite3.IntegrityError: FOREIGN KEY constraint failed
    POST /api/sala-procedimento/atendimento/AT-.../solicitacao
    (solicitacoes.py, DELETE FROM solicitacao_itens ...)

A sala pediu OPME, a farmácia atendeu vinculando material de outro código
(`solicitacao_vinculos` aponta para `solicitacao_itens.id_item`), e quando a
sala salvou o formulário de novo o código apagava e recriava TODAS as linhas —
o DELETE batia no vínculo e o banco recusava.

Agora a linha que continua no pedido é atualizada, mantendo o id_item e o
vínculo. Só a linha retirada é apagada, e o vínculo sai antes dela.
"""
import pytest

from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import atendimentos, estoque, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso

FARM = "BLOCO CIRURGICO"
_n = [0]


def _atendimento():
    _n[0] += 1
    ok, ida = atendimentos.abrir({"prontuario": f"66{_n[0]:05d}", "unidade": FARM,
                                  "sala": str(700 + _n[0]), "especialidade": "ORTOPEDIA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


def _formulario_com_duas_linhas():
    """Usa o primeiro formulário que tenha pelo menos duas linhas."""
    for chave, form in solicitacoes.FORMULARIOS.items():
        linhas = solicitacoes.linhas(chave)
        if len(linhas) >= 2:
            return chave, linhas
    pytest.skip("nenhum formulário com duas linhas")


def _unidade_de_outro_codigo(ida):
    """Material bipado para o paciente que não casa com nenhuma linha do pedido."""
    _n[0] += 1
    cod, lote = f"78994{_n[0]:09d}", f"VINC{_n[0]}"
    ok, m = estoque.cadastrar_manual({
        "xProd": "MATERIAL DE OUTRO CODIGO", "codigo_barras": cod, "codigo_aghu": f"8880{_n[0]}",
        "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
        "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, FARM, lote))
    from src.providers.implementations.opme.services import fluxo
    r = fluxo.bipar(operacao="dispensar_sala", codigo=cod, usuario="farm1",
                    id_atendimento=ida, farmacia=FARM)
    assert r["ok"], r.get("mensagem")
    return db.escalar("SELECT id_unidade FROM unidades WHERE nLote = ?", (lote,))


def _cenario():
    """Pedido com 2 linhas e a farmácia vinculando material na primeira."""
    ida = _atendimento()
    chave, linhas = _formulario_com_duas_linhas()
    l1, l2 = linhas[0], linhas[1]
    ok, msg = solicitacoes.salvar_formulario(ida, chave, {str(l1["linha"]): 1, str(l2["linha"]): 1},
                                  {}, "sala1")
    assert ok, msg
    item = next(l for l in solicitacoes.situacao(ida)["linhas"]
                if l["descricao"] == l1["descricao"])
    ok, msg = solicitacoes.vincular_outro_codigo(
        ida, item["id_item"], [_unidade_de_outro_codigo(ida)],
        "o código AGHU do material mudou", "farm1")
    assert ok, msg
    return ida, chave, l1, l2, item["id_item"]


def test_salvar_de_novo_nao_quebra_a_chave_estrangeira(client):
    ida, chave, l1, l2, id_item = _cenario()
    ok, msg = solicitacoes.salvar_formulario(ida, chave, {str(l1["linha"]): 2, str(l2["linha"]): 1}, {}, "sala1")
    assert ok, msg
    atual = next(l for l in solicitacoes.situacao(ida)["linhas"]
                 if l["descricao"] == l1["descricao"])
    assert atual["id_item"] == id_item, "o id_item tem de ser o mesmo, senão o vínculo se perde"
    assert atual["quantidade"] == 2
    assert db.escalar("SELECT COUNT(*) FROM solicitacao_vinculos WHERE id_item = ?", (id_item,)) == 1


def test_tirar_a_linha_vinculada_apaga_o_vinculo(client):
    ida, chave, l1, l2, id_item = _cenario()
    ok, msg = solicitacoes.salvar_formulario(ida, chave, {str(l1["linha"]): 0, str(l2["linha"]): 1}, {}, "sala1")
    assert ok, msg
    assert db.escalar("SELECT COUNT(*) FROM solicitacao_vinculos WHERE id_item = ?", (id_item,)) == 0
    assert db.escalar("SELECT COUNT(*) FROM solicitacao_itens WHERE id_item = ?", (id_item,)) == 0


def test_cancelar_e_pedir_de_novo_tambem_funciona(client):
    """`_abrir_ou_pegar` limpa os itens do pedido cancelado — e os vínculos."""
    ida, chave, l1, l2, id_item = _cenario()
    assert solicitacoes.cancelar(ida, "sala1", "paciente nao operou")[0]
    ok, msg = solicitacoes.salvar_formulario(ida, chave, {str(l2["linha"]): 1}, {}, "sala1")
    assert ok, msg
    assert db.escalar("SELECT COUNT(*) FROM solicitacao_vinculos WHERE id_item = ?", (id_item,)) == 0


def test_pela_tela(client, admin_headers):
    ida, chave, l1, l2, id_item = _cenario()
    r = client.post(f"/api/sala-procedimento/atendimento/{ida}/solicitacao",
                    data={"formulario": chave, f"qtd_{l1['linha']}": "3",
                          f"qtd_{l2['linha']}": "1"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "FOREIGN KEY" not in r.text
