"""Router — Chamados ("Reportar problema"), nov/2026.

Abrir chamado: qualquer usuário logado. Lista, resposta e imagens: Administração.
"""

from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import chamados_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/chamados",
    tags=["Chamados"],
    dependencies=[Depends(auth_handler.decode_token)],
)


@router.get("")
async def lista(request: Request, status: str = "", req: Requisicao = Depends(obter_requisicao)):
    """Administração: GET /chamados"""
    return await executar(request, req, controller.lista, status=status)


@router.post("/abrir")
async def abrir(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Qualquer usuário: abre um chamado (JSON: descricao, imagem, pagina, versao)."""
    return await executar(request, req, controller.abrir)


@router.get("/meus")
async def meus(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Chamados do próprio usuário (últimos 10)."""
    return await executar(request, req, controller.meus)


@router.post("/{id_chamado}/atualizar")
async def atualizar(request: Request, id_chamado: str, req: Requisicao = Depends(obter_requisicao)):
    """Administração: muda a situação e responde."""
    return await executar(request, req, controller.atualizar, id_chamado=id_chamado)


@router.get("/imagem/{nome}")
async def imagem(request: Request, nome: str, req: Requisicao = Depends(obter_requisicao)):
    """Administração: imagem anexada ao chamado."""
    return await executar(request, req, controller.imagem, nome=nome)
