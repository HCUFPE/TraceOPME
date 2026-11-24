# tests/test_v18_2_balanco.py
"""v18.2: na ciência dos não utilizados, a farmácia vê o que foi para o paciente,
o que foi usado e o que deve voltar."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import (atendimentos, devolucoes, dispensacoes, estoque,
                                                         fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso


def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


def test_balanco_da_devolucao(client, admin_headers):
    estoque.cadastrar_manual({"xProd": "PLACA BAL", "codigo_barras": "7891230007771", "codigo_aghu": "661",
                              "fornecedor": "F", "marca_fabricante": "M", "nLote": "LB", "dVal": "2031-01-01",
                              "quantidade": "3", "tipo_entrada": "aquisicao_propria"}, "admin")
    db.executar("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE codigo_barras='7891230007771'")
    ok, a = _abrir_at({"prontuario": "660001", "unidade": "BLOCO CIRURGICO", "sala": "02",
                                "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    for _ in range(3):
        r = dispensacoes.bipar(codigo="7891230007771", id_atendimento=a, usuario="admin", farmacia="BLOCO CIRURGICO")
        assert r["ok"], r
    disp = db.consultar_um("SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento=?", (a,))
    db.executar("UPDATE usuarios SET status='ativo' WHERE username='admin'")
    ok, msg = dispensacoes.confirmar(id_dispensacao=disp["id_dispensacao"], logado={"username": "admin", "nome": "Admin", "papel": "admin"})
    assert ok, msg
    r = client.post("/api/bipar", headers=admin_headers, json={"operacao": "registrar_uso", "codigo": "7891230007771",
                                                                "atendimento": a}).json()
    assert r["ok"], r
    ok, msg, _ = fechamento.finalizar_uso(a, {"username": "admin", "nome": "Admin", "papel": "admin"})
    assert ok, msg
    dev = db.consultar_um("SELECT id_devolucao FROM devolucoes WHERE id_atendimento=? AND status='pendente'", (a,))
    b = devolucoes.balanco(dev["id_devolucao"])
    assert b["resumo"]["usado"] == 1 and b["resumo"]["voltando"] == 2 and b["resumo"]["total"] == 3
    usado = next(l for l in b["linhas"] if l["situacao"] == "usado")
    assert usado["usado_em"] and usado["usado_por"] == "admin"
    tela = client.get(f"/api/devolucoes/{dev['id_devolucao']}", headers=admin_headers).json()
    assert tela["dados"]["balanco"]["resumo"]["voltando"] == 2
