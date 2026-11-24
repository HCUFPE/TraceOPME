# tests/test_v18_35_conferencia_continua.py
"""v18.35: a conferência do recebimento não se perde se a farmácia parar no meio.

Pedido da Camila (18/11/2026): "recebi um pedido do almoxarifado; quando estou
conferindo, se eu precisar parar, perco o que já conferi e preciso conferir do
zero". O que já tinha sido bipado vivia só na tela.

Agora cada bipe é gravado na hora (`remessa_itens.conferido_em`), a tela volta
de onde parou — inclusive em outro computador ou com outra pessoa — e a ciência
usa o que está guardado, não o que a página tem na memória.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO
from src.providers.implementations.opme.services import estoque, remessas

FARM = "BLOCO CIRURGICO"
ADMIN = {"username": "admin", "nome": "Administrador", "papel": "admin"}
_n = [0]


def _remessa_com(itens=3):
    """Cadastra N unidades no almoxarifado e envia para a farmácia."""
    _n[0] += 1
    codigos = []
    for k in range(itens):
        cod, lote = f"78995{_n[0]:04d}{k:04d}", f"RCB{_n[0]}{k}"
        ok, m = estoque.cadastrar_manual({
            "xProd": f"MATERIAL RCB {_n[0]}{k}", "codigo_barras": cod, "codigo_aghu": "90200",
            "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
            "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
        assert ok, m
        codigos.append(cod)
    ok, id_r = remessas.abrir(FARM, "admin")
    assert ok, id_r
    for cod in codigos:
        r = remessas.bipar(id_r, cod, "admin")
        assert r["ok"], r
    ok, msg = remessas.finalizar_envio(id_r, "admin")
    assert ok, msg
    return id_r, codigos


def _pendentes(id_r):
    return [str(i["id_item"]) for i in remessas.buscar(id_r)["pendentes"]]


def test_o_bipe_parcial_fica_guardado(client):
    id_r, _cods = _remessa_com(3)
    itens = _pendentes(id_r)
    ok, dados = remessas.marcar_conferido(id_r, [itens[0]], ADMIN)
    assert ok, dados
    assert remessas.conferidos(id_r) == [itens[0]]
    # "fechou a tela" e voltou: continua lá
    assert remessas.conferidos(id_r) == [itens[0]]
    ok, _ = remessas.marcar_conferido(id_r, [itens[1]], ADMIN)
    assert ok
    assert set(remessas.conferidos(id_r)) == {itens[0], itens[1]}


def test_desbipar_tira_da_conferencia(client):
    id_r, _cods = _remessa_com(2)
    itens = _pendentes(id_r)
    remessas.marcar_conferido(id_r, itens, ADMIN)
    assert len(remessas.conferidos(id_r)) == 2
    remessas.marcar_conferido(id_r, [itens[0]], ADMIN, marcar=False)
    assert remessas.conferidos(id_r) == [itens[1]]


def test_a_tela_volta_de_onde_parou(client, admin_headers):
    id_r, _cods = _remessa_com(3)
    itens = _pendentes(id_r)
    r = client.post(f"/api/farmacia/recebimento/{id_r}/conferido",
                    data={"id_item": [itens[0], itens[1]], "marcar": "1"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["ok"] is True

    tela = client.get(f"/api/farmacia/recebimento/{id_r}", headers=admin_headers)
    assert tela.status_code == 200
    assert set(tela.json()["dados"]["conferidos"]) == {itens[0], itens[1]}
    assert "marcar" in tela.json()["dados"]["rotas"]


def test_a_ciencia_usa_o_que_esta_guardado(client, admin_headers):
    """Mesmo que a página esteja velha, vale o que foi bipado de verdade."""
    id_r, _cods = _remessa_com(3)
    itens = _pendentes(id_r)
    remessas.marcar_conferido(id_r, [itens[0], itens[1]], ADMIN)
    # a página manda uma lista desatualizada (só o primeiro)
    r = client.post(f"/api/farmacia/recebimento/{id_r}/conferir",
                    data={"modo": "bipando", "bipado": itens[0]}, headers=admin_headers)
    assert r.status_code == 200
    por_item = {str(i["id_item"]): i["situacao"] for i in remessas.buscar(id_r)["itens"]}
    assert por_item[itens[0]] == "recebido" and por_item[itens[1]] == "recebido"
    assert por_item[itens[2]] == "nao_recebido"


def test_depois_da_ciencia_a_conferencia_e_zerada(client):
    id_r, _cods = _remessa_com(2)
    itens = _pendentes(id_r)
    remessas.marcar_conferido(id_r, itens, ADMIN)
    ok, msg = remessas.conferir(id_r, set(itens), ADMIN, "bipando")
    assert ok, msg
    assert remessas.conferidos(id_r) == []
    for lote_item in itens:
        pass
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE status = ?", (EM_ESTOQUE_FARMACIA,)) >= 2


def test_nao_aceita_item_de_outra_remessa(client):
    id_a, _ = _remessa_com(2)
    id_b, _ = _remessa_com(2)
    de_b = _pendentes(id_b)
    ok, dados = remessas.marcar_conferido(id_a, de_b, ADMIN)
    assert not ok and "não encontrado" in dados["mensagem"]
    assert remessas.conferidos(id_a) == []


def test_remessa_ja_conferida_nao_aceita_mais_bipe(client):
    id_r, _cods = _remessa_com(2)
    itens = _pendentes(id_r)
    assert remessas.conferir(id_r, set(itens), ADMIN, "bipando")[0]
    ok, dados = remessas.marcar_conferido(id_r, itens, ADMIN)
    assert not ok and "aguardando conferência" in dados["mensagem"]


def test_unidades_so_entram_no_estoque_na_ciencia(client):
    """Bipar na conferência não movimenta o material — só a ciência movimenta."""
    id_r, _cods = _remessa_com(2)
    itens = _pendentes(id_r)
    id_unidade = db.escalar("SELECT id_unidade FROM remessa_itens WHERE id_item = ?", (itens[0],))
    remessas.marcar_conferido(id_r, [itens[0]], ADMIN)
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (id_unidade,)) \
        not in (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO)
    assert remessas.conferir(id_r, {itens[0], itens[1]}, ADMIN, "bipando")[0]
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?",
                      (id_unidade,)) == EM_ESTOQUE_FARMACIA
