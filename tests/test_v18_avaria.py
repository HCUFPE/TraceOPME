# tests/test_v18_avaria.py
"""v18: sinalizar problema (caiu, danificado) no material registrado no paciente."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import atendimentos, estoque, fluxo
from src.providers.implementations.opme.utils import hoje_iso


def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


def test_avaria_no_bip_e_depois(client, admin_headers):
    estoque.cadastrar_manual({"xProd": "STENT AV", "codigo_barras": "7891230000099", "codigo_aghu": "880",
                              "fornecedor": "F", "marca_fabricante": "M", "nLote": "LAV", "dVal": "2031-01-01",
                              "quantidade": "2", "tipo_entrada": "aquisicao_propria"}, "admin")
    ok, id_at = _abrir_at({"prontuario": "990011", "unidade": "BLOCO CIRURGICO", "sala": "01",
                                    "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, id_at
    r = client.post("/api/bipar", headers=admin_headers, json={
        "operacao": "registrar_uso", "codigo": "7891230000099", "atendimento": id_at,
        "avaria": "Caiu no chão / contaminou", "avaria_detalhe": "caiu ao abrir"}).json()
    assert r["ok"], r
    item = r["uso"]["lista"][0]
    assert item["avaria"]["motivo"] == "Caiu no chão / contaminou" and item["avaria"]["detalhe"] == "caiu ao abrir"
    assert "Caiu no chão / contaminou" in r["uso"]["motivos_avaria"]
    r2 = client.post("/api/bipar", headers=admin_headers, json={
        "operacao": "registrar_uso", "codigo": "7891230000099", "atendimento": id_at}).json()
    assert r2["ok"], r2
    outro = [i for i in r2["uso"]["lista"] if not i["avaria"]][0]
    r3 = client.post("/api/avaria", headers=admin_headers, json={
        "id_unidade": outro["id_unidade"], "atendimento": id_at, "motivo": "Veio danificado / embalagem violada"}).json()
    assert r3["ok"] and all(i["avaria"] for i in r3["uso"]["lista"])
    assert db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='avaria_sinalizada' AND id_atendimento=?", (id_at,)) == 2
    # v18.4.7: não gera alerta — vai para o indicador de problemas na sala
    assert db.escalar("SELECT COUNT(*) FROM alertas WHERE titulo LIKE 'Material com problema%'") == 0
    from src.providers.implementations.opme.services import indicadores
    ps = indicadores.problemas_na_sala(hoje_iso(), hoje_iso())
    assert ps["total"] >= 2
    assert {m["motivo"] for m in ps["por_motivo"]} >= {"Caiu no chão / contaminou", "Veio danificado / embalagem violada"}
    assert any(m["codigo_aghu"] == "880" for m in ps["por_material"])
    tela = client.get("/api/indicadores/qualidade", headers=admin_headers)
    assert tela.status_code == 200 and tela.json()["dados"]["problemas_sala"]["total"] >= 2
    r4 = client.post("/api/avaria", headers=admin_headers, json={
        "id_unidade": outro["id_unidade"], "atendimento": id_at, "motivo": "Outro problema"}).json()
    assert not r4["ok"]
