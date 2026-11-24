# tests/test_v18_5_robo_servidor.py
"""v18.5: robô do AGHU no servidor, conduzido pela página (tela simulada do AGHU)."""
import time
from pathlib import Path

import pytest

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import aghu_remoto, aghu_robo

CHAVE = "26261112345678000199550010000015131000015139"
MOCK = Path(__file__).parent / "fixtures" / "aghu_mock" / "login.html"

pytest.importorskip("playwright")


def _nf(client, h):
    db.executar("INSERT OR IGNORE INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                (CHAVE, "1513", "F", db.agora()))
    db.executar("""INSERT OR IGNORE INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total, qtd_pendente, criado_em)
                   VALUES ('ITW1', ?, 'CATETER', '7890000001513', 'LW1', '2030-01-31', 550, 2, 2, ?)""", (CHAVE, db.agora()))
    r = client.post(f"/api/almoxarifado/nf/{CHAVE}/receber", headers=h,
                    data={"id_item": "ITW1", "quantidade": "2", "codigo_aghu": "20843", "marca_fabricante": "SMT"})
    assert r.status_code == 200


def _esperar(client, h, sid, cond, segundos=60):
    fim = time.time() + segundos
    linhas = []
    while time.time() < fim:
        e = client.get(f"/api/almoxarifado/robo-web/{sid}/estado", headers=h).json()
        linhas += e.get("log", [])
        if cond(e):
            return e, linhas
        time.sleep(0.2)
    raise AssertionError(f"tempo esgotado; último estado: {e}\nlog: {linhas[-15:]}")


def _pergunta(trecho):
    return lambda e: e["status"] == "sua_vez" and trecho in (e.get("pergunta") or {}).get("texto", "")


def test_lancamento_pela_pagina(client, admin_headers, monkeypatch):
    h = admin_headers
    monkeypatch.setenv("AGHU_URL", MOCK.as_uri())
    monkeypatch.setenv("AGHU_NAVEGADOR_SERVIDOR", "")
    _nf(client, h)
    tela = client.get(f"/api/almoxarifado/nf/{CHAVE}/aghu/web", headers=h).json()
    assert tela["tela"] == "almoxarifado/aghu_web.html" and tela["dados"]["linhas"] == 1
    r = client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/web/iniciar", headers=h,
                    json={"largura": 1600, "altura": 820}).json()
    assert r["ok"], r
    sid = r["sessao"]
    assert aghu_robo.situacao(CHAVE)["status"] == "em_lancamento"
    # segunda pessoa não abre outro robô na mesma NF; a mesma pessoa continua o dela
    assert client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/web/iniciar", headers=h).json()["sessao"] == sid

    e, log = _esperar(client, h, sid, _pergunta("Lançar estes itens"))
    assert any("NF 1513" in l for l in log)
    client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": "S"})

    e, log = _esperar(client, h, sid, _pergunta("faça o login"))
    assert client.get(f"/api/almoxarifado/robo-web/{sid}/tela", headers=h).headers["content-type"] == "image/jpeg"
    assert e["largura"] == 1600 and e["altura"] == 820
    # v18.5.1: tela em fluxo contínuo — primeiro quadro é um JPEG com o tamanho na frente
    sess = aghu_remoto.buscar(sid, "admin")
    gerador = sess.fluxo()
    bloco = next(gerador)
    n = int.from_bytes(bloco[:4], "big")
    assert n > 1000 and bloco[4:6] == b"\xff\xd8" and len(bloco) == 4 + n
    gerador.close()
    assert sess._transmitindo, "screencast não ligou"
    # a pessoa faz o login digitando na tela (o campo usuário tem foco)
    ev = [{"t": "texto", "v": "camila"}, {"t": "tecla", "k": "Tab"}, {"t": "texto", "v": "SenhaSecreta#1"},
          {"t": "tecla", "k": "Enter"}]
    assert client.post(f"/api/almoxarifado/robo-web/{sid}/entrada", headers=h, json={"eventos": ev}).json()["aceitos"] == 4
    time.sleep(1.5)
    client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": ""})
    _esperar(client, h, sid, lambda e: "faça o login" not in ((e.get("pergunta") or {}).get("texto", "")))

    # valor da NF simulada (1.100,00) ≠ planilha (2 × 550,00 = 1.100,00)? se perguntar, segue
    def proxima(e):
        return e["status"] == "sua_vez" or not e["ativo"]
    for _ in range(6):
        e, log2 = _esperar(client, h, sid, proxima)
        log += log2
        txt = (e.get("pergunta") or {}).get("texto", "")
        if not e["ativo"]:
            break
        if "GRAVE a nota" in txt:
            client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": ""})
            _esperar(client, h, sid, lambda e: "GRAVE a nota" not in ((e.get("pergunta") or {}).get("texto", "")))
        elif "foi GRAVADA" in txt:
            client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": "S"})
            _esperar(client, h, sid, lambda e: "foi GRAVADA" not in ((e.get("pergunta") or {}).get("texto", "")))
        elif "Número da nota" in txt:
            client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": "NR-9"})
        elif "Continuar assim mesmo" in txt:
            client.post(f"/api/almoxarifado/robo-web/{sid}/responder", headers=h, json={"resposta": "S"})
        elif "faça o login" in txt:
            pass
        else:
            raise AssertionError(f"pergunta inesperada: {txt}\n{log[-20:]}")
        time.sleep(0.3)
    e, log2 = _esperar(client, h, sid, lambda e: not e["ativo"])
    log += log2
    assert e["status"] == "concluido", (e, log[-20:])
    assert any("Material 20843" in l for l in log) and any("lote LW1" in l for l in log), log
    s = aghu_robo.situacao(CHAVE)
    assert s["status"] == "lancada" and s["nr"] == "NR-9"
    # o que foi digitado na tela do AGHU não aparece em lugar nenhum
    assert not any("SenhaSecreta" in l for l in log)
    sess = aghu_remoto.buscar(sid, "admin")
    assert not any("SenhaSecreta" in l for l in sess.log)
    # outra pessoa não acessa a sessão
    assert aghu_remoto.buscar(sid, "outra.pessoa") is None


def test_digitacao_nao_vai_para_auditoria_nem_log(client, admin_headers):
    """Roda depois do lançamento: nada do que foi digitado na tela do AGHU ficou gravado."""
    import os
    import sqlite3
    caminho = os.environ["APP_DB_URL"].split(":///", 1)[1]
    con = sqlite3.connect(caminho)
    tabelas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tabelas:
        for linha in con.execute(f"SELECT * FROM {t}"):
            assert "SenhaSecreta" not in " ".join(str(c) for c in linha), t
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE COALESCE(observacao,'') LIKE '%SenhaSecreta%'") == 0
    pasta = os.environ["OPME_LOG_DIR"]
    for raiz, _d, arqs in os.walk(pasta):
        for a in arqs:
            assert "SenhaSecreta" not in open(os.path.join(raiz, a), encoding="utf-8", errors="ignore").read()
