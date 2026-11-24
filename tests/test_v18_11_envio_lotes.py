# tests/test_v18_11_envio_lotes.py
"""v18.11: lote sem diferença de maiúscula, lote da etiqueta inexistente e várias unidades por bip."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import estoque, remessas


def _cad(cod, lote, qtd=1, marca="M", val="2031-01-01"):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {cod}", "codigo_barras": cod, "codigo_aghu": "4242",
                                      "fornecedor": "F", "marca_fabricante": marca, "nLote": lote, "dVal": val,
                                      "quantidade": str(qtd), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


def test_lote_guardado_em_maiuscula_e_mesmo_grupo(client):
    _cad("7891110000011", "SP1125031405", 6, marca="APT")
    _cad("7891110000011", "sp1125031405", 1, marca="apt medical")
    assert db.escalar("SELECT COUNT(DISTINCT nLote) FROM unidades WHERE codigo_barras='7891110000011'") == 1
    assert db.escalar("SELECT nLote FROM unidades WHERE codigo_barras='7891110000011' LIMIT 1") == "SP1125031405"
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    r = remessas.bipar(id_r, "7891110000011", "admin")
    assert r["ok"] and not r.get("escolher"), r          # não pede para escolher entre "SP" e "sp"


def test_varias_unidades_num_bip(client):
    _cad("7891110000028", "CX01", 10)
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    r = remessas.bipar(id_r, "7891110000028", "admin", quantidade=6)
    assert r["ok"] and r["quantidade"] == 6
    r = remessas.bipar(id_r, "7891110000028", "admin", quantidade=5)
    assert not r["ok"] and "Só há 4" in r["mensagem"]


def test_lote_da_etiqueta_inexistente_obriga_escolher(client):
    _cad("07891110000035", "LOTEA", 2)
    ok, id_r = remessas.abrir("BLOCO CIRURGICO", "admin")
    r = remessas.bipar(id_r, "0107891110000035" + "10LOTEZZ", "admin")
    assert not r["ok"] and r.get("escolher") and r.get("lote_nao_encontrado"), r
    assert "LOTEZZ" in r["mensagem"]


def test_busca_avisa_lote_nao_encontrado(client, admin_headers):
    _cad("07891110000042", "LOTEB", 1)
    r = client.get("/api/consultas/itens?busca=0107891110000042" + "10LOTEQQ", headers=admin_headers).json()
    assert r["dados"]["lote_nao_encontrado"] == "LOTEQQ"
    r = client.get("/api/consultas/itens?busca=0107891110000042" + "10LOTEB", headers=admin_headers).json()
    assert not r["dados"]["lote_nao_encontrado"]


def test_inventario_varias_unidades_por_bip(client):
    from src.providers.implementations.opme.services import inventario
    _cad("7891110000059", "CXINV", 5)
    ok, _m, idi = inventario.abrir("almoxarifado", "admin")
    assert ok, _m
    r = inventario.bipar(idi, "7891110000059", "admin", quantidade=4)
    assert r["ok"] and r["quantidade"] == 4 and r["por_situacao"] == {"confere": 4}, r
    r = inventario.bipar(idi, "7891110000059", "admin", quantidade=3)
    assert r["por_situacao"] == {"confere": 1, "excedente": 2} and r["pendencia"], r


def test_caixa_consignado_so_com_nome_e_fornecedores_dos_itens(client):
    from src.providers.implementations.opme.services import caixas_consignado
    ok, msg, idc = caixas_consignado.criar({"nome": "CARDIOLOGIA - NID"}, "admin")
    assert ok and idc.startswith("CX-CARD-"), msg
    ok, _m, _ = caixas_consignado.criar({"nome": ""}, "admin")
    assert not ok
    for i, forn in enumerate(("BIOTRONIK", "MEDTRONIC")):
        _cad(f"78911100001{i}5", f"LCX{i}", 1)
        db.executar("UPDATE unidades SET fornecedor = ?, id_caixa = ? WHERE nLote = ?", (forn, idc, f"LCX{i}"))
    c = next(c for c in caixas_consignado.listar(True) if c["id_caixa"] == idc)
    assert c["fornecedores"] == "BIOTRONIK, MEDTRONIC" and not c["fornecedor"]


def test_caixa_nao_coloca_outro_lote_e_retira_sem_motivo(client, admin_headers):
    from src.providers.implementations.opme.services import caixas_almox
    ok, _m, idc = caixas_almox.criar({"nome": "CARDIOLOGIA - TESTE"}, "admin")
    _cad("08904118388741", "S26TZAGQAH", 2)
    r = client.post(f"/api/almoxarifado/caixas/{idc}/adicionar", headers=admin_headers,
                    data={"codigo": "0108904118388741" + "17270831" + "10S25TZAVUAH"}).json()
    assert r["dados"]["lote_nao_encontrado"] == "S25TZAVUAH" and r["dados"]["escolha"], r
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (idc,)) == 0
    # o lote certo entra direto
    client.post(f"/api/almoxarifado/caixas/{idc}/adicionar", headers=admin_headers,
                data={"codigo": "0108904118388741" + "10S26TZAGQAH"})
    idu = db.escalar("SELECT id_unidade FROM unidades WHERE id_caixa = ?", (idc,))
    assert idu
    client.post(f"/api/almoxarifado/caixas/{idc}/retirar/{idu}", headers=admin_headers, data={"motivo": ""})
    assert not db.escalar("SELECT id_caixa FROM unidades WHERE id_unidade = ?", (idu,))


def test_caixa_da_farmacia_so_aceita_estoque_da_farmacia(client):
    from src.providers.implementations.opme.services import caixas, caixas_consignado
    ok, _m, idc = caixas_consignado.criar({"nome": "HEMO TESTE"}, "admin")
    db.executar("UPDATE caixas SET farmacia = 'HEMODINAMICA' WHERE id_caixa = ?", (idc,))
    _cad("7891110000301", "FX1", 2)
    r = caixas.adicionar_item(idc, "7891110000301", "admin")   # ainda no almoxarifado
    assert not r["ok"] and "estoque da farmácia" in r["mensagem"], r
    assert not caixas_consignado.candidatos_para_caixa("7891110000301", farmacia="HEMODINAMICA")
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='HEMODINAMICA' WHERE nLote='FX1'")
    assert len(caixas_consignado.candidatos_para_caixa("7891110000301", farmacia="HEMODINAMICA")) == 1
    assert not caixas_consignado.candidatos_para_caixa("7891110000301", farmacia="BLOCO CIRURGICO")
    assert caixas.adicionar_item(idc, "7891110000301", "admin")["ok"]


def test_consignado_mostra_descricao_do_material(client):
    from src.providers.implementations.opme.services import consignado_aghu
    def cad(lote, xprod):
        return estoque.cadastrar_manual({"xProd": xprod, "codigo_barras": "7891110000400", "codigo_aghu": "401845",
                                         "fornecedor": "SMT", "marca_fabricante": "SMT", "nLote": lote,
                                         "dVal": "2031-01-01", "quantidade": "1", "tipo_entrada": "consignado"}, "admin")
    assert cad("DSC1", "STENT SUPRAFLEX 2,50 X 13MM")[0]
    assert db.escalar("SELECT descritivo_hospital FROM unidades WHERE nLote='DSC1'") == "STENT SUPRAFLEX 2,50 X 13MM"
    consignado_aghu.salvar("401845", "401845", "admin", "SMT", "SUPRAFLEX CRUZ 3,00 X 16MM")
    assert db.escalar("SELECT descritivo_hospital FROM unidades WHERE nLote='DSC1'") == "SUPRAFLEX CRUZ 3,00 X 16MM"
    assert cad("DSC2", "qualquer")[0]
    assert db.escalar("SELECT descritivo_hospital FROM unidades WHERE nLote='DSC2'") == "SUPRAFLEX CRUZ 3,00 X 16MM"


def test_sala_bipa_so_o_item_de_caixa(client):
    from src.providers.implementations.opme.services import atendimentos, caixas, caixas_consignado, fluxo
    from src.providers.implementations.opme.utils import hoje_iso
    ok, _m, idc = caixas_consignado.criar({"nome": "HEMO SALA"}, "admin")
    db.executar("UPDATE caixas SET farmacia = 'BLOCO CIRURGICO' WHERE id_caixa = ?", (idc,))
    _cad("7891110000509", "CXS1", 1)
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE nLote='CXS1'")
    assert caixas.adicionar_item(idc, "7891110000509", "admin")["ok"]
    ok, ida = atendimentos.abrir({"prontuario": "551100", "unidade": "BLOCO CIRURGICO", "sala": "97",
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    db.executar("UPDATE atendimentos SET sala_aberta_em = ? WHERE id_atendimento = ?", (db.agora(), ida))
    r = fluxo.bipar(operacao="registrar_uso", codigo="7891110000509", usuario="admin", id_atendimento=ida)
    assert r["ok"], r
    assert caixas_consignado.esperado(idc) == 0


def test_saidas_da_caixa_em_tela_propria(client, admin_headers):
    from src.providers.implementations.opme.services import caixas, caixas_almox
    ok, _m, idc = caixas_almox.criar({"nome": "VASCULAR SAIDAS"}, "admin")
    _cad("7891110000608", "SAI1", 1)
    idu = caixas.adicionar_item(idc, "7891110000608", "admin")["item"]["id_unidade"]
    caixas.retirar_item(idc, idu, "admin", "")
    r = client.get(f"/api/almoxarifado/caixas/{idc}/saidas", headers=admin_headers).json()
    assert r["tela"] == "farmacia/caixa_saidas.html" and len(r["dados"]["saidas"]) == 1
    r = client.get(f"/api/almoxarifado/caixas/{idc}/saidas?de=2000-01-01&ate=2000-01-31", headers=admin_headers).json()
    assert r["dados"]["saidas"] == []
    r = client.get(f"/api/almoxarifado/caixas/{idc}", headers=admin_headers).json()
    assert "saidas" not in r["dados"]


def test_reposicao_das_caixas(client, admin_headers):
    from src.providers.implementations.opme.services import caixas, caixas_almox, reposicao_caixas
    ok, _m, idc = caixas_almox.criar({"nome": "REPOSICAO T"}, "admin")
    _cad("7891110000707", "REP1", 3)
    db.executar("UPDATE unidades SET codigo_aghu = '777001' WHERE nLote = 'REP1'")
    ids = [caixas.adicionar_item(idc, "7891110000707", "admin")["item"]["id_unidade"] for _ in range(2)]
    db.executar("UPDATE caixa_itens SET saiu_em = ?, saiu_por = 'sala', motivo_saida = 'uso' WHERE id_unidade = ?",
                (db.agora(), ids[0]))
    db.executar("UPDATE unidades SET id_caixa = NULL, status = 'utilizado' WHERE id_unidade = ?", (ids[0],))
    l = next(x for x in reposicao_caixas.a_repor() if x["id_caixa"] == idc)
    assert l["usados"] == 1 and l["faltam"] == 1 and l["no_almoxarifado"] == 1 and l["acao"] == "enviar"
    r = client.get("/api/almoxarifado/reposicao-caixas", headers=admin_headers).json()
    assert r["tela"] == "almoxarifado/reposicao_caixas.html"
    assert any(x["id_caixa"] == idc for x in r["dados"]["linhas"])


def test_caixa_unidades_por_bip(client, admin_headers):
    from src.providers.implementations.opme.services import caixas_almox
    ok, _m, idc = caixas_almox.criar({"nome": "QTD CAIXA"}, "admin")
    _cad("7891110000806", "QB1", 5)
    client.post(f"/api/almoxarifado/caixas/{idc}/adicionar", headers=admin_headers,
                data={"codigo": "7891110000806", "quantidade": "4"})
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (idc,)) == 4
    client.post(f"/api/almoxarifado/caixas/{idc}/adicionar", headers=admin_headers,
                data={"codigo": "7891110000806", "quantidade": "3"})          # só resta 1: não entra nada
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa = ?", (idc,)) == 4


def test_uso_e_dispensacao_nao_trocam_o_lote(client):
    """v18.12: etiqueta com lote que não existe NÃO registra outro lote — pede a escolha."""
    from src.providers.implementations.opme.services import atendimentos, fluxo
    from src.providers.implementations.opme.utils import hoje_iso
    _cad("07891110000905", "LOTECERTO", 2)
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE nLote='LOTECERTO'")
    ok, ida = atendimentos.abrir({"prontuario": "551200", "unidade": "BLOCO CIRURGICO", "sala": "96",
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    db.executar("UPDATE atendimentos SET sala_aberta_em = ? WHERE id_atendimento = ?", (db.agora(), ida))
    errado = "0107891110000905" + "10LOTEERRADO"
    for operacao in ("dispensar_sala", "registrar_uso"):
        r = fluxo.bipar(operacao=operacao, codigo=errado, usuario="admin", id_atendimento=ida, farmacia="BLOCO CIRURGICO")
        assert not r["ok"] and r.get("escolha") and r.get("lote_nao_encontrado") == "LOTEERRADO", (operacao, r)
        assert len(r["opcoes"]) == 1
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote='LOTECERTO' AND status='em_estoque_farmacia'") == 2
    # escolhendo a unidade, registra (com o alerta do lote)
    r = fluxo.bipar(operacao="registrar_uso", codigo=errado, usuario="admin", id_atendimento=ida,
                    farmacia="BLOCO CIRURGICO", id_unidade=r["opcoes"][0]["id_unidade"])
    assert r["ok"], r
    # o lote certo passa direto
    r = fluxo.bipar(operacao="registrar_uso", codigo="0107891110000905" + "10LOTECERTO", usuario="admin",
                    id_atendimento=ida, farmacia="BLOCO CIRURGICO")
    assert r["ok"] and not r.get("escolha"), r


def test_solicitacao_cancelada_nao_fica_para_atender(client, admin_headers):
    """v18.12.2: cancelada — some das pendências da farmácia e não alerta 'não solicitado'."""
    from src.providers.implementations.opme.services import atendimentos, solicitacoes
    from src.providers.implementations.opme.utils import hoje_iso
    ok, ida = atendimentos.abrir({"prontuario": "551300", "unidade": "HEMODINAMICA", "sala": "95",
                                  "especialidade": "CARDIOLOGIA INTERVENCIONISTA",
                                  "data_procedimento": hoje_iso()}, "admin")
    ok, _m = solicitacoes.adicionar_avulso(ida, "", "1", "CATETER X", "kleciane")
    assert ok
    assert any(p["id_atendimento"] == ida for p in solicitacoes.em_aberto())
    ok, msg = solicitacoes.cancelar(ida, "kleciane", "Material não será mais necessário")
    assert ok, msg
    assert not any(p["id_atendimento"] == ida for p in solicitacoes.em_aberto())
    s = solicitacoes.situacao(ida)
    assert s["cancelada_em"] and s["pode_cancelar"] is False
    _cad("7891110001001", "NS1", 1)
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='HEMODINAMICA - PDT' WHERE nLote='NS1'")
    idu = db.escalar("SELECT id_unidade FROM unidades WHERE nLote='NS1'")
    assert solicitacoes.unidade_nao_solicitada(ida, idu) == ""
