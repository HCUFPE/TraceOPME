"""Router — Consignados (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/consignados_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import consignados_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/consignados",
    tags=["Consignados"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: GET /consignados"""
    return await executar(request, req, controller.hub)


@router.get("/pendentes")
async def pendentes(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: GET /consignados/pendentes"""
    return await executar(request, req, controller.pendentes)


@router.post("/vincular")
async def vincular(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: POST /consignados/vincular"""
    return await executar(request, req, controller.vincular, id_unidade=req.campo("id_unidade", ""), id_empenho=req.campo("id_empenho", ""), observacao=req.campo("observacao", ""))


@router.get("/empenhos")
async def lista_empenhos(
    request: Request,
    fornecedor: str = "",
    status: str = "",
    termo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: GET /consignados/empenhos"""
    return await executar(request, req, controller.lista_empenhos, fornecedor=fornecedor, status=status, termo=termo)


@router.get("/empenhos/novo")
async def novo_empenho(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: GET /consignados/empenhos/novo"""
    return await executar(request, req, controller.novo_empenho)


@router.post("/empenhos/novo")
async def criar_empenho(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: POST /consignados/empenhos/novo"""
    return await executar(request, req, controller.criar_empenho)


@router.post("/empenhos/importar")
async def importar_empenhos(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — cadastra empenhos a partir de uma planilha (.xlsx ou .csv)."""
    return await executar(request, req, controller.importar_empenhos)


@router.get("/empenhos/{id_empenho}/pdf")
async def pdf_empenho(
    request: Request,
    id_empenho: str,
    inicio: str = "",
    fim: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — materiais vinculados ao empenho, em PDF, no período escolhido."""
    return await executar(request, req, controller.pdf_empenho, id_empenho=id_empenho, inicio=inicio, fim=fim)


@router.get("/empenhos/{id_empenho}")
async def detalhe_empenho(
    request: Request,
    id_empenho: str,
    inicio: str = "",
    fim: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: GET /consignados/empenhos/{id_empenho}"""
    return await executar(request, req, controller.detalhe_empenho, id_empenho=id_empenho, inicio=inicio, fim=fim)


@router.post("/empenhos/{id_empenho}/encerrar")
async def encerrar_empenho(
    request: Request,
    id_empenho: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: POST /consignados/empenhos/{id_empenho}/encerrar"""
    return await executar(request, req, controller.encerrar_empenho, id_empenho=id_empenho, motivo=req.campo("motivo", ""))


@router.post("/vinculo/{id_vinculo}/cancelar")
async def cancelar_vinculo(
    request: Request,
    id_vinculo: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consignados: POST /consignados/vinculo/{id_vinculo}/cancelar"""
    return await executar(request, req, controller.cancelar_vinculo, id_vinculo=id_vinculo, motivo=req.campo("motivo", ""))


# ---------------------------------------------------------------- nov/2026: código consignado ↔ AGHU

@router.get("/associacoes")
async def associacoes(
    request: Request,
    termo: str = "",
    editar: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Associações código consignado ↔ código AGHU."""
    return await executar(request, req, controller.associacoes, termo=termo, editar=editar)


@router.get("/associacoes/consultar")
async def associacao_consultar(
    request: Request,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """AGHU associado a um código consignado (JSON)."""
    return await executar(request, req, controller.associacao_consultar, codigo=codigo)


@router.post("/associacoes")
async def associacao_salvar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Cria ou atualiza uma associação."""
    return await executar(request, req, controller.associacao_salvar,
                          codigo_consignado=req.campo("codigo_consignado", ""), codigo_aghu=req.campo("codigo_aghu", ""),
                          fornecedor=req.campo("fornecedor", ""), descricao=req.campo("descricao", ""))


@router.post("/associacoes/excluir")
async def associacao_excluir(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Exclui uma associação (se não estiver em empenho ativo)."""
    return await executar(request, req, controller.associacao_excluir,
                          codigo_consignado=req.campo("codigo_consignado", ""))


@router.post("/associacoes/importar")
async def associacoes_importar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Importa associações de uma planilha (Código consignado, Código AGHU)."""
    return await executar(request, req, controller.associacoes_importar)
