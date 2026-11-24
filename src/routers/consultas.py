"""Router — Consultas (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/consultas_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import consultas_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/consultas",
    tags=["Consultas"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas"""
    return await executar(request, req, controller.hub)


@router.get("/itens")
async def itens(
    request: Request,
    busca: str = "",
    status: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/itens"""
    return await executar(request, req, controller.itens, busca=busca, status=status)


@router.get("/item/{id_unidade}")
async def item(
    request: Request,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/item/{id_unidade}"""
    return await executar(request, req, controller.item, id_unidade=id_unidade)


@router.get("/prontuario")
async def prontuario(
    request: Request,
    numero: str = "",
    formato: str = "",
    data: str | None = None,
    inicio: str = "",
    fim: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Ficha do paciente. Em `formato=txt` ou `pdf`, sai o descritivo cirúrgico.
    
    `data` recorta por procedimento. Sem ela (primeira consulta), abre no
    procedimento mais recente — é a cirurgia que está sendo documentada.
    `data=todas` mostra o histórico completo do paciente."""
    return await executar(request, req, controller.prontuario, numero=numero, formato=formato, data=data,
                          inicio=inicio, fim=fim)


@router.get("/classificacao")
async def classificacao(
    request: Request,
    inicio: str = "",
    fim: str = "",
    tipo_entrada: str = "",
    fornecedor: str = "",
    base: str = "entrada",
    detalhado: int = 1,
    exportar: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Material por classificação (consignado, aquisição própria…) em um período.
    
    Duas leituras dos mesmos filtros: o resumo agrupa por produto e serve à
    prestação de contas; o detalhado abre uma linha por material, com paciente,
    lote, validade e série — é o que se manda ao fornecedor para ele emitir a
    nota do consignado. A tela abre no detalhado porque é esse o uso do dia a
    dia; o resumo fica a um clique."""
    return await executar(request, req, controller.classificacao, inicio=inicio, fim=fim, tipo_entrada=tipo_entrada, fornecedor=fornecedor, base=base, detalhado=detalhado, exportar=exportar)


@router.get("/lote")
async def lote(
    request: Request,
    termo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/lote"""
    return await executar(request, req, controller.lote, termo=termo)


@router.get("/recall")
async def lista_recall(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/recall"""
    return await executar(request, req, controller.lista_recall)


@router.post("/recall")
async def criar_recall(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: POST /consultas/recall"""
    return await executar(request, req, controller.criar_recall)


@router.get("/recall/{id_bloqueio}")
async def detalhe_recall(
    request: Request,
    id_bloqueio: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/recall/{id_bloqueio}"""
    return await executar(request, req, controller.detalhe_recall, id_bloqueio=id_bloqueio)


@router.post("/recall/{id_bloqueio}/liberar")
async def liberar_recall(
    request: Request,
    id_bloqueio: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: POST /consultas/recall/{id_bloqueio}/liberar"""
    return await executar(request, req, controller.liberar_recall, id_bloqueio=id_bloqueio, motivo=req.campo("motivo", ""))


@router.get("/utilizados")
async def utilizados(
    request: Request,
    inicio: str = "",
    fim: str = "",
    prontuario: str = "",
    sala: str = "",
    especialidade: str = "",
    produto: str = "",
    exportar: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/utilizados"""
    return await executar(request, req, controller.utilizados, inicio=inicio, fim=fim, prontuario=prontuario, sala=sala, especialidade=especialidade, produto=produto, exportar=exportar)


@router.get("/dispensas")
async def dispensas(
    request: Request,
    inicio: str = "",
    fim: str = "",
    tipo: str = "",
    farmacia: str = "",
    busca: str = "",
    exportar: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Relatório de todas as movimentações de dispensa no período:
    almoxarifado → farmácia e farmácia → sala."""
    return await executar(request, req, controller.dispensas, inicio=inicio, fim=fim, tipo=tipo, farmacia=farmacia, busca=busca, exportar=exportar)


@router.get("/validades")
async def validades(
    request: Request,
    exportar: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consultas: GET /consultas/validades"""
    return await executar(request, req, controller.validades, exportar=exportar)


@router.get("/eventos")
async def eventos(
    request: Request,
    inicio: str = "",
    fim: str = "",
    unidade: str = "",
    sala: str = "",
    prontuario: str = "",
    tipo: str = "",
    usuario: str = "",
    formato: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — histórico de movimentações com filtros (antes: só os últimos 200)."""
    return await executar(request, req, controller.eventos, inicio=inicio, fim=fim, unidade=unidade, sala=sala, prontuario=prontuario, tipo=tipo, usuario=usuario, formato=formato)


@router.get("/caixa/{id_caixa}")
async def caixa_no_momento(
    request: Request,
    id_caixa: str,
    evento: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — situação de uma caixa de consignado no momento de um movimento
    (ex.: a devolução), e a situação de agora."""
    return await executar(request, req, controller.caixa_no_momento, id_caixa=id_caixa, evento=evento)
