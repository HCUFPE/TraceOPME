# tests/test_selecao_por_nome.py
"""Seleção manual (sem bipar) também acha pelo nome do material (nov/2026)."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo


def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


def _cad(aghu, nome, lote):
    ok, m = estoque.cadastrar_manual({"xProd": nome, "codigo_barras": f"789{aghu}{lote}", "codigo_aghu": aghu,
                                      "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
                                      "quantidade": "2", "tipo_entrada": "aquisicao_propria"}, "admin",
                                     farmacia="BLOCO CIRURGICO")
    assert ok, m


def test_busca_por_codigo_e_por_nome(client):
    _cad("71001", "PARAFUSO CORTICAL 3.5MM", "PN1")
    _cad("71002", "PARAFUSO ESPONJOSO 6.5MM", "PN2")
    _cad("71003", "PLACA BLOQUEADA", "PN3")
    sel = lambda t: {g["aghu"] for g in fluxo.selecao_manual("dispensar_sala", t, farmacia="BLOCO CIRURGICO")}  # noqa: E731
    assert sel("71001") == {"71001"}
    assert sel("parafuso") == {"71001", "71002"}
    assert sel("parafuso cortical") == {"71001"}
    assert sel("pa") == set()


def test_nao_cadastrado_pesquisa_pelo_nome(client, admin_headers):
    _cad("72001", "PLACA DE TITÂNIO 4 FUROS", "PT1")
    r = client.get("/api/sala-procedimento/nao-cadastrado/buscar?q=placa tit", headers=admin_headers).json()
    assert any(i["codigo_aghu"] == "72001" and i["fornecedor"] == "F" for i in r["itens"])
    assert client.get("/api/sala-procedimento/nao-cadastrado/buscar?q=pl", headers=admin_headers).json()["itens"] == []


def test_nao_cadastrado_com_foto_da_etiqueta(client, admin_headers):
    import base64
    from src.providers.implementations.opme import db
    from src.providers.implementations.opme.services import atendimentos, nao_cadastrados
    ok, _ = _abrir_at({"prontuario": "778899", "unidade": "BLOCO CIRURGICO", "sala": "01",
                                "especialidade": "ORTOPEDIA", "data_procedimento": "2031-12-01"}, "admin")
    at = db.consultar_um("SELECT id_atendimento FROM atendimentos WHERE prontuario = '778899'")
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    dados = {"xProd": "PLACA X", "nLote": "LF1", "dVal": "2031-01-01", "fornecedor": "F", "motivo": "Outro",
             "detalhe": "teste de foto", "quantidade": "1", "usuario_supervisao": "admin", "senha_supervisao": "admin",
             "foto_etiqueta": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}
    ok, msg = nao_cadastrados.registrar(at["id_atendimento"], dados, {"username": "admin", "nome": "Admin"})
    assert ok, msg
    reg = db.consultar_um("SELECT foto, etiqueta_no_prontuario FROM nao_cadastrados WHERE id_atendimento = ?", (at["id_atendimento"],))
    assert reg["foto"] and reg["etiqueta_no_prontuario"] == 0
    r = client.get(f"/api/sala-procedimento/nao-cadastrado/foto/{reg['foto']}", headers=admin_headers)
    assert r.status_code == 200 and r.content == jpeg
    assert client.get("/api/sala-procedimento/nao-cadastrado/foto/..%2Fopme.db", headers=admin_headers).status_code == 404
    sem = dict(dados, foto_etiqueta="", detalhe="sem foto nem etiqueta")
    ok, msg = nao_cadastrados.registrar(at["id_atendimento"], sem, {"username": "admin", "nome": "Admin"})
    assert not ok and "foto" in msg


def test_nao_cadastrado_so_com_lote_e_validade(client, admin_headers):
    from src.providers.implementations.opme import db
    from src.providers.implementations.opme.services import atendimentos, nao_cadastrados
    _abrir_at({"prontuario": "778800", "unidade": "BLOCO CIRURGICO", "sala": "02",
                        "especialidade": "ORTOPEDIA", "data_procedimento": "2031-12-02"}, "admin")
    at = db.consultar_um("SELECT id_atendimento FROM atendimentos WHERE prontuario = '778800'")
    ok, msg = nao_cadastrados.registrar(at["id_atendimento"], {
        "nLote": "LSO", "dVal": "2031-01-01", "motivo": "Urgência / emergência", "quantidade": "1",
        "etiqueta_no_prontuario": "1", "usuario_supervisao": "admin", "senha_supervisao": "admin"},
        {"username": "admin", "nome": "Admin"})
    assert ok, msg
    reg = db.consultar_um("SELECT n.id, u.xProd, u.fornecedor FROM nao_cadastrados n JOIN unidades u USING(id_unidade) "
                          "WHERE u.nLote = 'LSO'")
    assert reg["xProd"] == nao_cadastrados.SEM_IDENTIFICACAO and reg["fornecedor"] == "NÃO INFORMADO"
    ok, msg = nao_cadastrados.regularizar(reg["id"], {"codigo_aghu": "99999"}, "admin")
    assert not ok and "descrição" in msg
    ok, msg = nao_cadastrados.regularizar(reg["id"], {"codigo_aghu": "99999", "xProd": "PLACA Y", "fornecedor": "ORTO"}, "admin")
    assert ok, msg
    u = db.consultar_um("SELECT xProd, fornecedor FROM unidades WHERE nLote = 'LSO'")
    assert u["xProd"] == "PLACA Y" and u["fornecedor"] == "ORTO"


def test_planilha_aghu_tem_nf_serie_e_valores(client):
    import io
    import openpyxl
    from src.providers.implementations.opme import db
    from src.providers.implementations.opme.services import estoque, planilha_aghu
    chave = "26261112345678000199550010000012341000012345"
    db.executar("INSERT INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                (chave, "1234", "F", db.agora()))
    db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total, qtd_pendente, criado_em)
                   VALUES ('ITP1', ?, 'PLACA', '7890000000017', 'LP1', '2030-01-31', 250.5, 2, 2, ?)""", (chave, db.agora()))
    ok, msg = estoque.dar_entrada_item_nf({"id_item": "ITP1", "quantidade": "2", "codigo_aghu": "55555",
                                           "marca_fabricante": "SMT"}, "almox")
    assert ok, msg
    assert planilha_aghu.serie_da_chave(chave) == "1"
    conteudo, _ = planilha_aghu.xlsx(chave)
    ws = openpyxl.load_workbook(io.BytesIO(conteudo)).active
    assert [c.value for c in ws[1]] == planilha_aghu.COLUNAS
    linha = [c.value for c in ws[2]]
    assert linha[8:] == ["1234", "1", 250.5, 501.0]  # v18: + coluna "Código master"
