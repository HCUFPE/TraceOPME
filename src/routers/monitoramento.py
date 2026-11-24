"""Router — Central de monitoramento das salas de procedimento (v18.1)."""

from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import monitoramento_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/monitoramento",
    tags=["Monitoramento"],
    dependencies=[Depends(auth_handler.decode_token)],
)


@router.get("")
async def central(request: Request, unidade: str = "", data: str = "",
                  req: Requisicao = Depends(obter_requisicao)):
    """Central das salas: GET /monitoramento"""
    return await executar(request, req, controller.central, unidade=unidade, data=data)


@router.get("/dados")
async def dados(request: Request, unidade: str = "", data: str = "",
                req: Requisicao = Depends(obter_requisicao)):
    """Os dados da central (JSON), para atualizar sozinha."""
    return await executar(request, req, controller.dados, unidade=unidade, data=data)


@router.get("/procedimento/{id_atendimento}")
async def procedimento(request: Request, id_atendimento: str,
                       req: Requisicao = Depends(obter_requisicao)):
    """Linha do tempo de um procedimento (JSON)."""
    return await executar(request, req, controller.procedimento, id_atendimento=id_atendimento)
