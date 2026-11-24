# tests/test_v18_10_robo_rm.py
"""v18.10: robô da RM nas telas simuladas — confere cabeçalho, inclui itens e marca lote + validade."""
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MOCK = RAIZ / "tests" / "fixtures" / "aghu_mock"


@pytest.fixture()
def robo(monkeypatch):
    sys.path.insert(0, str(RAIZ / "ferramentas" / "robo_nota_aghu"))
    mod = importlib.import_module("robo_nota_aghu")
    rm = importlib.import_module("passos_rm")
    perguntas = []

    def perguntar(msg):
        perguntas.append(msg)
        return "S" if "(S/N)" in msg else ""
    monkeypatch.setattr(mod, "perguntar", perguntar)
    yield mod, rm, perguntas
    sys.path.pop(0)


def _abrir(pw, arquivo):
    nav = pw.chromium.launch()
    pag = nav.new_page()
    pag.goto((MOCK / arquivo).as_uri())
    pag.wait_for_timeout(300)
    return nav, pag


def test_rm_inclui_e_marca_lote_com_validade(robo):
    from playwright.sync_api import sync_playwright
    mod, rm, perguntas = robo
    at = {"prontuario": "22375521", "paciente": "ANA BEATRIZ DA SILVA", "data_br": "12/11/2026"}
    itens = [{"codigo": "401557", "quantidade": 2, "descricao": "CATETER",
              "lotes": [{"lote": "GB2411", "validade": "30/11/2030", "quantidade": 1},
                        {"lote": "GB2415", "validade": "30/11/2030", "quantidade": 1}]},
             {"codigo": "24870", "quantidade": 1, "descricao": "INTRODUTOR",
              "lotes": [{"lote": "IF21", "validade": "01/01/2031", "quantidade": 1}]}]
    with sync_playwright() as pw:
        nav, pag = _abrir(pw, "rm_casca.html")
        assert rm.lancar(mod, lambda: pag, at, itens) is True
        f2 = next(f for f in pag.frames if f.query_selector('[id="formControleValidade"]'))
        log = f2.evaluate("JSON.stringify(window.LOG)")
        nav.close()
    # v18.12: quantidade na linha do ITEM; com 2 lotes o robô também preenche lote a lote
    assert '["item","401557","2"]' in log and '["item","24870","1"]' in log
    assert '"GB2411","1"' in log and '"GB2415","1"' in log and '"IF21","1"' in log
    texto = "\n".join(mod.LOG)
    assert "validade no AGHU 30/11/2030, no TraceOPME 01/01/2031" in texto
    assert not any("Falta escolher" in p for p in perguntas)


def test_rm_cobra_cabecalho_escolhido_na_lista(robo):
    from playwright.sync_api import sync_playwright
    mod, rm, perguntas = robo
    with sync_playwright() as pw:
        nav, pag = _abrir(pw, "rm_casca.html")
        f1 = next(f for f in pag.frames if f.query_selector('[id="formItens"]'))
        f1.evaluate('document.getElementById("sbCCReq:sbCCReq:suggestion_hinput").value=""')
        respostas = iter(["", "S"])
        mod.perguntar = lambda msg: (perguntas.append(msg), next(respostas, "S"))[1]
        assert rm.incluir_itens(mod, lambda: pag, {"prontuario": "22375521"}, []) is None
        nav.close()
    assert "Falta escolher NA LISTA: CA Requisição" in "\n".join(mod.LOG)


def test_rm_robo_preenche_cabecalho_e_vincula_atendimento(robo):
    """v18.10.2: tela em branco — o robô vincula o atendimento escolhido e escolhe CC/almox da Hemodinâmica."""
    from playwright.sync_api import sync_playwright
    mod, rm, perguntas = robo
    respostas = iter(["", "2"])   # ENTER (tela aberta) · atendimento nº 2
    mod.perguntar = lambda msg: (perguntas.append(msg), "S" if "(S/N)" in msg else next(respostas, ""))[1]
    at = {"prontuario": "22068662", "paciente": "", "unidade": "HEMODINAMICA"}
    itens = [{"codigo": "24870", "quantidade": 1, "lotes": []}]
    with sync_playwright() as pw:
        nav, pag = _abrir(pw, "rm_casca_vazia.html")
        f1 = next(f for f in pag.frames if f.query_selector('[id="formItens"]'))
        f1.evaluate('fixa("sbCCReq","31011")')   # CA Requisição: a pessoa escolhe à mão
        assert rm.incluir_itens(mod, lambda: pag, at, itens) is True
        f1 = next(f for f in pag.frames if f.query_selector('[id="formItens"]'))
        log = f1.evaluate("JSON.stringify(window.LOG)")
        nav.close()
    assert '["atd","2750001"]' in log
    # CC Aplicação: o vínculo pôs 34309; o robô trocou para 31047 depois
    assert log.index('"34309"') < log.index('"31047"')
    assert log.count('"sbCCReq"') == 1 and '["cab","sbAlmoxarifado","12"]' in log
    assert '["item","24870","1"]' in log


def test_rm_um_lote_so_usa_a_quantidade_do_item(robo):
    """v18.12: com UM lote o AGHU preenche a Quantidade Atendida sozinho — o robô só
    marca o lote e digita a Quantidade Entregue na linha do item."""
    from playwright.sync_api import sync_playwright
    mod, rm, _perguntas = robo
    at = {"prontuario": "22375521", "paciente": "", "data_br": ""}
    itens = [{"codigo": "24870", "quantidade": 3, "descricao": "INTRODUTOR",
              "lotes": [{"lote": "if21", "validade": "30/11/2030", "quantidade": 3}]}]
    with sync_playwright() as pw:
        nav, pag = _abrir(pw, "rm_casca.html")
        rm.marcar_lotes(mod, lambda: pag, itens)
        f2 = next(f for f in pag.frames if f.query_selector('[id="formControleValidade"]'))
        log = f2.evaluate("JSON.stringify(window.LOG)")
        nav.close()
    assert '["item","24870","3"]' in log
    assert log.count('"IF21"') == 1          # não escreve de novo por cima
    assert '"IF21","3"' in log


def test_rm_lote_inexistente_usa_outro_lote(robo):
    """v18.12 (pedido da Camila): lote que não existe no AGHU — o robô marca outro lote
    (com saldo) para a RM não travar e avisa para conferir."""
    from playwright.sync_api import sync_playwright
    mod, rm, _p = robo
    itens = [{"codigo": "401557", "quantidade": 2, "descricao": "CATETER",
              "lotes": [{"lote": "NAOEXISTE9", "validade": "01/01/2031", "quantidade": 2}]}]
    with sync_playwright() as pw:
        nav, pag = _abrir(pw, "rm_casca.html")
        problemas = rm.marcar_lotes(mod, lambda: pag, itens)
        f2 = next(f for f in pag.frames if f.query_selector('[id="formControleValidade"]'))
        log = f2.evaluate("JSON.stringify(window.LOG)")
        nav.close()
    assert '["item","401557","2"]' in log
    assert '"GB2413","2"' in log            # pegou o lote com saldo (6)
    texto = "\n".join(mod.LOG)
    assert "NÃO existe no AGHU" in texto and "Usei o lote GB2413" in texto
    assert any("não existe — usei GB2413" in p for p in problemas)
