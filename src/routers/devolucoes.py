"""Router — Devoluções (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/devolucoes_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import devolucoes_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/devolucoes",
    tags=["Devoluções"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("/atendimento/{id_atendimento}")
async def do_atendimento(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções: GET /devolucoes/atendimento/{id_atendimento}"""
    return await executar(request, req, controller.do_atendimento, id_atendimento=id_atendimento)


@router.get("/{id_devolucao}")
async def ficha(
    request: Request,
    id_devolucao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções: GET /devolucoes/{id_devolucao}"""
    return await executar(request, req, controller.ficha, id_devolucao=id_devolucao)


@router.get("/{id_devolucao}/identificar")
async def identificar(
    request: Request,
    id_devolucao: str,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Conferência bipando: a tela pergunta qual linha o código lido atende."""
    return await executar(request, req, controller.identificar, id_devolucao=id_devolucao, codigo=codigo)


@router.post("/{id_devolucao}/confirmar")
async def confirmar(
    request: Request,
    id_devolucao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções: POST /devolucoes/{id_devolucao}/confirmar"""
    return await executar(request, req, controller.confirmar, id_devolucao=id_devolucao)


@router.post("/{id_devolucao}/incluir-sem-destino")
async def incluir_sem_destino(
    request: Request,
    id_devolucao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções: POST /devolucoes/{id_devolucao}/incluir-sem-destino"""
    return await executar(request, req, controller.incluir_sem_destino, id_devolucao=id_devolucao)


@router.post("/item/{id_item}/remover")
async def remover(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções: POST /devolucoes/item/{id_item}/remover"""
    return await executar(request, req, controller.remover, id_item=id_item)
