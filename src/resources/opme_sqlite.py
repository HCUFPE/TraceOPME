# src/resources/opme_sqlite.py
"""
Resource: conexão com o banco local de rastreabilidade do TraceOPME (SQLite).
==============================================================================

Camada *Resource* do Framework SETISD para o banco ``opme.db``. É o mesmo
arquivo usado pela versão 17 do TraceOPME, então os dados de produção seguem
valendo sem migração: basta apontar ``OPME_DB`` (no ``.env``) para ele.

Por que ``sqlite3`` e não o pool assíncrono do SQLAlchemy aqui?
    As regras de rastreabilidade dependem de transações ``BEGIN IMMEDIATE``
    (tudo ou nada em cada movimentação) e de duas funções SQL próprias
    (``gtin()`` e ``lote_norm()``) registradas na conexão. Elas foram mantidas
    exatamente como estavam — e testadas — na versão 17. As rotas executam essas
    operações fora do *event loop* (``run_in_threadpool``), sem bloquear o servidor.

O banco *interno do framework* (``APP_DB_URL`` — refresh tokens e ``audit_logs``)
continua no SQLAlchemy assíncrono, em ``src/resources/database.py``.
"""

import sqlite3
from pathlib import Path
from typing import Callable

from ..config import settings

# Funções SQL escalares registradas em toda conexão: (nome, nº de argumentos, função).
_FUNCOES_SQL: list[tuple[str, int, Callable]] = []


def registrar_funcao_sql(nome: str, n_argumentos: int, funcao: Callable) -> None:
    """Registra uma função Python para ser usada dentro do SQL (ex.: ``gtin(codigo)``)."""
    if not any(f[0] == nome for f in _FUNCOES_SQL):
        _FUNCOES_SQL.append((nome, n_argumentos, funcao))


def caminho_banco() -> Path:
    """Caminho do arquivo ``opme.db`` em uso (vem de ``OPME_DB`` no ``.env``)."""
    return settings.OPME_DB_PATH


def conectar() -> sqlite3.Connection:
    """Abre uma conexão com o ``opme.db`` já configurada (WAL, chaves estrangeiras, funções SQL)."""
    conn = sqlite3.connect(caminho_banco(), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    for nome, n_argumentos, funcao in _FUNCOES_SQL:
        conn.create_function(nome, n_argumentos, funcao, deterministic=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def verificar_conexao() -> bool:
    """Teste simples (``SELECT 1``) usado pelo endpoint de saúde ``/api/health``."""
    conn = conectar()
    try:
        conn.execute("SELECT 1").fetchone()
        return True
    finally:
        conn.close()
