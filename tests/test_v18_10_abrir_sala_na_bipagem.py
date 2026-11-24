# tests/test_v18_10_abrir_sala_na_bipagem.py
"""v18.10: registrar uso com a sala fechada abre a tela travada e "Abrir sala agora" libera ali mesmo."""
from src.providers.implementations.opme.services import atendimentos
from src.providers.implementations.opme.utils import hoje_iso


def test_abrir_sala_na_propria_bipagem(client, admin_headers):
    h = admin_headers
    ok, a = atendimentos.abrir({"prontuario": "771010", "unidade": "BLOCO CIRURGICO", "sala": "07",
                                "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso(),
                                "hora_inicio": "09:00"}, "admin")
    assert ok
    r = client.get(f"/api/bipagem/registrar_uso?atendimento={a}", headers=h).json()
    assert r.get("tela") == "bipagem.html" and r["dados"]["sala_fechada"] is True
    r = client.post("/api/abrir-sala", headers=h, json={"atendimento": a}).json()
    assert r["ok"], r
    assert atendimentos.buscar(a)["sala_aberta_em"]
    r = client.get(f"/api/bipagem/registrar_uso?atendimento={a}", headers=h).json()
    assert r["dados"]["sala_fechada"] is False
    # abrir de novo não quebra
    assert "ok" in client.post("/api/abrir-sala", headers=h, json={"atendimento": a}).json()
