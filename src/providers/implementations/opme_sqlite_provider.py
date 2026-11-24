"""Provedor SQLite do TraceOPME (banco local opme.db).

As regras de rastreabilidade (transições de estado, caixas, empenhos,
inventário, indicadores...) vivem em ``providers/implementations/opme/`` —
portadas sem alteração de comportamento da versão 17 e cobertas pela suíte de
testes. Cada serviço executa SQL nativo sobre a conexão aberta pela camada
Resource (``src/resources/opme_sqlite.py``) e devolve listas de dicionários.
"""
import importlib
from types import ModuleType

from ..interfaces.opme_provider_interface import OpmeProviderInterface
from ...resources.opme_sqlite import verificar_conexao


class OpmeSqliteProvider(OpmeProviderInterface):
    """Implementação do contrato sobre o banco SQLite ``opme.db``."""

    PACOTE = __package__ + ".opme"

    def inicializar(self) -> None:
        """Abertura do banco, na mesma ordem da versão 17 (app/main.py)."""
        from .opme import db, log
        from .opme.config import DB_PATH
        db.inicializar()
        # Carrega no histórico de sugestões o que unidades já cadastradas antes
        # desta versão já tinham de marca/fabricante.
        self.servico("estoque").backfilar_historico()
        # A cópia é feita depois da migração e antes de qualquer uso: se algo der
        # errado no dia, o ponto de retorno é o banco como estava ao abrir.
        self.servico("backup").copiar()
        # Caixa em estado diferente do próprio conteúdo passa a estar onde os
        # itens estão. Ver caixas.reconciliar.
        self.servico("caixas").reconciliar()
        log.info(f"aplicação iniciada · banco={DB_PATH}")

    def verificar(self) -> bool:
        return verificar_conexao()

    def servico(self, nome: str) -> ModuleType:
        return importlib.import_module(f"{self.PACOTE}.services.{nome}")
