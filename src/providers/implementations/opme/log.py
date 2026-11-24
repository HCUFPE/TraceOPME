"""Registro de log da aplicação.

Separação proposital de responsabilidades:

* a tabela `eventos` é a **auditoria de negócio** — quem movimentou qual item,
  quando e por quê. É consultável pela interface e nunca é apagada;
* o arquivo `logs/opme.log` é o **diário técnico** — erros de programação,
  falhas de banco, tentativas de login. Serve para diagnosticar problema,
  não para auditoria assistencial.

Nada de dado clínico vai para o arquivo: nem prontuário, nem nome de paciente.
Isso é intencional — arquivo de log costuma acabar em anexo de e-mail.
"""

import logging
import re
from logging.handlers import RotatingFileHandler

from .config import LOG_DIR

ARQUIVO = LOG_DIR / "opme.log"

_PRONTUARIO = re.compile(r"\b(prontu[áa]rio|paciente)\s*[:=]?\s*\S+", re.IGNORECASE)


class SemDadoClinico(logging.Filter):
    """Remove prontuário e nome de paciente antes de gravar."""

    def filter(self, registro: logging.LogRecord) -> bool:
        try:
            registro.msg = _PRONTUARIO.sub(r"\1 [oculto]", str(registro.getMessage()))
            registro.args = ()
        except Exception:
            pass
        return True


def _configurar() -> logging.Logger:
    logger = logging.getLogger("opme")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(usuario)-15s | %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )

    arquivo = RotatingFileHandler(
        ARQUIVO, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    arquivo.setFormatter(formato)
    arquivo.addFilter(SemDadoClinico())
    logger.addHandler(arquivo)

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(formato)
    console.addFilter(SemDadoClinico())
    logger.addHandler(console)

    return logger


_logger = _configurar()


def _com_usuario(usuario: str = "") -> dict:
    return {"extra": {"usuario": usuario or "sistema"}}


def info(mensagem: str, usuario: str = "") -> None:
    _logger.info(mensagem, **_com_usuario(usuario))


def aviso(mensagem: str, usuario: str = "") -> None:
    _logger.warning(mensagem, **_com_usuario(usuario))


def erro(mensagem: str, usuario: str = "", excecao: BaseException | None = None) -> None:
    """Registra a falha com o traceback completo, que não vai para a tela do operador."""
    _logger.error(mensagem, exc_info=excecao, **_com_usuario(usuario))


def ultimas_linhas(quantidade: int = 200) -> list[str]:
    """Últimas linhas do log, para a tela de diagnóstico do administrador."""
    if not ARQUIVO.exists():
        return []
    with open(ARQUIVO, "r", encoding="utf-8", errors="replace") as arquivo:
        return [linha.rstrip("\n") for linha in arquivo.readlines()[-quantidade:]][::-1]
