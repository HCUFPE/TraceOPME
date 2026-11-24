# tests/test_v18_4_backup.py
"""v18.4: cópia diária conferida + cópia fora do servidor."""
from datetime import datetime

from src.providers.implementations.opme.services import backup


def test_copia_conferida_e_enviada_para_fora(client, tmp_path, monkeypatch):
    externa = tmp_path / "rede" / "traceopme"
    monkeypatch.setenv("BACKUP_PASTA_EXTERNA", str(externa))
    c = backup.copiar(forcar=True)
    assert c and c.exists()
    st = backup.situacao()
    assert st["conferencia"].startswith("íntegra")
    assert st["externa_configurada"] and st["externo_ultima"] and not st["externo_erro"]
    assert (externa / c.name).exists() and (externa / c.name).stat().st_size == c.stat().st_size
    assert st["tudo_certo"] is True or st["em_dia"]


def test_pasta_externa_inacessivel_aparece_como_erro(client, tmp_path, monkeypatch):
    arquivo_no_caminho = tmp_path / "isto_e_um_arquivo"
    arquivo_no_caminho.write_text("x")
    monkeypatch.setenv("BACKUP_PASTA_EXTERNA", str(arquivo_no_caminho / "sub"))
    c = backup.copiar(forcar=True)
    assert c  # a cópia local vale mesmo com a rede fora
    st = backup.situacao()
    assert st["externo_erro"] and not st["externo_em_dia"]


def test_sem_pasta_externa_configurada(client, monkeypatch):
    monkeypatch.delenv("BACKUP_PASTA_EXTERNA", raising=False)
    backup.copiar(forcar=True)
    st = backup.situacao()
    assert not st["externa_configurada"] and not st["tudo_certo"]


def test_horario_programado(client, monkeypatch):
    monkeypatch.setenv("BACKUP_HORA", "23:59")
    assert backup.precisa_copiar(datetime.now().replace(hour=1, minute=0)) is False
    monkeypatch.setenv("BACKUP_HORA", "nada")
    assert backup.hora_programada() == "02:00"


def test_tela_admin_mostra_backup(client, admin_headers):
    d = client.get("/api/admin", headers=admin_headers).json()["dados"]
    assert "hora" in d["backup"] and "externa_configurada" in d["backup"]
