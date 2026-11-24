# tests/test_v18_4_5_nao_recebido.py
"""v18.4.5: conferência do "não recebido" pela farmácia.

- "estava na sala" atualiza também o item da dispensação (recebido, com a tratativa
  guardando a divergência inicial);
- depois da finalização do registro de uso, "estava na sala" é recusado e a tratativa
  é "recolhido à farmácia", com o local informado;
- só a farmácia dona do material confere;
- caixa não recebida não volta ao estoque enquanto houver unidade pendente;
- o indicador geral do backup exige a cópia do app.db."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque, fechamento,
                                                         rel_dispensas)
from src.providers.implementations.opme.utils import hoje_iso

def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


ADM = {"username": "admin", "nome": "Admin", "papel": "admin"}
BLOCO, HEMO = "BLOCO CIRURGICO", "HEMODINAMICA - PDT"


def _cad(cod, lote, qtd=1):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": cod[-4:],
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
                                      "quantidade": str(qtd), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia=? WHERE codigo_barras=?", (BLOCO, cod))


def _tres_dispensadas_uma_recebida(cod, pront):
    _cad(cod, "L" + pront, 3)
    ok, a = _abrir_at({"prontuario": pront, "unidade": BLOCO, "sala": "11", "especialidade": "X",
                                "data_procedimento": hoje_iso()}, "admin")
    atendimentos.abrir_sala(a, "admin")
    for _ in range(3):
        assert dispensacoes.bipar(codigo=cod, id_atendimento=a, usuario="admin", farmacia=BLOCO)["ok"]
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a,))["id_dispensacao"]
    itens = dispensacoes.itens(d, so_pendentes=True)
    assert dispensacoes.confirmar(id_dispensacao=d, logado=ADM, modo="lista", recebidos=[itens[0]["id_item"]])[0]
    faltas = [i["id_unidade"] for i in dispensacoes.nao_recebidos(BLOCO) if i["prontuario"] == pront]
    assert len(faltas) == 2
    return a, faltas


def _situacao_item(id_unidade):
    return db.consultar_um("""SELECT situacao, tratativa FROM dispensacao_itens WHERE id_unidade=?
                              ORDER BY id_item DESC LIMIT 1""", (id_unidade,))


def test_na_sala_atualiza_o_item_da_dispensacao(client):
    a, faltas = _tres_dispensadas_uma_recebida("7899995000001", "995001")
    ok, msg = dispensacoes.tratar_nao_recebido(faltas[0], "na_sala", "admin", farmacia=BLOCO)
    assert ok, msg
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (faltas[0],)) == "em_sala"
    it = _situacao_item(faltas[0])
    assert it["situacao"] == "recebido" and it["tratativa"] == "recebido_na_conferencia"
    # a divergência inicial continua registrada
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE id_unidade=? AND tipo='nao_recebido_sala'", (faltas[0],)) == 1
    # os outros desfechos guardam a tratativa sem virar "recebido"
    assert dispensacoes.tratar_nao_recebido(faltas[1], "localizado", "admin", farmacia=BLOCO)[0]
    it2 = _situacao_item(faltas[1])
    assert it2["situacao"] == "nao_recebido" and it2["tratativa"] == "localizado_farmacia"
    # relatório: texto novo, sem "voltou à farmácia"
    linhas = rel_dispensas._dispensacoes(hoje_iso(), hoje_iso(), "", "")
    textos = [l["situacao"] for l in linhas if l["prontuario"] == "995001"]
    assert any("confirmou que estava na sala" in t for t in textos)
    assert any("localizado na farmácia" in t for t in textos)
    assert not any("voltou à farmácia" in t for t in textos)


def test_depois_da_finalizacao_nao_aceita_na_sala(client):
    a, faltas = _tres_dispensadas_uma_recebida("7899995000002", "995002")
    db.executar("UPDATE atendimentos SET uso_finalizado_em=?, uso_finalizado_por='admin' WHERE id_atendimento=?",
                (db.agora(), a))
    ok, msg = dispensacoes.tratar_nao_recebido(faltas[0], "na_sala", "admin", farmacia=BLOCO)
    assert not ok and "finalizou" in msg
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (faltas[0],)) == "nao_recebido_conferir"
    # tratativa específica: exige o local e devolve ao estoque, conciliado
    assert not dispensacoes.tratar_nao_recebido(faltas[0], "recolhido_apos_finalizacao", "admin", farmacia=BLOCO)[0]
    ok, msg = dispensacoes.tratar_nao_recebido(faltas[0], "recolhido_apos_finalizacao", "admin",
                                               "gaveta da sala 11, recolhido por Ana", farmacia=BLOCO)
    assert ok, msg
    u = db.consultar_um("SELECT status, id_atendimento FROM unidades WHERE id_unidade=?", (faltas[0],))
    assert u["status"] == "em_estoque_farmacia" and not u["id_atendimento"]
    assert _situacao_item(faltas[0])["tratativa"] == "recolhido_apos_finalizacao"
    obs = db.escalar("""SELECT observacao FROM eventos WHERE id_unidade=? AND tipo='nao_recebido_conferido'""", (faltas[0],))
    assert "gaveta da sala 11" in obs
    # com o uso ainda aberto, "recolhido após finalização" não se aplica
    a2, f2 = _tres_dispensadas_uma_recebida("7899995000003", "995003")
    assert not dispensacoes.tratar_nao_recebido(f2[0], "recolhido_apos_finalizacao", "admin", "x", farmacia=BLOCO)[0]


def test_so_a_farmacia_dona_confere(client):
    a, faltas = _tres_dispensadas_uma_recebida("7899995000004", "995004")
    ok, msg = dispensacoes.tratar_nao_recebido(faltas[0], "localizado", "admin", farmacia=HEMO)
    assert not ok and "Bloco" in msg
    ok, msg = dispensacoes.tratar_nao_recebido(faltas[0], "localizado", "admin", farmacia="")
    assert not ok and "farmácia" in msg
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade=?", (faltas[0],)) == "nao_recebido_conferir"
    assert dispensacoes.tratar_nao_recebido(faltas[0], "localizado", "admin", farmacia=BLOCO)[0]


def test_caixa_nao_volta_ao_estoque_com_unidade_pendente(client):
    _cad("7899995000005", "LCX5", 2)
    db.executar("""INSERT INTO caixas (id_caixa, nome, especialidade, farmacia, status, criado_em)
                   VALUES ('CX-T5', 'Caixa teste', 'X', ?, 'transito_sala', ?)""", (BLOCO, db.agora()))
    ids = [r["id_unidade"] for r in db.consultar("SELECT id_unidade FROM unidades WHERE codigo_barras='7899995000005'")]
    ok, a = _abrir_at({"prontuario": "995005", "unidade": BLOCO, "sala": "12", "especialidade": "X",
                                "data_procedimento": hoje_iso()}, "admin")
    db.executar("UPDATE unidades SET status='transito_sala', id_caixa='CX-T5', id_atendimento=? WHERE codigo_barras='7899995000005'", (a,))
    disp = {"id_dispensacao": "DTESTE5", "id_atendimento": a}
    db.executar("""INSERT INTO dispensacoes (id_dispensacao, id_atendimento, status, criado_em)
                   VALUES ('DTESTE5', ?, 'pendente', ?)""", (a, db.agora()))
    faltou = []
    for u in ids:
        db.executar("""INSERT INTO dispensacao_itens (id_dispensacao, id_unidade, id_caixa, bipado_por, bipado_em)
                       VALUES ('DTESTE5', ?, 'CX-T5', 'admin', ?)""", (u, db.agora()))
        faltou.append(db.consultar_um("SELECT * FROM dispensacao_itens WHERE id_unidade=?", (u,)))
    dispensacoes._registrar_nao_recebidos(disp, faltou, ADM)
    assert db.escalar("SELECT status FROM caixas WHERE id_caixa='CX-T5'") == "nao_recebido_conferir"
    assert dispensacoes.tratar_nao_recebido(ids[0], "localizado", "admin", farmacia=BLOCO)[0]
    # ainda há unidade pendente: a caixa continua fora do estoque
    assert db.escalar("SELECT status FROM caixas WHERE id_caixa='CX-T5'") == "nao_recebido_conferir"
    assert dispensacoes.tratar_nao_recebido(ids[1], "localizado", "admin", farmacia=BLOCO)[0]
    assert db.escalar("SELECT status FROM caixas WHERE id_caixa='CX-T5'") == "em_estoque_farmacia"


def test_indicador_do_backup_exige_app_db(client, tmp_path, monkeypatch):
    from src.providers.implementations.opme.services import backup
    monkeypatch.setenv("APP_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'nao_existe.db'}")
    monkeypatch.setenv("BACKUP_PASTA_EXTERNA", str(tmp_path / "rede"))
    backup._gravar_situacao(app_ultima="", app_ok=None, app_erro="")
    backup.copiar(forcar=True)
    s = backup.situacao()
    assert s["opme_em_dia"] and s["externo_em_dia"]
    assert not s["app_em_dia"] and "não encontrado" in s["app_erro"]
    assert not s["tudo_certo"] and not s["em_dia"]


def test_aguardando_confirmacao_nao_aparece_como_falta_finalizar(client):
    _cad("7899995000006", "LAF6", 2)
    ok, a = _abrir_at({"prontuario": "995006", "unidade": BLOCO, "sala": "13", "especialidade": "X",
                                "data_procedimento": hoje_iso()}, "admin")
    for _ in range(2):
        assert dispensacoes.bipar(codigo="7899995000006", id_atendimento=a, usuario="admin", farmacia=BLOCO)["ok"]
    assert a not in {x["id_atendimento"] for x in atendimentos.a_concluir(BLOCO)}
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a,))["id_dispensacao"]
    atendimentos.abrir_sala(a, "admin")
    assert dispensacoes.confirmar(id_dispensacao=d, logado=ADM)[0]
    assert a in {x["id_atendimento"] for x in atendimentos.a_concluir(BLOCO)}
