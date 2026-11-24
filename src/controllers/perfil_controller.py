"""Controller — Perfil do usuário e metadados do TraceOPME.

Portado de app/routers/acesso.py (perfil e troca de senha) e dos "globals" que
os templates Jinja recebiam em app/main.py (rótulos de status, unidades,
operações...), agora entregues ao frontend Vue por /api/sistema/meta.
"""

from ..helpers.web_helper import Requisicao as Request
from ..helpers.web_helper import avisar, exigir_login, ir_para, render
from ..providers.implementations.opme import config as cfg
from ..providers.implementations.opme.domain import ESTADOS, OPERACOES
from ..providers.implementations.opme.security import (
    MODULOS, PAPEIS, modo_autenticacao, modulos_do_papel,
)
from ..providers.implementations.opme.services import usuarios


def perfil(request: Request):
    """Tela "Meu perfil": dados do acesso e troca de senha (modo local)."""
    usuario = exigir_login(request)
    return render(request, "perfil.html", {
        "perfil": usuario,
        "modulos": modulos_do_papel(usuario["papel"]),
        "modo_autenticacao": modo_autenticacao(),
    })


def trocar_senha(request: Request, senha_atual: str = "", nova_senha: str = "", confirmar: str = ""):
    """Troca da própria senha (só no modo local; com AD a senha é a da rede)."""
    usuario = exigir_login(request)
    if nova_senha != confirmar:
        avisar(request, "A confirmação não confere com a nova senha.", "erro")
        return ir_para("/perfil")
    ok, mensagem = usuarios.trocar_propria_senha(usuario["username"], senha_atual, nova_senha)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return ir_para("/perfil")


def meta(request: Request) -> dict:
    """Constantes do domínio usadas pelas telas (antes: globals dos templates)."""
    from ..providers.implementations.opme.services.relatorios import ROTULO_TIPO

    exigir_login(request)
    return {
        "app_title": cfg.APP_TITLE,
        "app_subtitle": cfg.APP_SUBTITLE,
        "organizacao": cfg.ORGANIZACAO,
        "estados": {k: {"rotulo": e.rotulo, "local": e.local, "cor": e.cor,
                        "descricao": e.descricao, "final": e.final} for k, e in ESTADOS.items()},
        "operacoes": {k: {"titulo": o.titulo, "modulo": o.modulo, "verbo": o.verbo}
                      for k, o in OPERACOES.items()},
        "modulos": MODULOS,
        "papeis": {k: v[0] for k, v in PAPEIS.items()},
        "unidades": cfg.UNIDADES,
        "unidades_ativas": list(cfg.UNIDADES_ATIVAS.keys()),
        "farmacias": cfg.FARMACIAS,
        "rotulo_especialidade": cfg.ROTULO_ESPECIALIDADE,
        "rotulo_tipo_evento": ROTULO_TIPO,
        "grade_ativa": cfg.GRADE_DAS_CAIXAS,
        "modo_autenticacao": modo_autenticacao(),
        "hoje": __import__("src.providers.implementations.opme.utils", fromlist=["x"]).hoje_iso(),
    }
