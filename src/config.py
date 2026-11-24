"""
Módulo Centralizado de Configurações e Validação de Segredos (Settings)
=======================================================================
Garante o Padrão de Governança de Variáveis de Ambiente (Env Vars & Secrets) do HC-UFPE.
Carrega o arquivo .env e valida se os parâmetros essenciais e chaves de segurança estão corretos.

Além das variáveis padrão do Framework SETISD, este módulo concentra as
variáveis do TraceOPME (prefixo ``OPME_``) — antes espalhadas em ``app/config.py``.
Nenhuma senha, DSN ou chave fica escrita no código: tudo vem do ``.env``.
"""

import os
import logging
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("config")

# Raiz do projeto (pasta que contém src/, frontend/, data/).
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    # 1. Configurações do Servidor
    ENV: str = os.getenv("ENV", "development").lower()
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").lower()
    RAW_ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
    ALLOWED_ORIGINS: List[str] = [
        origin.strip() for origin in RAW_ALLOWED_ORIGINS.split(",") if origin.strip()
    ]

    # 2. Provedores e Bancos de Dados
    PACIENTE_PROVIDER_TYPE: str = os.getenv("PACIENTE_PROVIDER_TYPE", "POSTGRES").upper()
    APP_DB_URL: str = os.getenv("APP_DB_URL", "sqlite+aiosqlite:///data/app.db")
    POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")
    ORACLE_DSN: str = os.getenv("ORACLE_DSN", "")

    # 3. Active Directory (LDAP)
    AD_URL: str = os.getenv("AD_URL", "")
    AD_BASEDN: str = os.getenv("AD_BASEDN", "DC=ebserhnet,DC=gov,DC=br")
    AD_BIND_USER: str = os.getenv("AD_BIND_USER", "")
    AD_BIND_PASSWORD: str = os.getenv("AD_BIND_PASSWORD", "")

    # 4. Segurança e Criptografia (JWT)
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
    JWT_EXP_HOURS: int = int(os.getenv("JWT_EXP_HOURS", "10"))
    REFRESH_TOKEN_EXP_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXP_DAYS", "30"))

    # 5. TraceOPME — banco local de rastreabilidade e regras do domínio
    # Banco SQLite único do TraceOPME (o mesmo arquivo opme.db da versão 17:
    # basta copiá-lo para data/ para manter todo o histórico).
    OPME_DB_PATH: Path = Path(os.getenv("OPME_DB", str(BASE_DIR / "data" / "opme.db")))
    # Diário técnico (logs/opme.log). Nunca recebe dado clínico.
    OPME_LOG_DIR: Path = Path(os.getenv("OPME_LOG_DIR", str(BASE_DIR / "logs")))
    OPME_ORG: str = os.getenv("OPME_ORG", "")
    # Trava de login: após N erros seguidos a conta fica bloqueada por M minutos.
    OPME_TENTATIVAS: int = int(os.getenv("OPME_TENTATIVAS", "5"))
    OPME_MINUTOS_BLOQUEIO: int = int(os.getenv("OPME_MINUTOS_BLOQUEIO", "15"))
    # Primeiro acesso: criado apenas se não existir nenhum usuário no banco.
    # Com o AD ligado, use em OPME_ADMIN o login de rede do administrador.
    OPME_ADMIN: str = os.getenv("OPME_ADMIN", "admin")
    OPME_ADMIN_SENHA: str = os.getenv("OPME_ADMIN_SENHA", "admin")
    OPME_DIAS_VALIDADE: int = int(os.getenv("OPME_DIAS_VALIDADE", "90"))
    OPME_LIMIAR_EMPENHO: float = float(os.getenv("OPME_LIMIAR_EMPENHO", "0.8"))
    OPME_GRADE_CAIXAS: bool = os.getenv("OPME_GRADE_CAIXAS", "0") == "1"

    # 6. Agenda de procedimentos direto do relatórios (Metabase) — nov/2026
    METABASE_URL: str = os.getenv("METABASE_URL", "http://relatorios.hc-ufpe.ebserh")
    METABASE_USUARIO: str = os.getenv("METABASE_USUARIO", "")
    METABASE_SENHA: str = os.getenv("METABASE_SENHA", "")
    AGENDA_MODELO: str = os.getenv("AGENDA_MODELO", "1703")
    AGENDA_COLUNA_DATA: str = os.getenv("AGENDA_COLUNA_DATA", "")
    # 1 = busca sozinho todo dia nos horários abaixo (precisa de usuário e senha acima)
    AGENDA_AUTOMATICA: bool = os.getenv("AGENDA_AUTOMATICA", "0") == "1"
    AGENDA_HORARIOS: str = os.getenv("AGENDA_HORARIOS", "06:00")
    # Dias buscados a cada vez: 0 = hoje, 1 = amanhã (ex.: "0,1")
    AGENDA_DIAS: str = os.getenv("AGENDA_DIAS", "0")

    @classmethod
    def ad_configurado(cls) -> bool:
        """True quando o Active Directory real está configurado (não o gabarito)."""
        return bool(cls.AD_URL) and "ad.domain.local" not in cls.AD_URL

    @classmethod
    def validate_config(cls):
        """Valida a integridade das configurações e dispara avisos de segurança."""
        if cls.ENV == "production":
            if "change-in-production" in cls.JWT_SECRET or "SUA_CHAVE_SECRETA" in cls.JWT_SECRET:
                logger.error(
                    "❌ ERRO CRÍTICO DE SEGURANÇA: A variável 'JWT_SECRET' está usando a chave padrão. "
                    "Altere para uma chave secreta aleatória forte no arquivo .env antes de rodar em produção!"
                )
            if not cls.AD_URL:
                logger.warning(
                    "⚠️ AVISO: Variável 'AD_URL' não definida em produção. "
                    "O sistema está operando no modo local (senhas do próprio TraceOPME)."
                )
            if cls.OPME_ADMIN_SENHA == "admin":
                logger.warning(
                    "⚠️ AVISO: 'OPME_ADMIN_SENHA' está com o valor padrão. Troque a senha do "
                    "administrador inicial (ou use o AD) antes de liberar o sistema."
                )
        logger.info(f"Configurações carregadas com sucesso. Ambiente: '{cls.ENV.upper()}'")


# Instância global de configurações
settings = Settings()
settings.validate_config()
