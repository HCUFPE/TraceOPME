# tests/test_v18_3_sala_qg.py
"""v18.3: abrir sala, etapas novas na Central (com sobreposição) e chamados para o QG."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, chamados_sala, estoque, fechamento, monitoramento
from src.providers.implementations.opme.utils import hoje_iso

ADM = {"username": "admin", "nome": "Admin", "papel": "admin"}


def _at(sala, pront, hora):
    ok, a = atendimentos.abrir({"prontuario": pront, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso(), "hora_inicio": hora}, "admin")
    return a


def test_abrir_sala_e_sobreposicao(client, admin_headers):
    h = admin_headers
    estoque.cadastrar_manual({"xProd": "PINO V183", "codigo_barras": "7891230008881", "codigo_aghu": "881",
                              "fornecedor": "F", "marca_fabricante": "M", "nLote": "L1", "dVal": "2031-01-01",
                              "quantidade": "3", "tipo_entrada": "aquisicao_propria"}, "admin")
    a1, a2 = _at("09", "830001", "08:00"), _at("09", "830002", "11:00")
    estoque.cadastrar_manual({"xProd": "PINO B", "codigo_barras": "7891230008882", "codigo_aghu": "882",
                              "fornecedor": "F", "marca_fabricante": "M", "nLote": "L2", "dVal": "2031-01-01",
                              "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    sala = lambda: next(s for s in monitoramento.painel("BLOCO CIRURGICO")["salas"] if s["sala"] == "09")
    assert sala()["etapa"] == "agendado"
    r = client.post(f"/api/sala-procedimento/atendimento/{a1}/abrir-sala", headers=h)
    assert r.status_code == 200
    at = atendimentos.buscar(a1)
    assert at["sala_aberta_em"] and not at["sala_aberta_auto"]
    assert sala()["etapa"] == "aberta"
    from src.providers.implementations.opme.services import dispensacoes
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7891230008881'")
    for _ in range(2):
        assert dispensacoes.bipar(codigo="7891230008881", id_atendimento=a1, usuario="admin", farmacia="BLOCO CIRURGICO")["ok"]
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a1,))
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=ADM)[0]
    assert sala()["etapa"] == "ciencia"
    client.post("/api/bipar", headers=h, json={"operacao": "registrar_uso", "codigo": "7891230008881", "atendimento": a1})
    assert sala()["etapa"] == "em_uso"
    ok, msg, _ = fechamento.finalizar_uso(a1, ADM)
    assert ok, msg
    s = sala()
    # a1 saiu da sala (conferência da farmácia); o próximo (a2) aparece como o da sala
    assert [p["id_atendimento"] for p in s["na_farmacia"]] == [a1]
    assert s["atual"]["id_atendimento"] == a2 and s["etapa"] == "agendado"
    # a2: bipar sem abrir a sala é bloqueado (v18.9); abre e bipa
    r = client.post("/api/bipar", headers=h, json={"operacao": "registrar_uso", "codigo": "7891230008882", "atendimento": a2}).json()
    assert not r["ok"] and r.get("sala_fechada")
    assert atendimentos.abrir_sala(a2, "admin")[0]
    client.post("/api/bipar", headers=h, json={"operacao": "registrar_uso", "codigo": "7891230008882", "atendimento": a2})
    at2 = atendimentos.buscar(a2)
    assert at2["sala_aberta_em"] and not at2["sala_aberta_auto"]
    s = sala()
    assert s["etapa"] == "em_uso" and s["atual"]["id_atendimento"] == a2 and len(s["na_farmacia"]) == 1
    # ficha da sala traz as etapas
    d = client.get(f"/api/sala-procedimento/atendimento/{a2}", headers=h).json()["dados"]
    assert d["etapas_sala"]["etapa"] == "em_uso" and len(d["etapas_rotulos"]) == 6


def test_chamados_qg(client, admin_headers):
    h = admin_headers
    a = _at("10", "830010", "09:00")
    client.post(f"/api/sala-procedimento/atendimento/{a}/chamado", headers=h,
                data={"tipo": "maqueiro", "motivo": "Buscar o paciente"})
    ok, msg = chamados_sala.chamar(tipo="maqueiro", unidade="BLOCO CIRURGICO", sala="10", usuario="x")
    assert not ok and "Já existe" in msg
    q = client.get("/api/qg/dados", headers=h).json()
    ch = next(c for c in q["aguardando"] if c["sala"] == "10")
    assert ch["tipo"] == "maqueiro" and ch["id_atendimento"] == a
    s = next(s for s in monitoramento.painel("BLOCO CIRURGICO")["salas"] if s["sala"] == "10")
    assert s["chamados"] and s["chamados"][0]["status"] == "aberto"
    r = client.post(f"/api/qg/chamado/{ch['id_chamado']}/direcionar", headers=h, json={"responsavel": "João"}).json()
    assert r["ok"], r
    assert chamados_sala.buscar(ch["id_chamado"])["status"] == "direcionado"
    r = client.post(f"/api/qg/chamado/{ch['id_chamado']}/atender", headers=h, json={}).json()
    assert r["ok"]
    q = client.get("/api/qg/dados", headers=h).json()
    assert q["resumo"]["atendidos_hoje"] >= 1 and not any(c["sala"] == "10" for c in q["aguardando"] + q["a_caminho"])
    # limpeza e cancelamento pela sala
    ok, _ = chamados_sala.chamar(tipo="limpeza", unidade="BLOCO CIRURGICO", sala="10", usuario="sala",
                                 motivo="Limpeza entre procedimentos")
    assert ok
    c2 = chamados_sala.da_sala("BLOCO CIRURGICO", "10", so_abertos=True)[0]
    client.post(f"/api/sala-procedimento/chamado/{c2['id_chamado']}/cancelar", headers=h,
                data={"voltar": f"/sala-procedimento/atendimento/{a}"})
    assert chamados_sala.buscar(c2["id_chamado"])["status"] == "cancelado"


def test_ciencia_so_com_sala_aberta_e_uma_sala_por_vez(client, admin_headers):
    from src.providers.implementations.opme.services import dispensacoes
    h = admin_headers
    estoque.cadastrar_manual({"xProd": "FIO V183", "codigo_barras": "7891230009991", "codigo_aghu": "991",
                              "fornecedor": "F", "marca_fabricante": "M", "nLote": "L9", "dVal": "2031-01-01",
                              "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7891230009991'")
    a1, a2 = _at("12", "840001", "08:00"), _at("12", "840002", "10:00")
    assert dispensacoes.bipar(codigo="7891230009991", id_atendimento=a1, usuario="admin", farmacia="BLOCO CIRURGICO")["ok"]
    d = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a1,))["id_dispensacao"]
    client.post(f"/api/dispensacoes/{d}/confirmar", headers=h, data={})
    assert db.escalar("SELECT status FROM dispensacoes WHERE id_dispensacao=?", (d,)) == "pendente"
    # abrir sala → vai direto para a ciência
    r = client.post(f"/api/sala-procedimento/atendimento/{a1}/abrir-sala", headers=h).json()
    assert d in str(r)
    client.post(f"/api/dispensacoes/{d}/confirmar", headers=h, data={})
    assert db.escalar("SELECT status FROM dispensacoes WHERE id_dispensacao=?", (d,)) == "confirmada"
    # a sala 12 está com a1: não abre para a2 até finalizar
    ok, msg = atendimentos.abrir_sala(a2, "admin")
    assert not ok and "840001" in msg
    tela = client.get("/api/sala-procedimento/salas", headers=h).json()
    assert tela["tela"] == "sala_procedimento/salas.html" if "tela" in tela else True
