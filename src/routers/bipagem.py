"""Router — Bipagem (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/bipagem_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import bipagem_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao
from ..providers.implementations.opme.domain import EM_ESTOQUE_RECEBIMENTO  # v18.4.2: faltava (NameError)

router = APIRouter(
    prefix="/api",
    tags=["Bipagem"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("/bipagem/{operacao}")
async def tela(
    request: Request,
    operacao: str,
    atendimento: str = "",
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Bipagem: GET /bipagem/{operacao}"""
    return await executar(request, req, controller.tela, operacao=operacao, atendimento=atendimento, busca=busca)


@router.post("/abrir-sala")
async def api_abrir_sala(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.10: abre a sala do atendimento na própria tela de registrar uso."""
    return await executar(request, req, controller.api_abrir_sala)


@router.post("/abrir-entrega")
async def api_abrir_entrega(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Confere a senha de quem recebe UMA vez, para abrir a entrega na tela.
    
    Não move nada e não substitui nada: cada leitura continua autenticando a
    senha por conta própria, então todo evento gravado é individualmente
    confirmado. Isto existe só para a tela poder dizer "entrega aberta por
    Fulano" antes da primeira leitura — antes, a senha errada só aparecia como
    tarja vermelha no primeiro material bipado, o que parece defeito do sistema
    e ensina a equipe a ignorar mensagem vermelha."""
    return await executar(request, req, controller.api_abrir_entrega)


@router.post("/bipar")
async def api_bipar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Bipagem: POST /bipar"""
    return await executar(request, req, controller.api_bipar)


@router.post("/avaria")
async def api_avaria(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18: sinaliza problema (caiu, danificado…) num material já registrado no paciente."""
    return await executar(request, req, controller.api_avaria)


@router.post("/excluir-uso")
async def api_excluir_uso(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Registro de uso: exclui, na própria tela de bipagem, um bip feito por engano.
    
    Mesma regra da tela de conclusão (fluxo.excluir_bip): motivo obrigatório,
    nada é apagado do histórico, e o item volta para onde estava antes do uso
    (na sala, se tinha sido dispensado; senão, ao estoque). Depois de finalizar
    os materiais utilizados não se exclui mais por aqui."""
    return await executar(request, req, controller.api_excluir_uso)


@router.get("/selecao-manual")
async def api_selecao_manual(
    request: Request,
    operacao: str = "",
    aghu: str = "",
    atendimento: str = "",
    caixa: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 (out/2026): lista por lote e validade para quem não conseguiu bipar."""
    return await executar(request, req, controller.api_selecao_manual, operacao=operacao, aghu=aghu, atendimento=atendimento, caixa=caixa)


@router.post("/ciencia-entrega")
async def api_ciencia_entrega(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — ciência de que a caixa do material vai ser entregue ao paciente."""
    return await executar(request, req, controller.api_ciencia_entrega)


@router.post("/desfazer")
async def api_desfazer(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Bipagem: POST /desfazer"""
    return await executar(request, req, controller.api_desfazer)


@router.post("/bipagem/{operacao}/pendencias")
async def tratar_pendencias(
    request: Request,
    operacao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Bipagem: POST /bipagem/{operacao}/pendencias"""
    return await executar(request, req, controller.tratar_pendencias, operacao=operacao, ids=req.lista("ids"), motivo=req.campo("motivo", ""), destino=req.campo("destino", EM_ESTOQUE_RECEBIMENTO), atendimento=req.campo("atendimento", ""))
