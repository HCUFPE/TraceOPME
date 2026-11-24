# tests/test_v18_4_concorrencia.py
"""v18.4.1: cliques simultâneos não duplicam; lote em recall não vai para a farmácia.

Os testes forçam a corrida: as duas chamadas leem o estado ANTES de qualquer
uma gravar (uma barreira segura as duas depois da leitura)."""
import threading

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque, fechamento,
                                                         recall, remessas)
from src.providers.implementations.opme.utils import hoje_iso

def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


ADM = {"username": "admin", "nome": "Admin", "papel": "admin"}


def _cad(cod, lote, qtd=1):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": cod[-4:],
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
                                      "quantidade": str(qtd), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


def _em_paralelo(funcao, n=2):
    resultados = []
    ts = [threading.Thread(target=lambda: resultados.append(funcao())) for _ in range(n)]
    [t.start() for t in ts]
    [t.join(20) for t in ts]
    return resultados


def test_duas_bipagens_da_mesma_unidade_na_remessa(client, monkeypatch):
    _cad("7899990001111", "LCONC")
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    barreira = threading.Barrier(2, timeout=10)
    original = remessas.gs1.filtrar

    def filtrar_e_esperar(*a, **k):
        r = original(*a, **k)
        try:
            barreira.wait()
        except threading.BrokenBarrierError:
            pass
        return r
    monkeypatch.setattr(remessas.gs1, "filtrar", filtrar_e_esperar)
    res = _em_paralelo(lambda: remessas.bipar(id_r, "7899990001111", "admin"))
    assert sum(1 for r in res if r.get("ok")) == 1, res
    uid = db.escalar("SELECT id_unidade FROM unidades WHERE codigo_barras='7899990001111'")
    assert db.escalar("SELECT COUNT(*) FROM remessa_itens WHERE id_unidade=?", (uid,)) == 1
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE id_unidade=? AND tipo='enviar_farmacia'", (uid,)) == 1


def test_duas_finalizacoes_simultaneas(client, monkeypatch):
    _cad("7899990002222", "LFIN", 2)
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7899990002222'")
    ok, a = _abrir_at({"prontuario": "990001", "unidade": "BLOCO CIRURGICO", "sala": "07",
                                "especialidade": "X", "data_procedimento": hoje_iso()}, "admin")
    for _ in range(2):
        assert dispensacoes.bipar(codigo="7899990002222", id_atendimento=a, usuario="admin", farmacia="BLOCO CIRURGICO")["ok"]
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a,))["id_dispensacao"]
    assert dispensacoes.confirmar(id_dispensacao=d, logado=ADM)[0]
    barreira = threading.Barrier(2, timeout=10)
    original = fechamento.sobras

    def sobras_e_esperar(*a_, **k):
        r = original(*a_, **k)
        try:
            barreira.wait()
        except threading.BrokenBarrierError:
            pass
        return r
    monkeypatch.setattr(fechamento, "sobras", sobras_e_esperar)
    res = _em_paralelo(lambda: fechamento.finalizar_uso(a, ADM))
    assert sum(1 for r in res if r[0]) == 1, res
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE id_atendimento=? AND tipo='uso_finalizado'", (a,)) == 1
    dup = db.escalar("""SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM devolucao_itens i JOIN devolucoes d
                        ON d.id_devolucao = i.id_devolucao WHERE d.id_atendimento = ? GROUP BY i.id_unidade)""", (a,))
    assert dup == 1


def test_lote_em_recall_nao_vai_para_a_farmacia(client):
    _cad("7899990003333", "LRECALL")
    ok, msg = recall.bloquear({"nLote": "LRECALL", "motivo": "Recall do fabricante"}, "admin")
    assert ok, msg
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    r = remessas.bipar(id_r, "7899990003333", "admin")
    assert not r["ok"] and "BLOQUEADO" in r["mensagem"]
    assert db.escalar("SELECT status FROM unidades WHERE codigo_barras='7899990003333'") == "em_estoque_recebimento"
    # transferência entre farmácias também trava; devolução ao almoxarifado continua liberada
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7899990003333'")
    ok, id_t = remessas.abrir("BLOCO CIRURGICO", "admin", remessas.TRANSFERENCIA)
    assert not remessas.bipar(id_t, "7899990003333", "admin")["ok"]
    ok, id_d = remessas.abrir("BLOCO CIRURGICO", "admin", remessas.DEVOLUCAO)
    assert remessas.bipar(id_d, "7899990003333", "admin")["ok"]


def test_duas_ciencias_da_mesma_devolucao(client, monkeypatch):
    from src.providers.implementations.opme.services import devolucoes
    _cad("7899990004444", "LDEV", 2)
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7899990004444'")
    ok, a = _abrir_at({"prontuario": "990004", "unidade": "BLOCO CIRURGICO", "sala": "08",
                                "especialidade": "X", "data_procedimento": hoje_iso()}, "admin")
    for _ in range(2):
        assert dispensacoes.bipar(codigo="7899990004444", id_atendimento=a, usuario="admin", farmacia="BLOCO CIRURGICO")["ok"]
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a,))["id_dispensacao"]
    assert dispensacoes.confirmar(id_dispensacao=d, logado=ADM)[0]
    assert fechamento.finalizar_uso(a, ADM)[0]
    dev = db.consultar_um("SELECT id_devolucao FROM devolucoes WHERE id_atendimento=?", (a,))["id_devolucao"]
    barreira = threading.Barrier(2, timeout=10)
    original = devolucoes.itens

    def itens_e_esperar(*a_, **k):
        r = original(*a_, **k)
        if k.get("so_pendentes"):
            try:
                barreira.wait()
            except threading.BrokenBarrierError:
                pass
        return r
    monkeypatch.setattr(devolucoes, "itens", itens_e_esperar)
    res = _em_paralelo(lambda: devolucoes.confirmar(id_devolucao=dev, operador="admin", responsavel=ADM))
    assert sum(1 for r in res if r[0]) == 1, res
    uid = db.escalar("SELECT id_unidade FROM unidades WHERE codigo_barras='7899990004444' LIMIT 1")
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE id_unidade=? AND tipo='devolver_nao_utilizado'", (uid,)) <= 1


def test_vencido_nao_vai_para_a_farmacia(client):
    db.executar("SELECT 1")
    ok, m = estoque.cadastrar_manual({"xProd": "MATERIAL DE TESTE", "codigo_barras": "7899990005555", "codigo_aghu": "5555",
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": "EXPIRED", "dVal": "2031-01-01",
                                      "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET dVal='2020-01-01' WHERE codigo_barras='7899990005555'")
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    r = remessas.bipar(id_r, "7899990005555", "admin")
    assert not r["ok"] and "venceu" in r["mensagem"]
    assert db.escalar("SELECT status FROM unidades WHERE codigo_barras='7899990005555'") == "em_estoque_recebimento"


def test_recall_registrado_entre_conferencia_e_gravacao(client, monkeypatch):
    _cad("7899990006666", "LTOCTOU")
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    original = remessas._gravar_bipagem

    def recall_no_meio(*a, **k):
        assert recall.bloquear({"nLote": "LTOCTOU", "motivo": "Recall no meio"}, "admin")[0]
        return original(*a, **k)
    monkeypatch.setattr(remessas, "_gravar_bipagem", recall_no_meio)
    r = remessas.bipar(id_r, "7899990006666", "admin")
    assert not r["ok"] and "BLOQUEADO" in r["mensagem"]
    assert db.escalar("SELECT status FROM unidades WHERE codigo_barras='7899990006666'") == "em_estoque_recebimento"


def test_backup_inclui_app_db(client, tmp_path, monkeypatch):
    from src.providers.implementations.opme.services import backup
    import sqlite3
    app_db = tmp_path / "app.db"
    sqlite3.connect(app_db).execute("CREATE TABLE t (x)").connection.commit()
    monkeypatch.setenv("APP_DB_URL", f"sqlite+aiosqlite:///{app_db}")
    monkeypatch.setenv("BACKUP_PASTA_EXTERNA", str(tmp_path / "rede"))
    c = backup.copiar(forcar=True)
    app_copia = c.parent / c.name.replace("opme_", "app_", 1)
    assert app_copia.exists()
    assert (tmp_path / "rede" / app_copia.name).exists()
    assert backup.situacao()["app_ultima"]


def test_rotas_de_estorno_e_pendencias_nao_quebram(client, admin_headers):
    r1 = client.post("/api/sala-procedimento/estorno/NAOEXISTE", headers=admin_headers, data={"motivo": "teste"})
    r2 = client.post("/api/bipagem/registrar_uso/pendencias", headers=admin_headers, data={"motivo": "teste"})
    assert r1.status_code < 500 and r2.status_code < 500, (r1.status_code, r1.text[:200], r2.status_code, r2.text[:200])


def test_nao_recebido_fica_aguardando_conferencia(client, admin_headers):
    _cad("7899990007777", "LNR", 3)
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7899990007777'")
    ok, a = _abrir_at({"prontuario": "990007", "unidade": "BLOCO CIRURGICO", "sala": "09",
                                "especialidade": "X", "data_procedimento": hoje_iso()}, "admin")
    atendimentos.abrir_sala(a, "admin")
    for _ in range(3):
        assert dispensacoes.bipar(codigo="7899990007777", id_atendimento=a, usuario="admin", farmacia="BLOCO CIRURGICO")["ok"]
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a,))["id_dispensacao"]
    itens = dispensacoes.itens(d, so_pendentes=True)
    assert dispensacoes.confirmar(id_dispensacao=d, logado=ADM, modo="lista", recebidos=[itens[0]["id_item"]])[0]
    nr = dispensacoes.nao_recebidos("BLOCO CIRURGICO")
    ids = [i["id_unidade"] for i in nr if i["prontuario"] == "990007"]
    assert len(ids) == 2
    assert all(db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (x,)) == "nao_recebido_conferir" for x in ids)
    # não pode ser dispensado de novo enquanto não for conferido
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_barras='7899990007777' AND status='em_estoque_farmacia'") == 0
    assert not dispensacoes.tratar_nao_recebido(ids[0], "extraviado", "admin", farmacia="BLOCO CIRURGICO")[0]  # exige motivo
    assert dispensacoes.tratar_nao_recebido(ids[0], "extraviado", "admin", "procurado na sala e na farmácia", farmacia="BLOCO CIRURGICO")[0]
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (ids[0],)) == "divergencia"
    assert dispensacoes.tratar_nao_recebido(ids[1], "na_sala", "admin", farmacia="BLOCO CIRURGICO")[0]
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (ids[1],)) == "em_sala"
    assert not dispensacoes.tratar_nao_recebido(ids[1], "localizado", "admin", farmacia="BLOCO CIRURGICO")[0]  # já conferido
    tela = client.get("/api/farmacia/nao-recebidos?todas=1", headers=admin_headers)
    assert tela.status_code == 200
