"""Router — Perfil do usuário e metadados do sistema (TraceOPME).

Protegido por padrão (Default-Private Router Pattern).
"""
from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import perfil_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api",
    tags=["Perfil"],
    dependencies=[Depends(auth_handler.decode_token)],
)


@router.get("/perfil")
async def perfil(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Tela "Meu perfil"."""
    return await executar(request, req, controller.perfil)


@router.post("/minha-senha")
async def trocar_senha(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Troca da própria senha (modo local)."""
    return await executar(request, req, controller.trocar_senha,
                          senha_atual=req.campo("senha_atual", ""),
                          nova_senha=req.campo("nova_senha", ""),
                          confirmar=req.campo("confirmar", ""))


@router.get("/sistema/meta")
async def meta(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Rótulos e listas do domínio (estados, operações, unidades, farmácias...)."""
    return await executar(request, req, controller.meta)
