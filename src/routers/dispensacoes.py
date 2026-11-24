"""Router — Dispensações (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/dispensacoes_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import dispensacoes_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/dispensacoes",
    tags=["Dispensações"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("/atendimento/{id_atendimento}")
async def do_atendimento(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Dispensações: GET /dispensacoes/atendimento/{id_atendimento}"""
    return await executar(request, req, controller.do_atendimento, id_atendimento=id_atendimento)


@router.get("/atendimento/{id_atendimento}/{acao}")
async def do_atendimento_acao(
    request: Request,
    id_atendimento: str,
    acao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — "Finalizar dispensa" e "Baixar PDF" a partir da tela de bipagem."""
    return await executar(request, req, controller.do_atendimento_acao, id_atendimento=id_atendimento, acao=acao)


@router.get("/{id_dispensacao}")
async def ficha(
    request: Request,
    id_dispensacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Dispensações: GET /dispensacoes/{id_dispensacao}"""
    return await executar(request, req, controller.ficha, id_dispensacao=id_dispensacao)


@router.get("/{id_dispensacao}/pdf")
async def pdf_dispensacao(
    request: Request,
    id_dispensacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — lista do material dispensado, em PDF, para acompanhar o material à sala."""
    return await executar(request, req, controller.pdf_dispensacao, id_dispensacao=id_dispensacao)


@router.get("/{id_dispensacao}/finalizada")
async def finalizada(
    request: Request,
    id_dispensacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — "Finalizar dispensa": resumo do que saiu para a sala, com o PDF."""
    return await executar(request, req, controller.finalizada, id_dispensacao=id_dispensacao)


@router.post("/{id_dispensacao}/confirmar")
async def confirmar(
    request: Request,
    id_dispensacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Dispensações: POST /dispensacoes/{id_dispensacao}/confirmar"""
    return await executar(request, req, controller.confirmar, id_dispensacao=id_dispensacao)


@router.get("/{id_dispensacao}/identificar")
async def identificar(
    request: Request,
    id_dispensacao: str,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Dispensações: GET /dispensacoes/{id_dispensacao}/identificar"""
    return await executar(request, req, controller.identificar, id_dispensacao=id_dispensacao, codigo=codigo)


@router.post("/item/{id_item}/remover")
async def remover(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Dispensações: POST /dispensacoes/item/{id_item}/remover"""
    return await executar(request, req, controller.remover, id_item=id_item)
