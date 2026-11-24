"""Router — Procedimentos (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/procedimentos_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import procedimentos_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/procedimentos",
    tags=["Procedimentos"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def lista(
    request: Request,
    data: str = "",
    unidade: str = "",
    sala: str = "",
    prontuario: str = "",
    so_opme: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Procedimentos: GET /procedimentos"""
    return await executar(request, req, controller.lista, data=data, unidade=unidade, sala=sala, prontuario=prontuario, so_opme=so_opme)


@router.post("")
async def abrir(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Procedimentos: POST /procedimentos"""
    return await executar(request, req, controller.abrir)


@router.post("/agenda")
async def importar_agenda(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Procedimentos: POST /procedimentos/agenda"""
    return await executar(request, req, controller.importar_agenda, arquivo=req.arquivo("arquivo"))


@router.post("/agenda/buscar")
async def buscar_agenda_metabase(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Busca a agenda do dia direto no relatórios (Metabase) e importa (nov/2026)."""
    return await executar(request, req, controller.buscar_agenda_metabase, data=req.campo("data", ""),
                          usuario_rede=req.campo("usuario_rede", ""), senha=req.campo("senha", ""))
