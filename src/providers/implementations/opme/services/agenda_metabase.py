"""nov/2026 — agenda de procedimentos direto do relatórios (Metabase).

Substitui o "baixar o CSV e anexar": o TraceOPME entra no Metabase do HC-UFPE
(login de rede, o Metabase usa o AD), pede as linhas do modelo da agenda
(1703 — "Escala prévia definitiva") só do dia escolhido e importa pelo mesmo
caminho do CSV (`atendimentos.importar_agenda_csv`): reimportar não duplica, e
o pedido de OPME é completado quando aparece.

Dois jeitos de usar:
* botão "Buscar no relatórios" em Procedimentos (com a senha da pessoa, ou com
  o usuário configurado no .env);
* rotina diária (AGENDA_AUTOMATICA=1): busca sozinha nos horários de
  AGENDA_HORARIOS. Se o sistema for ligado depois de um horário, busca na hora.

Cada busca fica registrada em `agenda_buscas` (quando, dia, origem, resultado).
Nunca grava a senha.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta

from .. import db, log
from ..utils import texto

LIMITE_JSON = 2000
ISO_DATA_HORA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")

SQL_TABELA = """CREATE TABLE IF NOT EXISTS agenda_buscas (
    id_busca   INTEGER PRIMARY KEY AUTOINCREMENT,
    quando     TEXT NOT NULL,
    dia        TEXT NOT NULL,
    origem     TEXT NOT NULL,          -- automatica | manual
    horario    TEXT,                   -- horário da rotina que disparou (automática)
    usuario    TEXT,
    ok         INTEGER NOT NULL,
    linhas     INTEGER,
    mensagem   TEXT
)"""


class ErroAgenda(Exception):
    pass


def _cfg():
    from .....config import settings
    return settings


def configurada() -> bool:
    s = _cfg()
    return bool(texto(s.METABASE_URL) and texto(s.METABASE_USUARIO) and texto(s.METABASE_SENHA))


def situacao() -> dict:
    s = _cfg()
    return {"configurada": configurada(), "automatica": bool(s.AGENDA_AUTOMATICA and configurada()),
            "horarios": horarios(), "dias": dias(), "modelo": s.AGENDA_MODELO, "url": s.METABASE_URL,
            "usuario": s.METABASE_USUARIO, "ultimas": ultimas(5)}


def horarios() -> list[str]:
    return [h.strip()[:5] for h in texto(_cfg().AGENDA_HORARIOS).split(",") if re.fullmatch(r"\d{1,2}:\d{2}", h.strip())]


def dias() -> list[int]:
    saida = []
    for d in texto(_cfg().AGENDA_DIAS or "0").split(","):
        try:
            saida.append(int(d.strip()))
        except ValueError:
            pass
    return saida or [0]


def _garantir_tabela() -> None:
    db.executar(SQL_TABELA)


def ultimas(limite: int = 10) -> list[dict]:
    _garantir_tabela()
    return db.consultar("SELECT * FROM agenda_buscas ORDER BY id_busca DESC LIMIT ?", (int(limite),))


def _registrar(dia: str, origem: str, usuario: str, ok: bool, linhas: int | None, mensagem: str,
               horario: str = "", quando: str = "") -> None:
    _garantir_tabela()
    db.executar("""INSERT INTO agenda_buscas (quando, dia, origem, horario, usuario, ok, linhas, mensagem)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (quando or db.agora(), dia, origem, horario or None, usuario, 1 if ok else 0, linhas, mensagem[:500]))


def _valor_csv(v):
    """Data do Metabase (2026-11-04T07:30:00-03:00) no formato do export do AGHU (4/11/2026, 07:30)."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        # nov/2026: colunas de lista (solicitacao_especial, opme) vêm como array;
        # escreve no mesmo formato do export do AGHU: ["OPME (1) - ...", "..."]
        return json.dumps([texto(x) for x in v if x is not None], ensure_ascii=False)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, str):
        m = ISO_DATA_HORA.match(v)
        if m:
            ano, mes, dia, hh, mm = m.groups()
            data = f"{int(dia)}/{int(mes)}/{ano}"
            return f"{data}, {hh}:{mm}" if hh else data
    return v


def _coluna_data(colunas: list[dict], preferida: str) -> dict:
    if preferida:
        for c in colunas:
            if preferida.upper() in (texto(c.get("name")).upper(), texto(c.get("display_name")).upper()):
                return c
        raise ErroAgenda(f"A coluna {preferida} (AGENDA_COLUNA_DATA) não existe no modelo.")
    datas = [c for c in colunas if "Date" in texto(c.get("base_type")) or "Date" in texto(c.get("effective_type"))]
    for pista in ("DTHR_INICIO", "INICIO_CIRG", "DATA_CIRURGIA", "DT_CIRURGIA", "DTHR", "DATA"):
        for c in datas:
            if pista in texto(c.get("name")).upper():
                return c
    if datas:
        return datas[0]
    raise ErroAgenda("O modelo da agenda não tem coluna de data. Informe AGENDA_COLUNA_DATA no .env.")


def buscar_csv(dia: str, usuario: str = "", senha: str = "") -> tuple[bytes, int]:
    """CSV (no formato do export do AGHU) com a agenda do `dia` (AAAA-MM-DD) e o número de linhas."""
    import requests

    s = _cfg()
    usuario = texto(usuario) or texto(s.METABASE_USUARIO)
    senha = senha or s.METABASE_SENHA
    if not usuario or not senha:
        raise ErroAgenda("Informe o usuário e a senha de rede para buscar no relatórios.")
    base = texto(s.METABASE_URL).rstrip("/")
    sessao = requests.Session()
    sessao.trust_env = False  # endereço interno: não passa pelo proxy de internet
    try:
        r = sessao.post(f"{base}/api/session", json={"username": usuario, "password": senha}, timeout=60)
    except requests.RequestException as erro:
        raise ErroAgenda(f"Não consegui falar com o relatórios ({base}). Confira a rede do hospital. ({erro.__class__.__name__})")
    if r.status_code in (400, 401):
        raise ErroAgenda("O relatórios não aceitou o usuário ou a senha.")
    if r.status_code != 200:
        raise ErroAgenda(f"O relatórios respondeu com erro ao entrar (HTTP {r.status_code}).")
    sessao.headers["X-Metabase-Session"] = r.json()["id"]
    try:
        r = sessao.get(f"{base}/api/card/{s.AGENDA_MODELO}", timeout=60)
        if r.status_code != 200:
            raise ErroAgenda(f"Não consegui abrir o modelo {s.AGENDA_MODELO} da agenda (HTTP {r.status_code}). "
                             "Confira se o seu usuário tem acesso a ele.")
        card = r.json()
        col = _coluna_data(card.get("result_metadata") or [], texto(s.AGENDA_COLUNA_DATA))
        tipo = col.get("base_type") or "type/DateTime"
        filtro = ["=", ["field", col["name"], {"base-type": tipo, "temporal-unit": "day"}], dia]
        consulta = {"database": card["database_id"], "type": "query",
                    "query": {"source-table": f"card__{s.AGENDA_MODELO}", "filter": filtro}, "parameters": []}
        r = sessao.post(f"{base}/api/dataset", json=consulta, timeout=300)
        dados = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code not in (200, 202) or dados.get("status") == "failed" or dados.get("error"):
            raise ErroAgenda(f"O relatórios recusou a consulta: {dados.get('error') or r.status_code}")
        # `name` (nome técnico, ex.: DTHR_INICIO_CIRG) é o que a importação reconhece.
        nomes = [c.get("name") or c.get("display_name") for c in dados["data"]["cols"]]
        linhas = dados["data"]["rows"]
        if len(linhas) >= LIMITE_JSON:
            r = sessao.post(f"{base}/api/dataset/csv", data={"query": json.dumps(consulta), "format_rows": "false"},
                            timeout=600)
            if r.status_code != 200:
                raise ErroAgenda(f"Falha na exportação completa (HTTP {r.status_code}).")
            todas = list(csv.reader(r.content.decode("utf-8-sig").splitlines()))
            linhas = todas[1:]
        saida = io.StringIO()
        w = csv.writer(saida, delimiter=";")
        w.writerow(nomes)
        for l in linhas:
            w.writerow([_valor_csv(v) for v in l])
        conteudo = saida.getvalue().encode("utf-8-sig")
        try:  # cópia da última busca, para conferir quando algo não vier como esperado
            from ..config import DATA_DIR
            (DATA_DIR / "ultima_agenda_relatorios.csv").write_bytes(conteudo)
        except Exception:
            pass
        return conteudo, len(linhas)
    finally:
        try:
            sessao.delete(f"{base}/api/session", timeout=20)
        except Exception:
            pass


def buscar_e_importar(dia: str, quem: str, origem: str = "manual", usuario: str = "", senha: str = "",
                      horario: str = "", quando: str = "") -> tuple[bool, str]:
    from . import atendimentos
    try:
        conteudo, n = buscar_csv(dia, usuario, senha)
    except ErroAgenda as erro:
        _registrar(dia, origem, quem, False, None, str(erro), horario, quando)
        log.info(f"agenda metabase · {dia} · falhou: {erro}", quem)
        return False, str(erro)
    except Exception as erro:  # noqa: BLE001 — nunca derrubar a rotina
        msg = f"Falha inesperada ao buscar a agenda: {erro.__class__.__name__}"
        _registrar(dia, origem, quem, False, None, msg, horario, quando)
        log.erro(msg, quem)
        return False, msg
    if n == 0:
        msg = f"O relatórios não tem procedimentos para {dia[8:10]}/{dia[5:7]}/{dia[:4]}."
        _registrar(dia, origem, quem, True, 0, msg, horario, quando)
        return True, msg
    ok, mensagem = atendimentos.importar_agenda_csv(conteudo, quem)
    _registrar(dia, origem, quem, ok, n, mensagem, horario, quando)
    return ok, mensagem


# ---------------------------------------------------------------- rotina diária

def pendentes_agora(agora: datetime | None = None) -> list[str]:
    """Horários de hoje que já passaram e ainda não tiveram busca automática."""
    agora = agora or datetime.now()
    _garantir_tabela()
    feitos = {l["horario"] for l in db.consultar(
        "SELECT DISTINCT horario FROM agenda_buscas WHERE origem = 'automatica' AND substr(quando, 1, 10) = ?",
        (agora.date().isoformat(),))}
    passados = [h for h in horarios() if h.zfill(5) <= agora.strftime("%H:%M")]
    # Só o último horário vencido: ligar o sistema às 14h não dispara 06:00 e 12:00 em sequência.
    return [passados[-1]] if passados and passados[-1] not in feitos else []


def executar_rotina(agora: datetime | None = None) -> list[str]:
    """Uma passada da rotina: busca os dias configurados para o horário vencido."""
    agora = agora or datetime.now()
    mensagens = []
    for horario in pendentes_agora(agora):
        for deslocamento in dias():
            dia = (agora.date() + timedelta(days=deslocamento)).isoformat()
            ok, msg = buscar_e_importar(dia, "rotina-agenda", "automatica", horario=horario,
                                        quando=agora.isoformat(timespec="seconds"))
            mensagens.append(f"{horario} · {dia} · {'ok' if ok else 'falhou'} · {msg}")
    return mensagens


async def rotina(intervalo: int = 60) -> None:
    """Laço da rotina diária (iniciado no lifespan quando AGENDA_AUTOMATICA=1)."""
    import asyncio

    from starlette.concurrency import run_in_threadpool
    while True:
        try:
            for m in await run_in_threadpool(executar_rotina):
                print(f"Agenda automática: {m}")
        except Exception as erro:  # noqa: BLE001
            print(f"Agenda automática: erro {erro.__class__.__name__}: {erro}")
        await asyncio.sleep(intervalo)
