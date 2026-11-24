"""Router — Sala de procedimento (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/sala_procedimento_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import sala_procedimento_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao
from ..providers.implementations.opme.domain import EM_ESTOQUE_RECEBIMENTO  # v18.4.2: faltava (NameError)

router = APIRouter(
    prefix="/api/sala-procedimento",
    tags=["Sala de procedimento"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.post("/unidade")
async def escolher_unidade(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/unidade"""
    return await executar(request, req, controller.escolher_unidade, unidade=req.campo("unidade", ""), proximo=req.campo("proximo", ""))


@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento"""
    return await executar(request, req, controller.hub)


@router.get("/caixas")
async def caixas_na_sala(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/caixas"""
    return await executar(request, req, controller.caixas_na_sala)


@router.get("/caixas/identificar")
async def caixas_identificar(
    request: Request,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/caixas/identificar"""
    return await executar(request, req, controller.caixas_identificar, codigo=codigo)


@router.post("/caixas/receber")
async def caixas_receber(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/caixas/receber"""
    return await executar(request, req, controller.caixas_receber)


@router.post("/caixas/{id_turno}/devolver")
async def caixas_devolver(
    request: Request,
    id_turno: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/caixas/{id_turno}/devolver"""
    return await executar(request, req, controller.caixas_devolver, id_turno=id_turno)


@router.get("/atendimentos")
async def lista_atendimentos(
    request: Request,
    data: str = "",
    sala: str = "",
    unidade: str | None = None,
    prontuario: str = "",
    operacao: str = "registrar_uso",
    so_opme: int = 1,
    mostrar: str = "",
    turno: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/atendimentos"""
    return await executar(request, req, controller.lista_atendimentos, data=data, sala=sala, unidade=unidade, prontuario=prontuario, operacao=operacao, so_opme=so_opme, turno=turno, mostrar=mostrar)


@router.post("/atendimentos")
async def criar_atendimento(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimentos"""
    return await executar(request, req, controller.criar_atendimento)


@router.post("/agenda")
async def importar_agenda(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/agenda"""
    return await executar(request, req, controller.importar_agenda, arquivo=req.arquivo("arquivo"))


@router.get("/atendimento/{id_atendimento}")
async def detalhe_atendimento(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/atendimento/{id_atendimento}"""
    return await executar(request, req, controller.detalhe_atendimento, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}")
async def salvar_atendimento(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}"""
    return await executar(request, req, controller.salvar_atendimento, id_atendimento=id_atendimento)


@router.get("/correcao-uso")
async def tela_correcao_uso(
    request: Request,
    atendimento: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/correcao-uso (v18.37)"""
    return await executar(request, req, controller.tela_correcao_uso, atendimento=atendimento)


@router.post("/correcao-uso/{id_usado}")
async def executar_correcao_uso(
    request: Request,
    id_usado: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/correcao-uso/{id_usado}"""
    return await executar(request, req, controller.executar_correcao_uso, id_usado=id_usado,
                          id_na_sala=req.campo("id_na_sala", ""), motivo=req.campo("motivo", ""))


@router.get("/estorno")
async def tela_estorno(
    request: Request,
    prontuario: str = "",
    atendimento: str = "",
    inicio: str = "",
    fim: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/estorno (v18: por paciente, com período)"""
    return await executar(request, req, controller.tela_estorno, prontuario=prontuario, atendimento=atendimento,
                          inicio=inicio, fim=fim)


@router.post("/estorno/{id_unidade}")
async def executar_estorno(
    request: Request,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/estorno/{id_unidade}"""
    return await executar(request, req, controller.executar_estorno, id_unidade=id_unidade, motivo=req.campo("motivo", ""), destino=req.campo("destino", EM_ESTOQUE_RECEBIMENTO), prontuario=req.campo("prontuario", ""))


@router.post("/atendimento/{id_atendimento}/passar-sala")
async def passar_sala(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.13.1: POST /sala-procedimento/atendimento/{id_atendimento}/passar-sala"""
    return await executar(request, req, controller.passar_sala, id_atendimento=id_atendimento,
                          destino=req.campo("destino", ""), motivo=req.campo("motivo", ""))


@router.post("/atendimento/{id_atendimento}/finalizar-uso")
async def finalizar_uso(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 (out/2026): a sala finaliza os materiais utilizados. O que sobrou do
    que a farmácia dispensou vai, sozinho, para a lista de não utilizados; o
    encerramento é da farmácia, depois da ciência."""
    return await executar(request, req, controller.finalizar_uso, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}/encerrar")
async def finalizar_uso_1(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 (out/2026): a sala finaliza os materiais utilizados. O que sobrou do
    que a farmácia dispensou vai, sozinho, para a lista de não utilizados; o
    encerramento é da farmácia, depois da ciência."""
    return await executar(request, req, controller.finalizar_uso, id_atendimento=id_atendimento)


@router.get("/atendimento/{id_atendimento}/concluir")
async def concluir(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Revisão antes de encerrar: o que foi bipado, com opção de excluir um bip."""
    return await executar(request, req, controller.concluir, id_atendimento=id_atendimento)


@router.get("/atendimento/{id_atendimento}/sobras/identificar")
async def sobras_identificar(
    request: Request,
    id_atendimento: str,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/atendimento/{id_atendimento}/sobras/identificar"""
    return await executar(request, req, controller.sobras_identificar, id_atendimento=id_atendimento, codigo=codigo)


@router.post("/atendimento/{id_atendimento}/excluir/{id_unidade}")
async def excluir_bip(
    request: Request,
    id_atendimento: str,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/excluir/{id_unidade}"""
    return await executar(request, req, controller.excluir_bip, id_atendimento=id_atendimento, id_unidade=id_unidade, motivo=req.campo("motivo", ""))


@router.post("/atendimento/{id_atendimento}/ciencia/{id_unidade}")
async def dar_ciencia(
    request: Request,
    id_atendimento: str,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/ciencia/{id_unidade}"""
    return await executar(request, req, controller.dar_ciencia, id_atendimento=id_atendimento, id_unidade=id_unidade)


@router.post("/atendimento/{id_atendimento}/reabrir")
async def reabrir(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/reabrir"""
    return await executar(request, req, controller.reabrir, id_atendimento=id_atendimento, usuario_supervisao=req.campo("usuario_supervisao", ""), senha_supervisao=req.campo("senha_supervisao", ""), motivo=req.campo("motivo", ""))


@router.post("/atendimento/{id_atendimento}/cancelar")
async def cancelar(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — procedimento previsto que não aconteceu."""
    return await executar(request, req, controller.cancelar, id_atendimento=id_atendimento, motivo=req.campo("motivo", ""), detalhe=req.campo("detalhe", ""))


@router.post("/atendimento/{id_atendimento}/descancelar")
async def descancelar(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.43 — cancelamento por engano: o procedimento volta a ficar aberto."""
    return await executar(request, req, controller.descancelar, id_atendimento=id_atendimento,
                          motivo=req.campo("motivo", ""))


@router.post("/atendimento/{id_atendimento}/abrir-sala")
async def abrir_sala(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.3 — a sala registra que abriu para este procedimento."""
    return await executar(request, req, controller.abrir_sala, id_atendimento=id_atendimento,
                          voltar=req.campo("voltar", ""))


@router.get("/salas")
async def salas(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.3 — Salas: abrir a sala para o paciente e seguir o fluxo."""
    return await executar(request, req, controller.salas)


@router.post("/atendimento/{id_atendimento}/chamado")
async def chamar(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.3 — chamar maqueiro / limpeza (vai para o QG da enfermagem)."""
    return await executar(request, req, controller.chamar, id_atendimento=id_atendimento,
                          tipo=req.campo("tipo", ""), motivo=req.campo("motivo", ""),
                          observacao=req.campo("observacao", ""))


@router.post("/salas/chamado")
async def chamar_sala(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.3 — chamar maqueiro / limpeza pela aba Salas."""
    return await executar(request, req, controller.chamar_sala, sala=req.campo("sala", ""),
                          tipo=req.campo("tipo", ""), motivo=req.campo("motivo", ""),
                          observacao=req.campo("observacao", ""))


@router.post("/chamado/{id_chamado}/cancelar")
async def cancelar_chamado(
    request: Request,
    id_chamado: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.3 — a sala cancela um chamado que ainda não foi atendido."""
    return await executar(request, req, controller.cancelar_chamado, id_chamado=id_chamado,
                          voltar=req.campo("voltar", ""))


@router.get("/atendimento/{id_atendimento}/solicitacao")
async def solicitacao_tela(
    request: Request,
    id_atendimento: str,
    formulario: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/atendimento/{id_atendimento}/solicitacao"""
    return await executar(request, req, controller.solicitacao_tela, id_atendimento=id_atendimento, formulario=formulario)


@router.post("/atendimento/{id_atendimento}/solicitacao")
async def solicitacao_salvar(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/solicitacao"""
    return await executar(request, req, controller.solicitacao_salvar, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}/solicitacao/cancelar")
async def solicitacao_cancelar(request: Request, id_atendimento: str, req: Requisicao = Depends(obter_requisicao)):
    """v18.7.3: a sala cancela a solicitação de OPME (com motivo)."""
    return await executar(request, req, controller.solicitacao_cancelar, id_atendimento=id_atendimento,
                          motivo=req.campo("motivo", ""))


@router.get("/solicitacao/buscar")
async def solicitacao_buscar(
    request: Request,
    q: str = "",
    formulario: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/solicitacao/buscar"""
    return await executar(request, req, controller.solicitacao_buscar, q=q, formulario=formulario)


@router.post("/atendimento/{id_atendimento}/solicitacao/incluir")
async def solicitacao_incluir(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/solicitacao/incluir"""
    return await executar(request, req, controller.solicitacao_incluir, id_atendimento=id_atendimento)


@router.get("/atendimento/{id_atendimento}/solicitacao/painel")
async def solicitacao_painel_sala(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/atendimento/{id_atendimento}/solicitacao/painel"""
    return await executar(request, req, controller.solicitacao_painel_sala, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}/solicitacao/avulso")
async def solicitacao_avulso(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/solicitacao/avulso"""
    return await executar(request, req, controller.solicitacao_avulso, id_atendimento=id_atendimento, codigo_aghu=req.campo("codigo_aghu", ""), descricao=req.campo("descricao", ""), quantidade=req.campo("quantidade", ""))


@router.post("/atendimento/{id_atendimento}/solicitacao/remover/{id_item}")
async def solicitacao_remover(
    request: Request,
    id_atendimento: str,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/solicitacao/remover/{id_item}"""
    return await executar(request, req, controller.solicitacao_remover, id_atendimento=id_atendimento, id_item=id_item)


@router.get("/atendimento/{id_atendimento}/nao-cadastrado")
async def nao_cadastrado_tela(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: GET /sala-procedimento/atendimento/{id_atendimento}/nao-cadastrado"""
    return await executar(request, req, controller.nao_cadastrado_tela, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}/nao-cadastrado")
async def nao_cadastrado_registrar(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Sala de procedimento: POST /sala-procedimento/atendimento/{id_atendimento}/nao-cadastrado"""
    return await executar(request, req, controller.nao_cadastrado_registrar, id_atendimento=id_atendimento)


@router.get("/nao-cadastrado/buscar")
async def nao_cadastrado_buscar(
    request: Request,
    q: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Sugestões de material (nome ou AGHU) para o registro de material não cadastrado."""
    return await executar(request, req, controller.nao_cadastrado_buscar, q=q)


@router.get("/nao-cadastrado/foto/{nome}")
async def nao_cadastrado_foto(
    request: Request,
    nome: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Foto da etiqueta do material não cadastrado."""
    return await executar(request, req, controller.nao_cadastrado_foto, nome=nome)
