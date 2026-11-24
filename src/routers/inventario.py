"""Router — Inventário (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/inventario_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import inventario_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/inventario",
    tags=["Inventário"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Inventário: GET /inventario"""
    return await executar(request, req, controller.hub)


@router.post("/novo")
async def novo(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Inventário: POST /inventario/novo"""
    return await executar(request, req, controller.novo, local=req.campo("local", ""), observacao=req.campo("observacao", ""))


@router.get("/{id_inventario}")
async def contagem(
    request: Request,
    id_inventario: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Inventário: GET /inventario/{id_inventario}"""
    return await executar(request, req, controller.contagem, id_inventario=id_inventario)


@router.post("/api/bipar")
async def api_bipar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Inventário: POST /inventario/api/bipar"""
    return await executar(request, req, controller.api_bipar)


@router.post("/{id_inventario}/encerrar")
async def encerrar(
    request: Request,
    id_inventario: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Inventário: POST /inventario/{id_inventario}/encerrar"""
    return await executar(request, req, controller.encerrar, id_inventario=id_inventario)


@router.get("/{id_inventario}/relatorio")
async def relatorio(
    request: Request,
    id_inventario: str,
    exportar: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Inventário: GET /inventario/{id_inventario}/relatorio"""
    return await executar(request, req, controller.relatorio, id_inventario=id_inventario, exportar=exportar)
