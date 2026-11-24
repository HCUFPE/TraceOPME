# tests/test_aghu_robo.py
"""Lançar a NF no AGHU pelo robô do computador de quem lança (nov/2026)."""
import base64
import io
import json
import zipfile

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import aghu_robo

CHAVE = "26261112345678000199550010000077771000077777"


def _nf():
    db.executar("INSERT OR IGNORE INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                (CHAVE, "7777", "F", db.agora()))
    db.executar("""INSERT OR IGNORE INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total, qtd_pendente, criado_em)
                   VALUES ('ITR1', ?, 'PLACA', '7890000000024', 'LR1', '2030-01-31', 10, 1, 1, ?)""", (CHAVE, db.agora()))


def _bloco(link):
    b = link.split("lancar/", 1)[1]
    return json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))


def test_fluxo_robo_no_pc(client, admin_headers, monkeypatch):
    _nf()
    monkeypatch.setenv("AGHU_URL", "http://aghu.teste/aghu/")
    client.post(f"/api/almoxarifado/nf/{CHAVE}/receber", headers=admin_headers,
                data={"id_item": "ITR1", "quantidade": "1", "codigo_aghu": "44444", "marca_fabricante": "SMT"})
    assert [n["chave_nf"] for n in aghu_robo.a_lancar()] == [CHAVE]
    d = client.get(f"/api/almoxarifado/nf/{CHAVE}", headers=admin_headers).json()["dados"]
    assert d["aghu"]["entrada_concluida"] and d["aghu"]["status"] == "" and d["aghu"]["instalador_disponivel"]
    r = client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/lancar", headers=admin_headers,
                    json={"servidor": "http://10.1.2.3:8000/"}).json()
    assert r["ok"] and r["link"].startswith("traceopme-aghu://lancar/") and "&" not in r["link"]
    dados = _bloco(r["link"])
    assert dados["s"] == "http://10.1.2.3:8000" and dados["c"] == CHAVE and dados["a"] == "http://aghu.teste/aghu/"
    token = dados["t"]
    assert aghu_robo.situacao(CHAVE)["status"] == "em_lancamento"
    # o robô baixa a planilha com o código
    p = client.get("/api/robo-aghu/planilha", params={"chave": CHAVE, "token": token})
    assert p.status_code == 200 and p.content[:2] == b"PK"
    assert client.get("/api/robo-aghu/planilha", params={"chave": CHAVE, "token": "x"}).status_code == 403
    assert client.post("/api/robo-aghu/retorno", json={"chave": CHAVE, "token": "errado", "gravou": True}).status_code == 400
    r = client.post("/api/robo-aghu/retorno", json={"chave": CHAVE, "token": token, "gravou": True, "numero_nr": "NR-55"})
    assert r.status_code == 200, r.text
    s = aghu_robo.situacao(CHAVE)
    assert s["status"] == "lancada" and s["nr"] == "NR-55" and s["lancada_por"] == "admin"
    assert aghu_robo.a_lancar() == []
    # o código vale uma vez
    assert client.post("/api/robo-aghu/retorno", json={"chave": CHAVE, "token": token, "gravou": False}).status_code == 400
    assert client.get("/api/robo-aghu/planilha", params={"chave": CHAVE, "token": token}).status_code == 403
    client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/marcar", headers=admin_headers, data={"acao": "desfazer"})
    assert aghu_robo.situacao(CHAVE)["status"] == ""
    client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/marcar", headers=admin_headers, data={"acao": "lancada", "numero_nr": "123"})
    assert aghu_robo.situacao(CHAVE)["status"] == "lancada"
    assert client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/lancar", headers=admin_headers,
                       json={"servidor": "http://x"}).json()["ok"] is False


def test_instalador(client, admin_headers):
    r = client.get("/api/almoxarifado/robo-aghu/instalador", headers=admin_headers)
    nomes = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert {"robo_nota_aghu/robo_nota_aghu.py", "robo_nota_aghu/instalar.bat",
            "robo_nota_aghu/abrir_pelo_traceopme.bat", "robo_nota_aghu/instalar.py"} <= set(nomes)


def test_clicar_duas_vezes_nao_invalida_o_robo_aberto(client, admin_headers):
    """v18.7.2: o segundo clique reaproveita o código — o robô aberto pelo primeiro continua valendo."""
    client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/marcar", headers=admin_headers, data={"acao": "desfazer"})
    r1 = client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/lancar", headers=admin_headers, json={"servidor": "http://x"}).json()
    r2 = client.post(f"/api/almoxarifado/nf/{CHAVE}/aghu/lancar", headers=admin_headers, json={"servidor": "http://x"}).json()
    t1, t2 = _bloco(r1["link"])["t"], _bloco(r2["link"])["t"]
    assert t1 == t2
    assert client.get("/api/robo-aghu/planilha", params={"chave": CHAVE, "token": t1}).status_code == 200
    # código recusado: o robô recebe o motivo em JSON
    r = client.get("/api/robo-aghu/planilha", params={"chave": CHAVE, "token": "errado"})
    assert r.status_code == 403 and "inválido" in r.json()["mensagem"]
