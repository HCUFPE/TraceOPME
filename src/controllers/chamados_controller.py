"""Controller — Chamados ("Reportar problema"), nov/2026."""

from fastapi import Request

MODULO_ADMIN = "admin"


async def abrir(request: Request):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_login
    from ..providers.implementations.opme.services import chamados
    usuario = exigir_login(request)
    corpo = await request.json()
    ok, mensagem, numero = chamados.abrir(corpo or {}, usuario)
    return JSONResponse({"ok": ok, "mensagem": mensagem, "numero": numero})


def meus(request: Request):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_login
    from ..providers.implementations.opme.services import chamados
    usuario = exigir_login(request)
    return JSONResponse({"chamados": chamados.meus(usuario["username"]), "situacoes": chamados.SITUACOES})


def lista(request: Request, status: str = ""):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import chamados
    exigir_modulo(request, MODULO_ADMIN)
    return render(request, "admin/chamados.html", {
        "chamados": chamados.listar(status), "status": status, "situacoes": chamados.SITUACOES,
        "abertos": chamados.contar_abertos()})


async def atualizar(request: Request, id_chamado: str):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import chamados
    usuario = exigir_modulo(request, MODULO_ADMIN)
    form = await request.form()
    ok, msg = chamados.atualizar(id_chamado, str(form.get("status") or ""), str(form.get("resposta") or ""),
                                 usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/chamados")


def imagem(request: Request, nome: str):
    from fastapi.responses import FileResponse, Response
    from ..helpers.web_helper import exigir_login
    from ..providers.implementations.opme.security import pode_acessar
    from ..providers.implementations.opme.services import chamados
    usuario = exigir_login(request)
    if not pode_acessar(usuario["papel"], MODULO_ADMIN):
        return Response("Sem acesso.", status_code=403)
    caminho = chamados.caminho_imagem(nome)
    if not caminho:
        return Response("Imagem não encontrada.", status_code=404)
    return FileResponse(caminho, media_type="image/png" if nome.endswith(".png") else "image/jpeg")
