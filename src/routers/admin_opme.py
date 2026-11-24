"""Router — Administração (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/admin_opme_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import admin_opme_controller as controller
from starlette.concurrency import run_in_threadpool

from ..helpers.web_helper import Requisicao, executar, obter_requisicao
from ..providers.implementations.opme.services import usuarios as _usuarios


async def _estado_usuario(username: str) -> dict | None:
    """Estado anterior do usuário, para a trilha de auditoria (dados_anteriores)."""
    return await run_in_threadpool(_usuarios.buscar, username)

router = APIRouter(
    prefix="/api/admin",
    tags=["Administração"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: GET /admin"""
    return await executar(request, req, controller.hub)


@router.post("/materiais")
async def atualizar_catalogo(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sobe a planilha de materiais (MasterTools) e atualiza o catálogo.
    
    A tela responde aqui mesmo, sem redirecionar, para poder mostrar o resumo
    do que mudou — quantos códigos novos, alterados e ignorados."""
    return await executar(request, req, controller.atualizar_catalogo, arquivo=req.arquivo("arquivo"))


@router.post("/usuarios/{username}/desbloquear")
async def desbloquear_usuario(
    request: Request,
    username: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/usuarios/{username}/desbloquear"""
    return await executar(request, req, controller.desbloquear_usuario, dados_anteriores=await _estado_usuario(username), username=username)


@router.post("/backup")
async def gerar_backup(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/backup"""
    return await executar(request, req, controller.gerar_backup)


@router.get("/diagnostico")
async def diagnostico(
    request: Request,
    linhas: int = 200,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: GET /admin/diagnostico"""
    return await executar(request, req, controller.diagnostico, linhas=linhas)


@router.post("/solicitacao/{id_solicitacao}/aprovar")
async def aprovar(
    request: Request,
    id_solicitacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/solicitacao/{id_solicitacao}/aprovar"""
    return await executar(request, req, controller.aprovar, id_solicitacao=id_solicitacao, papel=req.campo("papel", ""))


@router.post("/solicitacao/{id_solicitacao}/rejeitar")
async def rejeitar(
    request: Request,
    id_solicitacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/solicitacao/{id_solicitacao}/rejeitar"""
    return await executar(request, req, controller.rejeitar, id_solicitacao=id_solicitacao, motivo=req.campo("motivo", ""))


@router.post("/usuario/{username}/papel")
async def mudar_papel(
    request: Request,
    username: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/usuario/{username}/papel"""
    return await executar(request, req, controller.mudar_papel, dados_anteriores=await _estado_usuario(username), username=username, papel=req.campo("papel", ""))


@router.post("/usuario/{username}/status")
async def mudar_status(
    request: Request,
    username: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/usuario/{username}/status"""
    return await executar(request, req, controller.mudar_status, dados_anteriores=await _estado_usuario(username), username=username, status=req.campo("status", ""))


@router.get("/entrega-paciente")
async def tela_entrega_paciente(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: GET /admin/entrega-paciente"""
    return await executar(request, req, controller.tela_entrega_paciente)


@router.post("/entrega-paciente")
async def incluir_entrega_paciente(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/entrega-paciente"""
    return await executar(request, req, controller.incluir_entrega_paciente, codigos=req.campo("codigos", ""), observacao=req.campo("observacao", ""))


@router.post("/entrega-paciente/{codigo}/remover")
async def remover_entrega_paciente(
    request: Request,
    codigo: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Administração: POST /admin/entrega-paciente/{codigo}/remover"""
    return await executar(request, req, controller.remover_entrega_paciente, codigo=codigo)
