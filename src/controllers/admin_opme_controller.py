"""Controller — Administração (TraceOPME).

Regras de tela do módulo, portadas de app/routers/admin.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/admin_opme.py.
Original:
    Administração: usuários e solicitações de acesso.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

from ..providers.implementations.opme import log
from ..providers.implementations.opme.security import PAPEIS
from ..providers.implementations.opme.services import usuarios

MODULO = "admin"


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "admin/hub.html", _contexto_hub())


def _contexto_hub(**extra) -> dict:
    from ..providers.implementations.opme.services import backup, materiais
    return {
        "usuarios": usuarios.listar(),
        "solicitacoes": usuarios.solicitacoes_pendentes(),
        "papeis": PAPEIS,
        "backup": backup.situacao(),
        "catalogo": materiais.situacao_catalogo(),
        "resultado_catalogo": None,
        "chamados_abertos": __import__("src.providers.implementations.opme.services.chamados",
                                       fromlist=["x"]).contar_abertos(),
    } | extra


async def atualizar_catalogo(request: Request, arquivo: UploadFile = None):
    """Sobe a planilha de materiais (MasterTools) e atualiza o catálogo.

    A tela responde aqui mesmo, sem redirecionar, para poder mostrar o resumo
    do que mudou — quantos códigos novos, alterados e ignorados.
    """
    from ..helpers.web_helper import avisar, render
    from ..providers.implementations.opme.services import materiais
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    conteudo = await arquivo.read() if arquivo else b""
    ok, mensagem, resumo = materiais.importar_planilha(
        conteudo, arquivo.filename if arquivo else "", usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return render(request, "admin/hub.html", _contexto_hub(resultado_catalogo=resumo or None))


def desbloquear_usuario(request: Request, username: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    quem = exigir_modulo(request, MODULO)
    ok, mensagem = usuarios.desbloquear(username, quem["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin")


def gerar_backup(request: Request):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import backup
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    caminho = backup.copiar(forcar=True)
    if caminho:
        st = backup.situacao()
        if st["externa_configurada"] and not st["externo_erro"]:
            avisar(request, f"Cópia gerada, conferida e enviada para a rede: {caminho.name}", "sucesso")
        elif st["externa_configurada"]:
            avisar(request, f"Cópia gerada ({caminho.name}), mas o envio para a rede falhou: {st['externo_erro']}", "erro")
        else:
            avisar(request, f"Cópia gerada: {caminho.name}. A pasta de rede ainda não está configurada.", "alerta")
    else:
        avisar(request, "Não foi possível gerar a cópia. Veja o diagnóstico técnico.", "erro")
    return redirecionar("/admin")


def diagnostico(request: Request, linhas: int = 200):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "admin/diagnostico.html", {
        "linhas": log.ultimas_linhas(linhas),
        "arquivo": str(log.ARQUIVO),
        "quantidade": linhas,
    })


def aprovar(request: Request, id_solicitacao: str, papel: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    admin = exigir_modulo(request, MODULO)
    ok, mensagem = usuarios.aprovar(id_solicitacao, admin["username"], papel)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin")


def rejeitar(request: Request, id_solicitacao: str, motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    admin = exigir_modulo(request, MODULO)
    ok, mensagem = usuarios.rejeitar(id_solicitacao, admin["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin")


def mudar_papel(request: Request, username: str, papel: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    admin = exigir_modulo(request, MODULO)
    ok, mensagem = usuarios.alterar_papel(username, papel, admin["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin")


def mudar_status(request: Request, username: str, status: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    admin = exigir_modulo(request, MODULO)
    ok, mensagem = usuarios.alterar_status(username, status, admin["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin")


# ---------------------------------------------------------
# v17 — códigos AGHU com entrega da caixa ao paciente
# ---------------------------------------------------------

def tela_entrega_paciente(request: Request):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import entrega_paciente
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "admin/entrega_paciente.html", {
        "codigos": entrega_paciente.listar(),
    })


def incluir_entrega_paciente(request: Request, codigos: str = (""),
                             observacao: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import entrega_paciente
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = entrega_paciente.marcar(codigos, observacao, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin/entrega-paciente")


def remover_entrega_paciente(request: Request, codigo: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import entrega_paciente
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = entrega_paciente.desmarcar(codigo, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/admin/entrega-paciente")
