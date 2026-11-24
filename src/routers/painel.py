"""Router — Painel (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/painel_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import painel_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api",
    tags=["Painel"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("/")
async def inicio(
    request: Request,
    sem_permissao: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Painel: GET /"""
    return await executar(request, req, controller.inicio, sem_permissao=sem_permissao)


@router.post("/alertas/{id_alerta}/resolver")
async def resolver_alerta(
    request: Request,
    id_alerta: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Painel: POST /alertas/{id_alerta}/resolver"""
    return await executar(request, req, controller.resolver_alerta, id_alerta=id_alerta)
