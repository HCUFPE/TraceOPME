"""Router — Farmácia (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/farmacia_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import farmacia_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/farmacia",
    tags=["Farmácia"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.post("/unidade")
async def escolher_unidade(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/unidade"""
    return await executar(request, req, controller.escolher_unidade, unidade=req.campo("unidade", ""), proximo=req.campo("proximo", ""))


@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia"""
    return await executar(request, req, controller.hub)


@router.get("/caixas-consignado")
async def caixas_consignado_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/caixas-consignado"""
    return await executar(request, req, controller.caixas_consignado_lista)


@router.post("/caixas-consignado")
async def caixas_consignado_criar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/caixas-consignado"""
    return await executar(request, req, controller.caixas_consignado_criar)


@router.get("/caixas-consignado/{id_caixa}/saidas")
async def caixa_consignado_saidas(
    request: Request,
    id_caixa: str,
    de: str = "",
    ate: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.11.7: GET /caixas-consignado/{id_caixa}/saidas — saídas da caixa por período"""
    return await executar(request, req, controller.caixa_consignado_saidas, id_caixa=id_caixa, de=de, ate=ate)


@router.get("/caixas-consignado/{id_caixa}")
async def caixa_consignado_ficha(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/caixas-consignado/{id_caixa}"""
    return await executar(request, req, controller.caixa_consignado_ficha, id_caixa=id_caixa)


@router.post("/caixas-consignado/{id_caixa}/adicionar")
async def caixa_consignado_adicionar(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Coloca um item na caixa. Aceita código de barras, série ou o código AGHU.
    
    Quando o código responde a mais de um lote/validade, a tela mostra as opções
    para a pessoa escolher — o sistema não escolhe sozinho."""
    return await executar(request, req, controller.caixa_consignado_adicionar, id_caixa=id_caixa, codigo=req.campo("codigo", ""), id_unidade=req.campo("id_unidade", ""), quantidade=req.campo("quantidade", "1"))


@router.post("/caixas-consignado/{id_caixa}/retirar/{id_unidade}")
async def caixa_consignado_retirar(
    request: Request,
    id_caixa: str,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/caixas-consignado/{id_caixa}/retirar/{id_unidade}"""
    return await executar(request, req, controller.caixa_consignado_retirar, id_caixa=id_caixa, id_unidade=id_unidade, motivo=req.campo("motivo", ""))


@router.post("/caixas-consignado/{id_caixa}/conferir")
async def caixa_consignado_conferir(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/caixas-consignado/{id_caixa}/conferir"""
    return await executar(request, req, controller.caixa_consignado_conferir, id_caixa=id_caixa)


@router.get("/caixas-consignado/{id_caixa}/etiqueta")
async def caixa_consignado_etiqueta(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/caixas-consignado/{id_caixa}/etiqueta"""
    return await executar(request, req, controller.caixa_consignado_etiqueta, id_caixa=id_caixa)


@router.get("/caixas-consignado/{id_caixa}/qr.png")
async def caixa_consignado_qr(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/caixas-consignado/{id_caixa}/qr.png"""
    return await executar(request, req, controller.caixa_consignado_qr, id_caixa=id_caixa)


@router.get("/caixas-sala")
async def caixas_sala_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/caixas-sala"""
    return await executar(request, req, controller.caixas_sala_lista)


@router.post("/caixas-sala/enviar")
async def caixas_sala_enviar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/caixas-sala/enviar"""
    return await executar(request, req, controller.caixas_sala_enviar, codigo=req.campo("codigo", ""), local=req.campo("local", ""))


@router.post("/caixas-sala/{id_turno}/cancelar")
async def caixas_sala_cancelar(
    request: Request,
    id_turno: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/caixas-sala/{id_turno}/cancelar"""
    return await executar(request, req, controller.caixas_sala_cancelar, id_turno=id_turno)


@router.get("/caixas-sala/{id_turno}")
async def caixa_sala_ficha(
    request: Request,
    id_turno: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/caixas-sala/{id_turno}"""
    return await executar(request, req, controller.caixa_sala_ficha, id_turno=id_turno)


@router.get("/caixas-sala/{id_turno}/identificar")
async def caixa_sala_identificar(
    request: Request,
    id_turno: str,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.2: conferência do retorno bipando (JSON)."""
    return await executar(request, req, controller.caixa_sala_identificar, id_turno=id_turno, codigo=codigo)


@router.post("/caixas-sala/{id_turno}/conferir")
async def caixa_sala_conferir(
    request: Request,
    id_turno: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/caixas-sala/{id_turno}/conferir"""
    return await executar(request, req, controller.caixa_sala_conferir, id_turno=id_turno)


@router.get("/devolucoes")
async def devolucoes_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — devoluções bipadas pela sala aguardando a senha da farmácia."""
    return await executar(request, req, controller.devolucoes_lista)


@router.get("/devolucoes/{id_devolucao}")
async def devolucao_ficha(
    request: Request,
    id_devolucao: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/devolucoes/{id_devolucao}"""
    return await executar(request, req, controller.devolucao_ficha, id_devolucao=id_devolucao)


@router.get("/procedimentos-a-concluir")
async def procedimentos_a_concluir(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/procedimentos-a-concluir"""
    return await executar(request, req, controller.procedimentos_a_concluir)


@router.get("/procedimento/{id_atendimento}")
async def procedimento(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/procedimento/{id_atendimento}"""
    return await executar(request, req, controller.procedimento, id_atendimento=id_atendimento)


@router.post("/procedimento/{id_atendimento}/receber")
async def procedimento_receber(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/procedimento/{id_atendimento}/receber"""
    return await executar(request, req, controller.procedimento_receber, id_atendimento=id_atendimento, id_unidade=req.campo("id_unidade", ""), id_caixa=req.campo("id_caixa", ""))


@router.post("/procedimento/{id_atendimento}/concluir")
async def procedimento_concluir(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/procedimento/{id_atendimento}/concluir"""
    return await executar(request, req, controller.procedimento_concluir, id_atendimento=id_atendimento)


@router.get("/atendimentos")
async def atendimentos_para_dispensar(
    request: Request,
    data: str = "",
    unidade: str = "",
    prontuario: str = "",
    operacao: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Escolha do paciente para dispensar. Mostra os atendimentos abertos do dia."""
    return await executar(request, req, controller.atendimentos_para_dispensar, data=data, unidade=unidade, prontuario=prontuario, operacao=operacao)


@router.get("/atendimento/{id_atendimento}")
async def atendimento_farmacia(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/atendimento/{id_atendimento}"""
    return await executar(request, req, controller.atendimento_farmacia, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}/cancelar")
async def atendimento_cancelar(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Procedimento cancelado antes de a sala receber o material: a farmácia
    cancela e o que ela dispensou volta direto para o estoque dela."""
    return await executar(request, req, controller.atendimento_cancelar, id_atendimento=id_atendimento, motivo=req.campo("motivo", ""), detalhe=req.campo("detalhe", ""), voltar=req.campo("voltar", ""))


@router.get("/estoque")
async def estoque_farmacia(
    request: Request,
    farmacia: str = "",
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Estoque de cada farmácia (Bloco e Hemodinâmica), por material, lote e validade."""
    return await executar(request, req, controller.estoque_farmacia, farmacia=farmacia, busca=busca)


@router.get("/recebimentos")
async def recebimentos(
    request: Request,
    todas: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Envios do almoxarifado para esta farmácia: conferir e dar ciência."""
    return await executar(request, req, controller.recebimentos, todas=todas)


@router.get("/recebimento/{id_remessa}")
async def recebimento_tela(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/recebimento/{id_remessa}"""
    return await executar(request, req, controller.recebimento_tela, id_remessa=id_remessa)


@router.get("/recebimento/{id_remessa}/identificar")
async def recebimento_identificar(
    request: Request,
    id_remessa: str,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/recebimento/{id_remessa}/identificar"""
    return await executar(request, req, controller.recebimento_identificar, id_remessa=id_remessa, codigo=codigo)


@router.post("/recebimento/{id_remessa}/conferir")
async def recebimento_conferir(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/recebimento/{id_remessa}/conferir"""
    return await executar(request, req, controller.recebimento_conferir, id_remessa=id_remessa)


@router.post("/recebimento/item/{id_item}/recebi")
async def recebimento_recebi_depois(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/recebimento/item/{id_item}/recebi"""
    return await executar(request, req, controller.recebimento_recebi_depois, id_item=id_item, voltar=req.campo("voltar", "/farmacia/recebimentos"))


@router.post("/recebimento/{id_remessa}/conferido")
async def recebimento_conferido(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/recebimento/{id_remessa}/conferido (bipe parcial)"""
    return await executar(request, req, controller.recebimento_conferido, id_remessa=id_remessa)


@router.get("/solicitacoes")
async def solicitacoes_em_aberto(
    request: Request,
    todas: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Pedidos de OPME da sala ainda não atendidos (qualquer data), da unidade
    que esta farmácia atende — ou de todas, se pedir."""
    return await executar(request, req, controller.solicitacoes_em_aberto, todas=todas)


@router.get("/atendimento/{id_atendimento}/solicitacao/imprimir")
async def solicitacao_imprimir(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: folha de separação do pedido, para imprimir."""
    return await executar(request, req, controller.solicitacao_imprimir, id_atendimento=id_atendimento)


@router.get("/atendimento/{id_atendimento}/solicitacao/painel")
async def solicitacao_painel(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Pedaço da tela de dispensar redesenhado a cada bip (a lista com os checks)."""
    return await executar(request, req, controller.solicitacao_painel, id_atendimento=id_atendimento)


@router.post("/atendimento/{id_atendimento}/solicitacao/manual/{id_item}")
async def solicitacao_manual(
    request: Request,
    id_atendimento: str,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Linha sem código AGHU (ex.: cateter diagnóstico, tipo escrito pela sala)."""
    return await executar(request, req, controller.solicitacao_manual, id_atendimento=id_atendimento, id_item=id_item, atendido=req.campo("atendido", "1"))


@router.post("/atendimento/{id_atendimento}/solicitacao/outro-codigo/{id_item}")
async def solicitacao_outro_codigo(
    request: Request,
    id_atendimento: str,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Item com AGHU atendido por material bipado com outro código (com motivo)."""
    return await executar(request, req, controller.solicitacao_outro_codigo, id_atendimento=id_atendimento, id_item=id_item)


@router.post("/atendimento/{id_atendimento}/solicitacao/falta/{id_item}")
async def solicitacao_falta(
    request: Request,
    id_atendimento: str,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.43: a farmácia marca a linha que não tem como atender (falta no estoque)."""
    return await executar(request, req, controller.solicitacao_falta,
                          id_atendimento=id_atendimento, id_item=id_item)


@router.post("/atendimento/{id_atendimento}/finalizar-dispensa")
async def finalizar_dispensa(
    request: Request,
    id_atendimento: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """"Finalizar dispensa": confere a solicitação da sala antes do resumo/PDF.
    Faltando item, exige o motivo (fica registrado e a sala vê)."""
    return await executar(request, req, controller.finalizar_dispensa, id_atendimento=id_atendimento, motivo=req.campo("motivo", ""))


@router.get("/dispensacoes")
async def dispensacoes_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: GET /farmacia/dispensacoes"""
    return await executar(request, req, controller.dispensacoes_lista)


@router.get("/usos-sem-dispensacao")
async def usos_sem_dispensacao_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — material usado na sala sem dispensação: a farmácia dá ciência."""
    return await executar(request, req, controller.usos_sem_dispensacao_lista)


@router.post("/usos-sem-dispensacao/ciencia")
async def usos_sem_dispensacao_ciencia(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia: POST /farmacia/usos-sem-dispensacao/ciencia"""
    return await executar(request, req, controller.usos_sem_dispensacao_ciencia)


@router.get("/conciliacao")
async def conciliacao(
    request: Request,
    inicio: str = "",
    fim: str = "",
    sala: str = "",
    unidade: str = "",
    prontuario: str = "",
    atendimento: str = "",
    formato: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — conciliação por sala: dispensado × usado × devolvido."""
    return await executar(request, req, controller.conciliacao, inicio=inicio, fim=fim, sala=sala, unidade=unidade, prontuario=prontuario, atendimento=atendimento, formato=formato)


# ---------------------------------------------------------------- nov/2026: devolver ao almoxarifado

@router.get("/devolucoes-almox")
async def devolucoes_almox(
    request: Request,
    todas: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções desta farmácia para o almoxarifado."""
    return await executar(request, req, controller.devolucoes_almox, todas=todas)


@router.post("/devolucoes-almox/novo")
async def devolucao_almox_nova(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Abre (ou continua) a devolução da farmácia escolhida."""
    return await executar(request, req, controller.devolucao_almox_nova, farmacia=req.campo("farmacia", ""))


@router.get("/devolucao-almox/{id_remessa}")
async def devolucao_almox_tela(
    request: Request,
    id_remessa: str,
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Montar a devolução bipando (ou ver uma devolução já finalizada)."""
    return await executar(request, req, controller.devolucao_almox_tela, id_remessa=id_remessa, busca=busca)


@router.post("/devolucao-almox/{id_remessa}/bipar")
async def devolucao_almox_bipar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Bipa um material na devolução (JSON)."""
    return await executar(request, req, controller.devolucao_almox_bipar, id_remessa=id_remessa)


@router.post("/devolucao-almox/item/{id_item}/tirar")
async def devolucao_almox_tirar(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Tira um item da devolução ainda aberta (JSON)."""
    return await executar(request, req, controller.devolucao_almox_tirar, id_item=id_item)


@router.post("/devolucao-almox/{id_remessa}/finalizar")
async def devolucao_almox_finalizar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Finaliza a devolução: o almoxarifado confere e dá ciência."""
    return await executar(request, req, controller.devolucao_almox_finalizar, id_remessa=id_remessa,
                          observacao=req.campo("observacao", ""))


@router.post("/devolucao-almox/{id_remessa}/cancelar")
async def devolucao_almox_cancelar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Cancela a devolução enquanto o almoxarifado não deu ciência."""
    return await executar(request, req, controller.devolucao_almox_cancelar, id_remessa=id_remessa,
                          motivo=req.campo("motivo", ""))


@router.post("/devolucao-almox/item/{id_item}/tratar")
async def devolucao_almox_tratar(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Tratativa do item que o almoxarifado não recebeu."""
    return await executar(request, req, controller.devolucao_almox_tratar, id_item=id_item,
                          acao=req.campo("acao", ""), motivo=req.campo("motivo", ""))


# ---------------------------------------------------------------- v18.4.3: não recebidos pela sala

@router.get("/nao-recebidos")
async def nao_recebidos(
    request: Request,
    todas: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Itens que a sala disse não ter recebido — a farmácia confere."""
    return await executar(request, req, controller.nao_recebidos, todas=todas)


@router.post("/nao-recebidos/{id_unidade}")
async def tratar_nao_recebido(
    request: Request,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Localizado / estava na sala / extraviado."""
    return await executar(request, req, controller.tratar_nao_recebido, id_unidade=id_unidade,
                          acao=req.campo("acao", ""), motivo=req.campo("motivo", ""))


# ---------------------------------------------------------------- v18.6: nota de consumo no AGHU

@router.get("/nota-consumo")
async def nota_consumo(request: Request, data: str = "", pendentes: int = 0,
                       req: Requisicao = Depends(obter_requisicao)):
    """Prontuários com uso no dia e o que foi bipado em cada paciente."""
    return await executar(request, req, controller.nota_consumo, data=data, pendentes=pendentes)


@router.post("/nota-consumo/{id_atendimento}/marcar")
async def nota_consumo_marcar(request: Request, id_atendimento: str, req: Requisicao = Depends(obter_requisicao)):
    """Marca à mão: lançada no AGHU / desfazer."""
    return await executar(request, req, controller.nota_consumo_marcar, id_atendimento=id_atendimento,
                          acao=req.campo("acao", ""), data=req.campo("data", ""), tipo=req.campo("tipo", "consumo"))


@router.post("/nota-consumo/{id_atendimento}/aghu/lancar")
async def nota_consumo_aghu_lancar(request: Request, id_atendimento: str,
                                   req: Requisicao = Depends(obter_requisicao)):
    """v18.7: link do robô instalado neste computador (JSON)."""
    return await executar(request, req, controller.nota_consumo_aghu_lancar, id_atendimento=id_atendimento)


@router.get("/robo-aghu/instalador")
async def robo_instalador(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Instalador do robô do AGHU."""
    return await executar(request, req, controller.robo_instalador)


@router.get("/nota-consumo/{id_atendimento}/aghu")
async def nota_consumo_aghu(request: Request, id_atendimento: str, req: Requisicao = Depends(obter_requisicao)):
    """Tela do robô do AGHU para a nota de consumo."""
    return await executar(request, req, controller.nota_consumo_aghu, id_atendimento=id_atendimento)


@router.post("/nota-consumo/{id_atendimento}/aghu/iniciar")
async def nota_consumo_aghu_iniciar(request: Request, id_atendimento: str,
                                    req: Requisicao = Depends(obter_requisicao)):
    """Começa o robô da nota de consumo (JSON)."""
    return await executar(request, req, controller.nota_consumo_aghu_iniciar, id_atendimento=id_atendimento)


# ---------------------------------------------------------------- v18: transferência entre farmácias

@router.get("/transferencias")
async def transferencias(
    request: Request,
    todas: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Transferências desta farmácia para a outra (Bloco ↔ Hemodinâmica)."""
    return await executar(request, req, controller.transferencias, todas=todas)


@router.post("/transferencias/novo")
async def transferencia_nova(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Abre (ou continua) a transferência que sai da farmácia escolhida."""
    return await executar(request, req, controller.transferencia_nova, farmacia=req.campo("farmacia", ""))


@router.get("/transferencia/{id_remessa}")
async def transferencia_tela(
    request: Request,
    id_remessa: str,
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Montar a transferência bipando (ou ver uma já finalizada)."""
    return await executar(request, req, controller.transferencia_tela, id_remessa=id_remessa, busca=busca)


@router.post("/transferencia/{id_remessa}/bipar")
async def transferencia_bipar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Bipa um material na transferência (JSON)."""
    return await executar(request, req, controller.transferencia_bipar, id_remessa=id_remessa)


@router.post("/transferencia/item/{id_item}/tirar")
async def transferencia_tirar(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Tira um item da transferência ainda aberta (JSON)."""
    return await executar(request, req, controller.transferencia_tirar, id_item=id_item)


@router.post("/transferencia/{id_remessa}/finalizar")
async def transferencia_finalizar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Finaliza: a farmácia de destino confere e dá ciência."""
    return await executar(request, req, controller.transferencia_finalizar, id_remessa=id_remessa,
                          observacao=req.campo("observacao", ""))


@router.post("/transferencia/{id_remessa}/cancelar")
async def transferencia_cancelar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Cancela enquanto a farmácia de destino não deu ciência."""
    return await executar(request, req, controller.transferencia_cancelar, id_remessa=id_remessa,
                          motivo=req.campo("motivo", ""))


@router.post("/transferencia/item/{id_item}/tratar")
async def transferencia_tratar(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Tratativa do item que a farmácia de destino não recebeu."""
    return await executar(request, req, controller.transferencia_tratar, id_item=id_item,
                          acao=req.campo("acao", ""), motivo=req.campo("motivo", ""))


# ---------------------------------------------------------------- nov/2026: cadastro manual na farmácia

@router.get("/manual")
async def tela_manual(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Cadastro manual: as unidades entram direto no estoque da farmácia escolhida."""
    return await executar(request, req, controller.tela_manual)


@router.post("/manual")
async def salvar_manual(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Grava o cadastro manual no estoque da farmácia (Bloco ou Hemodinâmica)."""
    return await executar(request, req, controller.salvar_manual)


@router.get("/etiquetas")
async def tela_etiquetas(
    request: Request,
    codigo: str = "",
    busca: str = "",
    tamanho: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Etiquetas QR do material cadastrado na farmácia sem código de barras."""
    return await executar(request, req, controller.tela_etiquetas, codigo=codigo, busca=busca, tamanho=tamanho)


@router.get("/qr/{codigo}.png")
async def imagem_qr(
    request: Request,
    codigo: str,
    sem_legenda: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """PNG do QR Code (etiqueta)."""
    return await executar(request, req, controller.imagem_qr, codigo=codigo, sem_legenda=sem_legenda)


@router.get("/consignado-aghu")
async def consignado_aghu_consultar(
    request: Request,
    codigo: str = "",
    aghu: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """AGHU associado ao código consignado (JSON) — preenche o cadastro sozinho."""
    return await executar(request, req, controller.consignado_aghu_consultar, codigo=codigo, aghu=aghu)


@router.post("/caixas-consignado/{id_caixa}/receber")
async def caixa_consignado_receber(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Farmácia dá ciência do recebimento de uma caixa dispensada pelo almoxarifado."""
    return await executar(request, req, controller.caixa_consignado_receber, id_caixa=id_caixa)


@router.get("/saidas-outros")
async def saidas_outros(
    request: Request,
    de: str = "",
    ate: str = "",
    destino: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.14: GET /saidas-outros — saídas de OPME para outros procedimentos"""
    return await executar(request, req, controller.saidas_outros, de=de, ate=ate, destino=destino)


@router.post("/saidas-outros/{id_unidade}/desfazer")
async def saida_outros_desfazer(
    request: Request,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.14: POST /saidas-outros/{id_unidade}/desfazer — item volta ao estoque"""
    return await executar(request, req, controller.saida_outros_desfazer,
                          id_unidade=id_unidade, motivo=req.campo("motivo", ""))
