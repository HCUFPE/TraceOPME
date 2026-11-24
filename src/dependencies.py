from typing import Callable

from .providers.interfaces.opme_provider_interface import OpmeProviderInterface
from .providers.implementations.opme_sqlite_provider import OpmeSqliteProvider

# Instância única: o provedor SQLite não guarda estado por requisição
# (cada operação abre e fecha a própria conexão/transação).
_opme_sqlite_provider = OpmeSqliteProvider()


# 1. Funções "getter" simples e independentes (privadas por convenção)
def _get_opme_sqlite_provider() -> OpmeProviderInterface:
    return _opme_sqlite_provider


# 2. A FÁBRICA: a única função que o restante da aplicação conhece.
def get_opme_provider(strategy: str = "SQLITE") -> Callable[..., OpmeProviderInterface]:
    """
    Fábrica de provedores do TraceOPME. Baseado na string 'strategy', retorna
    a FUNÇÃO DE DEPENDÊNCIA correta que o FastAPI deve usar.
    """
    if strategy.upper() == "SQLITE":
        return _get_opme_sqlite_provider
    raise ValueError(f"Estratégia de provedor desconhecida: {strategy}")
