"""Router — Indicadores (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/indicadores_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import indicadores_controller as controller
from starlette.concurrency import run_in_threadpool

from ..helpers.web_helper import Requisicao, executar, obter_requisicao
from ..providers.implementations.opme.services import indicadores as _calc

router = APIRouter(
    prefix="/api/indicadores",
    tags=["Indicadores"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def hub(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores"""
    return await executar(request, req, controller.hub, inicio=inicio, fim=fim, unidade=unidade)


@router.get("/fluxo")
async def fluxo(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores/fluxo"""
    return await executar(request, req, controller.fluxo, inicio=inicio, fim=fim, unidade=unidade)


@router.get("/desperdicio")
async def desperdicio(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores/desperdicio"""
    return await executar(request, req, controller.desperdicio, inicio=inicio, fim=fim, unidade=unidade)


@router.get("/financeiro")
async def financeiro(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores/financeiro"""
    return await executar(request, req, controller.financeiro, inicio=inicio, fim=fim, unidade=unidade)


@router.get("/qualidade")
async def qualidade(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores/qualidade"""
    return await executar(request, req, controller.qualidade, inicio=inicio, fim=fim, unidade=unidade)


@router.get("/exportar")
async def exportar(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores/exportar"""
    return await executar(request, req, controller.exportar, inicio=inicio, fim=fim, unidade=unidade)


@router.get("/metas")
async def metas(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: GET /indicadores/metas"""
    return await executar(request, req, controller.metas)


@router.post("/metas/{codigo}")
async def salvar_meta(
    request: Request,
    codigo: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Indicadores: POST /indicadores/metas/{codigo}"""
    anterior = (await run_in_threadpool(_calc.metas_atuais)).get(codigo)
    return await executar(request, req, controller.salvar_meta, dados_anteriores=anterior, codigo=codigo, meta=req.campo("meta", ""), atencao=req.campo("atencao", ""), acao=req.campo("acao", "salvar"))
