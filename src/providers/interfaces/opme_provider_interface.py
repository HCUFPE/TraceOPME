"""Interface (contrato) do provedor de dados de rastreabilidade de OPME."""
from abc import ABC, abstractmethod
from types import ModuleType


class OpmeProviderInterface(ABC):
    """Contrato da fonte de dados do TraceOPME.

    O controller nunca sabe como os dados são guardados: ele usa os serviços
    de domínio expostos aqui (estoque, fluxo, caixas, empenhos, inventário...).
    """

    @abstractmethod
    def inicializar(self) -> None:
        """Cria/atualiza a estrutura do banco e roda as rotinas de abertura."""

    @abstractmethod
    def verificar(self) -> bool:
        """True se a fonte de dados responde (usado pelo /api/health)."""

    @abstractmethod
    def servico(self, nome: str) -> ModuleType:
        """Módulo de serviço de domínio pelo nome (ex.: 'estoque', 'fluxo')."""
