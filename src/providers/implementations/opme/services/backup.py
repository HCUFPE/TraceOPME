"""Cópia de segurança do banco.

Todo o sistema vive em um arquivo só (`data/opme.db`). Isso é ótimo para
operar — não há servidor de banco para administrar — e péssimo para perder:
um disco com defeito leva junto o histórico inteiro de rastreabilidade, que é
exatamente o que não pode faltar numa auditoria ou num recall.

A cópia é feita com a API de backup do próprio SQLite, e não com uma cópia de
arquivo. A diferença importa: copiar o arquivo com o sistema em uso pode
capturar um estado inconsistente, no meio de uma transação. A API do SQLite
resolve isso e funciona com o banco aberto.

v18.4 — cópia diária de verdade e cópia FORA do servidor:
* a rotina (`rotina()`, ligada no lifespan) faz a cópia do dia no horário
  BACKUP_HORA (padrão 02:00), mesmo que a aplicação fique semanas sem reiniciar;
* cada cópia é conferida (PRAGMA integrity_check) antes de valer;
* depois, a cópia vai também para BACKUP_PASTA_EXTERNA (pasta de rede do
  hospital, ex.: //servidor/backup/traceopme ou uma unidade mapeada), guardando BACKUP_EXTERNO_MANTER
  cópias. Falhas ficam registradas e aparecem na Administração.
"""

import json
import os
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import log
from ..config import DB_PATH

PASTA = DB_PATH.parent / "backups"
COPIAS_MANTIDAS = int(os.getenv("BACKUP_MANTER", "30") or 30)
SITUACAO = PASTA / "situacao.json"


def hora_programada() -> str:
    h = (os.getenv("BACKUP_HORA", "02:00") or "02:00").strip()
    try:
        datetime.strptime(h, "%H:%M")
        return h
    except ValueError:
        return "02:00"


def pasta_externa() -> Path | None:
    v = (os.getenv("BACKUP_PASTA_EXTERNA", "") or "").strip()
    return Path(v) if v else None


def externo_manter() -> int:
    try:
        return max(1, int(os.getenv("BACKUP_EXTERNO_MANTER", "60") or 60))
    except ValueError:
        return 60


def _ler_situacao() -> dict:
    try:
        return json.loads(SITUACAO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_situacao(**campos) -> None:
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        atual = _ler_situacao() | campos
        SITUACAO.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as falha:  # nunca derruba o sistema
        log.erro("falha ao gravar a situação do backup", excecao=falha)


def caminho_app_db() -> Path | None:
    """v18.4.2: o banco administrativo do framework (app.db), se for SQLite."""
    url = (os.getenv("SQLITE_DSN") or os.getenv("APP_DB_URL") or "sqlite+aiosqlite:///data/app.db").strip()
    if not url.startswith("sqlite"):
        return None
    caminho = url.split(":///", 1)[1] if ":///" in url else ""
    if not caminho:
        return None
    p = Path(caminho)
    return p if p.is_absolute() else (Path.cwd() / p)


def conferir(arquivo: Path) -> tuple[bool, str]:
    """A cópia abre e está íntegra? (PRAGMA integrity_check)."""
    try:
        con = sqlite3.connect(f"file:{arquivo}?mode=ro", uri=True)
        try:
            r = con.execute("PRAGMA integrity_check").fetchone()
            tem_unidades = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='unidades'").fetchone()
            n = con.execute("SELECT COUNT(*) FROM unidades").fetchone()[0] if tem_unidades else None
        finally:
            con.close()
        if not r or r[0] != "ok":
            return False, f"cópia com defeito: {r[0] if r else 'sem resposta'}"
        return True, (f"íntegra · {n} unidade(s)" if n is not None else "íntegra")
    except Exception as falha:
        return False, f"não abriu: {falha}"


def _copiar_sqlite(origem_path: Path, destino: Path) -> None:
    origem = sqlite3.connect(origem_path)
    try:
        copia = sqlite3.connect(destino)
        try:
            origem.backup(copia)
        finally:
            copia.close()
    finally:
        origem.close()


def copiar_app_db(data_ref: str) -> Path | None:
    """v18.4.2: cópia do app.db junto com a do opme.db (mesmo dia/hora no nome)."""
    origem = caminho_app_db()
    if not origem:
        return None
    if not origem.exists():
        # v18.4.5: banco administrativo esperado e não encontrado conta como falha.
        _gravar_situacao(app_ok=False, app_erro=f"app.db não encontrado em {origem}")
        return None
    destino = PASTA / f"app_{data_ref}.db"
    try:
        _copiar_sqlite(origem, destino)
        ok, detalhe = conferir(destino)
        if not ok:
            log.erro(f"cópia do app.db com problema · {detalhe}")
            _gravar_situacao(app_ok=False, app_erro=detalhe)
            return None
        _gravar_situacao(app_ok=True, app_erro="", app_ultima=datetime.now().isoformat(timespec="seconds"))
        for velha in sorted(PASTA.glob("app_????-??-??.db"))[:-COPIAS_MANTIDAS]:
            try:
                velha.unlink()
            except OSError:
                pass
        return destino
    except Exception as falha:
        log.erro("falha ao copiar o app.db", excecao=falha)
        _gravar_situacao(app_ok=False, app_erro=f"{falha.__class__.__name__}: {falha}")
        return None


def copiar_externo(arquivo: Path, extras: list[Path] | None = None) -> tuple[bool, str]:
    """Copia a cópia do dia (e as extras, como o app.db) para a pasta de rede."""
    destino_pasta = pasta_externa()
    if not destino_pasta:
        _gravar_situacao(externo_ok=False, externo_erro="pasta externa não configurada (BACKUP_PASTA_EXTERNA)",
                         externo_tentativa=datetime.now().isoformat(timespec="seconds"))
        return False, "pasta externa não configurada"
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        destino_pasta.mkdir(parents=True, exist_ok=True)
        destino = destino_pasta / arquivo.name
        for origem_arq in [arquivo, *(extras or [])]:
            alvo = destino_pasta / origem_arq.name
            temporario = destino_pasta / (origem_arq.name + ".parcial")
            shutil.copy2(origem_arq, temporario)
            if temporario.stat().st_size != origem_arq.stat().st_size:
                raise OSError(f"tamanho da cópia de {origem_arq.name} diferente do original")
            os.replace(temporario, alvo)
        for padrao in ("opme_*.db", "app_*.db"):
            copias = sorted(destino_pasta.glob(padrao))
            for velha in copias[:-externo_manter()]:
                try:
                    velha.unlink()
                except OSError:
                    pass
        _gravar_situacao(externo_ok=True, externo_erro="", externo_ultima=agora, externo_arquivo=str(destino),
                         externo_tentativa=agora)
        log.info(f"cópia de segurança enviada para fora do servidor · {destino}")
        return True, str(destino)
    except Exception as falha:
        _gravar_situacao(externo_ok=False, externo_erro=f"{falha.__class__.__name__}: {falha}",
                         externo_tentativa=agora)
        log.erro(f"falha ao copiar o backup para {destino_pasta}", excecao=falha)
        return False, str(falha)


def _nome_do_dia() -> str:
    return f"opme_{date.today().isoformat()}.db"


def copiar(forcar: bool = False) -> Path | None:
    """Faz a cópia do dia. Devolve o caminho, ou None se não havia o que copiar.

    Uma cópia por dia é suficiente e evita encher o disco: quem abre o sistema
    cinco vezes no dia não precisa de cinco cópias iguais.
    """
    if not DB_PATH.exists():
        return None

    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / _nome_do_dia()
    if destino.exists() and not forcar:
        return destino
    if forcar and destino.exists():
        # cópia manual no mesmo dia: guarda com a hora, sem perder a do dia
        destino = PASTA / f"opme_{date.today().isoformat()}_{datetime.now():%H%M%S}.db"

    try:
        origem = sqlite3.connect(DB_PATH)
        try:
            copia = sqlite3.connect(destino)
            try:
                origem.backup(copia)
            finally:
                copia.close()
        finally:
            origem.close()
    except Exception as falha:
        # Backup que falha não pode impedir o sistema de subir — mas tem que
        # aparecer no log e na tela de administração.
        log.erro("falha ao gerar a cópia de segurança", excecao=falha)
        return None

    ok, detalhe = conferir(destino)
    agora = datetime.now().isoformat(timespec="seconds")
    if not ok:
        log.erro(f"cópia de segurança com problema · {destino.name} · {detalhe}")
        _gravar_situacao(local_ok=False, local_erro=detalhe, local_tentativa=agora)
        try:
            destino.rename(destino.with_suffix(".defeito"))
        except OSError:
            pass
        return None
    _gravar_situacao(local_ok=True, local_erro="", local_ultima=agora, local_arquivo=destino.name,
                     local_detalhe=detalhe, local_tentativa=agora)
    _limpar_antigas()
    log.info(f"cópia de segurança gerada · {destino.name} · {detalhe}")
    app = copiar_app_db(destino.stem.replace("opme_", "", 1))
    copiar_externo(destino, [app] if app else None)
    return destino


def _limpar_antigas() -> None:
    copias = sorted(PASTA.glob("opme_????-??-??.db"))
    for velha in copias[:-COPIAS_MANTIDAS]:
        try:
            velha.unlink()
        except OSError:
            pass


def listar() -> list[dict]:
    if not PASTA.exists():
        return []
    linhas = []
    for arquivo in sorted(PASTA.glob("opme_*.db"), reverse=True):
        info = arquivo.stat()
        linhas.append({
            "nome": arquivo.name,
            "tamanho_mb": round(info.st_size / 1_000_000, 2),
            "quando": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
        })
    return linhas


def situacao() -> dict:
    """Resumo para a tela de administração avisar quando algo está errado."""
    copias = listar()
    ultima = copias[0] if copias else None
    dias = None
    if ultima:
        dias = (date.today() - datetime.fromisoformat(ultima["quando"]).date()).days
    st = _ler_situacao()
    ext = pasta_externa()
    dias_ext = None
    if st.get("externo_ultima"):
        dias_ext = (date.today() - datetime.fromisoformat(st["externo_ultima"]).date()).days
    externo_em_dia = bool(ext) and dias_ext is not None and dias_ext <= 1 and st.get("externo_ok") is not False
    # v18.4.5: o indicador geral exige também a cópia do app.db (usuários, perfis, auditoria).
    app_esperado = caminho_app_db() is not None
    dias_app = None
    if st.get("app_ultima"):
        dias_app = (date.today() - datetime.fromisoformat(st["app_ultima"]).date()).days
    app_em_dia = (not app_esperado) or (dias_app is not None and dias_app <= 1 and st.get("app_ok") is not False)
    opme_em_dia = dias is not None and dias <= 1
    return {
        "pasta": str(PASTA),
        "total": len(copias),
        "ultima": ultima,
        "dias_desde_ultima": dias,
        "em_dia": opme_em_dia and app_em_dia,
        "opme_em_dia": opme_em_dia,
        "app_esperado": app_esperado,
        "app_em_dia": app_em_dia,
        "copias": copias[:10],
        # v18.4
        "hora": hora_programada(),
        "conferencia": st.get("local_detalhe", ""),
        "erro_local": st.get("local_erro", "") if st.get("local_ok") is False else "",
        "externa_configurada": bool(ext),
        "pasta_externa": str(ext) if ext else "",
        "externo_ultima": st.get("externo_ultima", ""),
        "dias_desde_externo": dias_ext,
        "externo_erro": st.get("externo_erro", "") if st.get("externo_ok") is False else "",
        "externo_em_dia": externo_em_dia,
        "tudo_certo": opme_em_dia and app_em_dia and externo_em_dia,
        "app_db": str(caminho_app_db() or ""),
        "app_ultima": st.get("app_ultima", ""),
        "app_erro": st.get("app_erro", "") if st.get("app_ok") is False else "",
    }


def _app_pendente(st: dict, agora: datetime) -> bool:
    """v18.4.5: o app.db é SQLite e ainda não tem cópia conferida de hoje."""
    return caminho_app_db() is not None and not str(st.get("app_ultima", "")).startswith(agora.date().isoformat())


def precisa_copiar(agora: datetime | None = None) -> bool:
    """Já passou da hora programada e ainda não há cópia de hoje (ou a externa falhou hoje)?"""
    agora = agora or datetime.now()
    if agora.strftime("%H:%M") < hora_programada():
        return False
    if not (PASTA / _nome_do_dia()).exists():
        return True
    st = _ler_situacao()
    # v18.4.5: a cópia do opme.db de hoje existe, mas a do app.db falhou: tenta de novo.
    if _app_pendente(st, agora):
        try:
            recente = agora - datetime.fromisoformat(st.get("app_tentativa", "")) < timedelta(minutes=30)
        except ValueError:
            recente = False
        if not recente:
            return True
    # a cópia local de hoje existe, mas a externa não foi feita hoje: tenta de novo
    # (no máximo a cada 30 minutos), até a pasta de rede voltar.
    if pasta_externa() and not str(st.get("externo_ultima", "")).startswith(agora.date().isoformat()):
        ultima_tentativa = st.get("externo_tentativa", "")
        try:
            return agora - datetime.fromisoformat(ultima_tentativa) >= timedelta(minutes=30)
        except ValueError:
            return True
    return False


def executar_rotina() -> str:
    if not precisa_copiar():
        return ""
    destino = PASTA / _nome_do_dia()
    if destino.exists():
        app = PASTA / destino.name.replace("opme_", "app_", 1)
        if _app_pendente(_ler_situacao(), datetime.now()):
            _gravar_situacao(app_tentativa=datetime.now().isoformat(timespec="seconds"))
            novo = copiar_app_db(destino.stem.replace("opme_", "", 1))
            if novo:
                ok, msg = copiar_externo(destino, [novo])
                return f"nova cópia do app.db: ok; externa: {'ok' if ok else msg}"
            return "nova cópia do app.db: FALHOU"
        ok, msg = copiar_externo(destino, [app] if app.exists() else None)
        return f"nova tentativa da cópia externa: {'ok' if ok else msg}"
    c = copiar()
    return f"cópia do dia: {c.name if c else 'FALHOU'}"


async def rotina(intervalo: int = 300) -> None:
    """Laço da cópia diária (iniciado no lifespan). Confere a cada 5 minutos."""
    import asyncio

    from starlette.concurrency import run_in_threadpool
    while True:
        try:
            m = await run_in_threadpool(executar_rotina)
            if m:
                print(f"Backup: {m}")
        except Exception as erro:  # noqa: BLE001
            print(f"Backup: erro {erro.__class__.__name__}: {erro}")
        await asyncio.sleep(intervalo)
