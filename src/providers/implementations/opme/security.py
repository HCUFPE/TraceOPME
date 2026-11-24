"""Senhas e permissões.

A versão anterior guardava a senha em texto puro na coluna `usuarios.password`
e ainda mantinha a senha desejada em claro na tabela de recuperação. Aqui as
senhas são derivadas com PBKDF2-SHA256 e comparadas em tempo constante.
"""

import hashlib
import hmac
import os
import secrets

ITERACOES = 240_000


def gerar_hash(senha: str) -> str:
    if not senha:
        raise ValueError("Senha vazia.")
    sal = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${sal.hex()}${dk.hex()}"


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    if not senha or not hash_armazenado:
        return False
    try:
        algoritmo, iteracoes, sal_hex, esperado_hex = hash_armazenado.split("$")
    except ValueError:
        return False
    if algoritmo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(sal_hex), int(iteracoes)
    )
    return hmac.compare_digest(dk.hex(), esperado_hex)


# =========================================================
# VALIDAÇÃO DA SENHA PELO ACTIVE DIRECTORY (Framework SETISD)
# =========================================================
#
# Com o AD configurado (AD_URL no .env), a senha de login e TODAS as senhas de
# confirmação (entrega à sala, devolução à farmácia, reabertura pela supervisão,
# material não cadastrado) passam a ser conferidas no AD — a senha de rede da
# pessoa. O papel (RBAC) continua vindo da tabela local `usuarios`.
#
# `src/auth/auth.py` registra aqui o validador na subida da aplicação. Sem AD
# configurado, nada é registrado e valem as senhas locais (PBKDF2) — o modo
# de reserva para desenvolvimento e para uso offline.

_validador_externo = None


class AdIndisponivel(Exception):
    """O AD não respondeu (fora do ar, rede, configuração) — não é senha errada."""


def registrar_validador_externo(funcao) -> None:
    """`funcao(username, senha) -> dict | None` (ou None para voltar às senhas locais).

    Devolve os dados da pessoa no AD (``nome``, ``email``, ``setor``) quando o
    login e a senha conferem, ``None`` quando não conferem, e levanta
    ``AdIndisponivel`` quando não foi possível consultar o AD.
    """
    global _validador_externo
    _validador_externo = funcao


def autenticar_externo(username: str, senha: str) -> dict | None:
    """nov/2026: confere login e senha no AD e devolve os dados da pessoa (ou None).

    Pode levantar ``AdIndisponivel``. Sem AD configurado, devolve None.
    """
    if _validador_externo is None or not senha:
        return None
    resultado = _validador_externo(username, senha)
    if not resultado:
        return None
    return resultado if isinstance(resultado, dict) else {}


def modo_autenticacao() -> str:
    """'ad' quando a senha é conferida no Active Directory; 'local' caso contrário."""
    return "ad" if _validador_externo else "local"


def senha_confere(username: str, senha: str, hash_armazenado: str) -> bool:
    """Confere a senha do usuário: no AD, se configurado; senão, no hash local."""
    if not senha:
        return False
    if _validador_externo is not None:
        try:
            return bool(_validador_externo(username, senha))
        except Exception:  # inclui AdIndisponivel: sem AD não há como conferir
            return False
    return verificar_senha(senha, hash_armazenado)


def senha_forte(senha: str) -> tuple[bool, str]:
    if len(senha or "") < 8:
        return False, "A senha precisa ter pelo menos 8 caracteres."
    if senha.isdigit() or senha.isalpha():
        return False, "Use letras e números na senha."
    return True, ""


def token() -> str:
    return secrets.token_urlsafe(24)


# =========================================================
# PAPÉIS E MÓDULOS
# =========================================================

MODULOS = {
    "painel": "Painel",
    # v17 (out/2026): abrir procedimento é geral — sala, farmácia e supervisão.
    "procedimentos": "Procedimentos",
    "almoxarifado": "Almoxarifado",
    "farmacia": "Farmácia",
    "sala-procedimento": "Sala de procedimento",
    "consignados": "Consignados",
    "inventario": "Inventário",
    "consultas": "Consultas",
    "indicadores": "Indicadores",
    # v18.1: central de monitoramento das salas (só leitura).
    "monitoramento": "Central das salas",
    # v18.3: QG da enfermagem — recebe os chamados de maqueiro / limpeza das salas.
    "qg": "QG da enfermagem",
    "admin": "Administração",
}

PAPEIS = {
    "admin": ("Administrador",
              ["painel", "procedimentos", "almoxarifado", "farmacia", "sala-procedimento",
               "consignados", "inventario", "consultas", "indicadores", "monitoramento", "qg", "admin"]),
    # v17: sem farmácia no fluxo. O almoxarifado assume os consignados
    # (empenho/NF), que antes ficavam com a farmácia.
    "almoxarifado": ("Almoxarifado",
                    ["painel", "almoxarifado", "consignados", "inventario", "consultas",
                     "indicadores"]),
    "sala-procedimento": ("Sala de procedimento",
                          ["painel", "procedimentos", "sala-procedimento", "monitoramento", "consultas", "indicadores"]),
    # v17: a farmácia monta e confere as caixas de consignado e confirma, com a
    # senha, a devolução do que a sala não utilizou.
    "farmacia": ("Farmácia", ["painel", "procedimentos", "farmacia", "monitoramento", "consultas", "inventario"]),
    # v17: reabre atendimento encerrado (com a própria senha, na hora).
    "supervisao": ("Supervisão",
                   ["painel", "procedimentos", "sala-procedimento", "monitoramento", "qg", "consultas", "indicadores"]),
    "gestao": ("Gestão / Coordenação",
               ["painel", "procedimentos", "monitoramento", "qg", "consignados", "inventario", "consultas", "indicadores"]),
    # v18.3: quem fica no QG da enfermagem e direciona maqueiro / limpeza.
    "qg_enfermagem": ("QG da enfermagem", ["painel", "qg", "monitoramento"]),
    "consulta": ("Somente consulta", ["painel", "consultas"]),
}

# Papéis renomeados na versão 15. Usuários gravados com o nome antigo continuam
# valendo: `db._migrar` converte na abertura do banco.
PAPEIS_RENOMEADOS = {
    "recebimento": "almoxarifado",
    "bloco": "sala-procedimento",
}


def modulos_do_papel(papel: str) -> list[str]:
    return PAPEIS.get(papel, PAPEIS["consulta"])[1]


def rotulo_papel(papel: str) -> str:
    return PAPEIS.get(papel, ("Desconhecido", []))[0]


def pode_acessar(papel: str, modulo: str) -> bool:
    return modulo in modulos_do_papel(papel)


# Quem pode autorizar a reabertura de um atendimento encerrado.
PAPEIS_REABRIR = ("supervisao", "admin")
