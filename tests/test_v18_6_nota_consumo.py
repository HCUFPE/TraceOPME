# tests/test_v18_6_nota_consumo.py
"""v18.6: Nota de Consumo no AGHU — lista da farmácia e robô no servidor (tela simulada)."""
import time
from pathlib import Path

import pytest

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import aghu_remoto, atendimentos, estoque, nota_consumo

def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


MOCK = Path(__file__).parent / "fixtures" / "aghu_mock" / "login.html"
DATA = "2026-11-09"


def _cad(cod_barras, aghu, lote, qtd):
    ok, m = estoque.cadastrar_manual({"xProd": f"MATERIAL {aghu}", "codigo_barras": cod_barras, "codigo_aghu": aghu,
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
                                      "quantidade": str(qtd), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


def _cenario():
    ok, a = _abrir_at({"prontuario": "2237552", "paciente": "ANA BEATRIZ DA SILVA", "unidade": "HEMODINAMICA - PDT",
                                "sala": "01", "especialidade": "HEMO", "data_procedimento": DATA}, "admin")
    assert ok
    _cad("7899996000001", "401557", "LA", 2)
    _cad("7899996000002", "24870", "LB", 1)
    _cad("7899996000003", "99999", "LC", 1)
    db.executar("UPDATE unidades SET codigo_aghu='' WHERE codigo_barras='7899996000003'")
    db.executar("""UPDATE unidades SET status='utilizado', id_atendimento=?
                   WHERE codigo_barras IN ('7899996000001','7899996000002','7899996000003')""", (a,))
    return a


def test_lista_do_dia_e_itens(client, admin_headers):
    a = _cenario()
    lista = nota_consumo.prontuarios_com_uso(DATA, "HEMODINAMICA - PDT")
    at = next(x for x in lista if x["id_atendimento"] == a)
    assert at["qtd_itens"] == 4 and at["sem_codigo"] == 1 and at["consumo_status"] == ""
    itens = {i["codigo_aghu"]: i for i in nota_consumo.itens(a)}
    assert itens["401557"]["quantidade"] == 2 and itens["24870"]["quantidade"] == 1 and "" in itens
    r = client.get(f"/api/farmacia/nota-consumo?data={DATA}", headers=admin_headers).json()
    assert r["tela"] == "farmacia/nota_consumo.html"
    assert any(x["id_atendimento"] == a and len(x["itens"]) == 3 for x in r["dados"]["atendimentos"])
    tela = client.get(f"/api/farmacia/nota-consumo/{a}/aghu", headers=admin_headers).json()
    assert tela["tela"] == "almoxarifado/aghu_web.html" and tela["dados"]["robo"]["pode_iniciar"]
    # marcar à mão / desfazer
    client.post(f"/api/farmacia/nota-consumo/{a}/marcar", headers=admin_headers, data={"acao": "lancada"})
    assert nota_consumo.atendimento(a)["aghu_consumo_status"] == "lancada"
    assert not aghu_remoto.iniciar_consumo(a, "admin")[0]
    client.post(f"/api/farmacia/nota-consumo/{a}/marcar", headers=admin_headers, data={"acao": "desfazer"})
    assert nota_consumo.atendimento(a)["aghu_consumo_status"] == ""
    assert len(nota_consumo.prontuarios_com_uso(DATA, "HEMODINAMICA - PDT", pendentes=True)) >= 1


def _esperar(client, h, sid, cond, segundos=60):
    fim, linhas = time.time() + segundos, []
    while time.time() < fim:
        e = client.get(f"/api/almoxarifado/robo-web/{sid}/estado", headers=h).json()
        linhas += e.get("log", [])
        if cond(e):
            return e, linhas
        time.sleep(0.2)
    raise AssertionError(f"tempo esgotado: {e}\n{linhas[-15:]}")


def _pergunta(trecho):
    return lambda e: e["status"] == "sua_vez" and trecho in (e.get("pergunta") or {}).get("texto", "")


def _responder(client, h, sid, valor, trecho):
    client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": valor})
    _esperar(client, h, sid, lambda e: trecho not in (e.get("pergunta") or {}).get("texto", ""))


def test_robo_lanca_a_nota_de_consumo(client, admin_headers, monkeypatch):
    pytest.importorskip("playwright")
    h = admin_headers
    monkeypatch.setenv("AGHU_URL", MOCK.as_uri() + "?ir=casca_consumo.html")
    monkeypatch.setenv("AGHU_NAVEGADOR_SERVIDOR", "")
    a = next(x["id_atendimento"] for x in nota_consumo.prontuarios_com_uso(DATA, "HEMODINAMICA - PDT")
             if x["prontuario"] == "2237552")
    r = client.post(f"/api/farmacia/nota-consumo/{a}/aghu/iniciar", headers=h, json={"largura": 1400, "altura": 800}).json()
    assert r["ok"], r
    sid = r["sessao"]
    assert nota_consumo.atendimento(a)["aghu_consumo_status"] == "em_lancamento"
    e, log = _esperar(client, h, sid, _pergunta("Lançar estes materiais"))
    assert any("401557" in l and "qtd   2" in l for l in log), log
    assert any("sem código AGHU" in l for l in log)
    _responder(client, h, sid, "S", "Lançar estes materiais")
    _esperar(client, h, sid, _pergunta("faça o login"))
    ev = [{"t": "texto", "v": "camila"}, {"t": "tecla", "k": "Tab"}, {"t": "texto", "v": "Segredo#2"}, {"t": "tecla", "k": "Enter"}]
    assert client.post(f"/api/almoxarifado/robo-web/{sid}/entrada", headers=h, json={"eventos": ev}).json()["aceitos"] == 4
    time.sleep(1.5)
    _responder(client, h, sid, "", "faça o login")
    e, log2 = _esperar(client, h, sid, _pergunta("GRAVAR"))
    log += log2
    assert any("401557" in l and "adicionado" in l for l in log2) or any("adicionado (qtd 2)" in l for l in log2), log2
    assert any("já estava na lista do AGHU: quantidade preenchida (1)" in l for l in log2), log2
    assert any("Na lista: 2 material(is)" in l for l in log2), log2
    sess = aghu_remoto.buscar(sid, "admin")
    _responder(client, h, sid, "", "GRAVAR")
    _esperar(client, h, sid, _pergunta("foi GRAVADA"))
    client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": "S"})
    e, _ = _esperar(client, h, sid, lambda e: not e["ativo"])
    assert e["status"] == "concluido"
    at = nota_consumo.atendimento(a)
    assert at["aghu_consumo_status"] == "lancada" and at["aghu_consumo_lancado_por"] == "admin"
    assert not any("Segredo#2" in l for l in sess.log)


def test_robo_no_computador_codigo_e_retorno(client, admin_headers, monkeypatch):
    """v18.7: o botão gera o link do robô instalado; o robô busca os materiais e avisa no fim."""
    import base64
    import json
    monkeypatch.setenv("AGHU_URL", "http://aghu.teste/aghu/")
    a = next(x["id_atendimento"] for x in nota_consumo.prontuarios_com_uso(DATA, "HEMODINAMICA - PDT")
             if x["prontuario"] == "2237552")
    nota_consumo.marcar(a, "desfazer", "admin")
    r = client.post(f"/api/farmacia/nota-consumo/{a}/aghu/lancar", headers=admin_headers,
                    json={"servidor": "http://10.1.2.3:8000/"}).json()
    assert r["ok"] and r["link"].startswith("traceopme-aghu://lancar/")
    b = r["link"].split("lancar/", 1)[1]
    dados = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
    assert dados["k"] == "consumo" and dados["c"] == a and dados["s"] == "http://10.1.2.3:8000"
    assert nota_consumo.atendimento(a)["aghu_consumo_status"] == "em_lancamento"
    assert client.get("/api/robo-aghu/consumo", params={"chave": a, "token": "x"}).status_code == 403
    m = client.get("/api/robo-aghu/consumo", params={"chave": a, "token": dados["t"]}).json()
    assert m["ok"] and {i["codigo"]: i["quantidade"] for i in m["itens"]} == {"401557": 2, "24870": 1}
    assert m["atendimento"]["paciente"] == "ANA BEATRIZ DA SILVA" and len(m["atendimento"]["sem_codigo"]) == 1
    r = client.post("/api/robo-aghu/retorno", json={"tipo": "consumo", "chave": a, "token": dados["t"], "gravou": True})
    assert r.status_code == 200, r.text
    at = nota_consumo.atendimento(a)
    assert at["aghu_consumo_status"] == "lancada" and at["aghu_consumo_lancado_por"] == "admin"
    # o código vale uma vez
    assert client.get("/api/robo-aghu/consumo", params={"chave": a, "token": dados["t"]}).status_code == 403
    assert client.get("/api/farmacia/robo-aghu/instalador", headers=admin_headers).content[:2] == b"PK"


def test_rm_lotes_e_situacao_propria(client, admin_headers):
    """v18.8: a RM tem situação própria e o robô recebe os lotes de cada material."""
    import base64
    import json
    a = next(x["id_atendimento"] for x in nota_consumo.prontuarios_com_uso(DATA, "HEMODINAMICA - PDT")
             if x["prontuario"] == "2237552")
    lotes = {i["codigo"]: i for i in nota_consumo.itens_por_lote(a)}
    assert lotes["401557"]["quantidade"] == 2 and lotes["401557"]["lotes"] == [{"lote": "LA", "validade": "01/01/2031", "quantidade": 2}]
    r = client.post(f"/api/farmacia/nota-consumo/{a}/aghu/lancar", headers=admin_headers,
                    json={"servidor": "http://10.1.2.3:8000", "tipo": "rm"}).json()
    assert r["ok"], r
    b = r["link"].split("lancar/", 1)[1]
    dados = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
    assert dados["k"] == "rm"
    at = nota_consumo.atendimento(a)
    assert at["aghu_rm_status"] == "em_lancamento" and at["aghu_consumo_status"] == "lancada"   # independentes
    # o código da RM não serve para a nota de consumo (e vice-versa)
    assert client.get("/api/robo-aghu/consumo", params={"chave": a, "token": dados["t"]}).status_code == 403
    m = client.get("/api/robo-aghu/consumo", params={"chave": a, "token": dados["t"], "tipo": "rm"}).json()
    assert m["ok"] and {i["codigo"]: [l["lote"] for l in i["lotes"]] for i in m["itens"]} == {"401557": ["LA"], "24870": ["LB"]}
    r = client.post("/api/robo-aghu/retorno", json={"tipo": "rm", "chave": a, "token": dados["t"], "gravou": True})
    assert r.status_code == 200, r.text
    assert nota_consumo.atendimento(a)["aghu_rm_status"] == "lancada"
    tela = client.get(f"/api/farmacia/nota-consumo?data={DATA}", headers=admin_headers).json()["dados"]
    x = next(x for x in tela["atendimentos"] if x["id_atendimento"] == a)
    assert x["rm_status"] == "lancada" and x["rm_rotulo"] == "Lançada no AGHU"
    assert next(i for i in x["itens"] if i["codigo_aghu"] == "401557")["lotes_qtd"][0]["lote"] == "LA"
    client.post(f"/api/farmacia/nota-consumo/{a}/marcar", headers=admin_headers, data={"acao": "desfazer", "tipo": "rm"})
    at = nota_consumo.atendimento(a)
    assert at["aghu_rm_status"] == "" and at["aghu_consumo_status"] == "lancada"
