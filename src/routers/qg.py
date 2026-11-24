"""Router — QG da enfermagem (chamados das salas) — v18.3."""

from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import qg_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(prefix="/api/qg", tags=["QG da enfermagem"], dependencies=[Depends(auth_handler.decode_token)])


@router.get("")
async def painel(request: Request, unidade: str = "", req: Requisicao = Depends(obter_requisicao)):
    """Quadro do QG: GET /qg"""
    return await executar(request, req, controller.painel, unidade=unidade)


@router.get("/dados")
async def dados(request: Request, unidade: str = "", req: Requisicao = Depends(obter_requisicao)):
    """O quadro em JSON, para atualizar sozinho."""
    return await executar(request, req, controller.dados, unidade=unidade)


@router.post("/chamado/{id_chamado}/{acao}")
async def acao(request: Request, id_chamado: str, acao: str, req: Requisicao = Depends(obter_requisicao)):
    """direcionar / atender / cancelar um chamado (JSON)."""
    return await executar(request, req, controller.acao, id_chamado=id_chamado, acao=acao)
