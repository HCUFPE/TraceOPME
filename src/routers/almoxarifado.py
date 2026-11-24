"""Router — Almoxarifado (TraceOPME).

Endpoints REST do módulo. Protegidos por padrão (Default-Private Router
Pattern): o token JWT é exigido no APIRouter e o RBAC local é conferido no
controller (exigir_modulo). A regra de cada tela está em
src/controllers/almoxarifado_controller.py.
"""

from typing import Optional  # noqa: F401


from fastapi import APIRouter, Depends, Request

from ..auth.auth import auth_handler
from ..controllers import almoxarifado_controller as controller
from ..helpers.web_helper import Requisicao, executar, obter_requisicao

router = APIRouter(
    prefix="/api/almoxarifado",
    tags=["Almoxarifado"],
    dependencies=[Depends(auth_handler.decode_token)],
)

@router.get("")
async def hub(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado"""
    return await executar(request, req, controller.hub)


@router.get("/manual")
async def tela_manual(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/manual"""
    return await executar(request, req, controller.tela_manual)


@router.post("/manual")
async def salvar_manual(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/manual"""
    return await executar(request, req, controller.salvar_manual)


@router.get("/etiquetas")
async def tela_etiquetas(
    request: Request,
    codigo: str = "",
    busca: str = "",
    tamanho: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Folha de etiquetas pronta para imprimir (Ctrl+P)."""
    return await executar(request, req, controller.tela_etiquetas, codigo=codigo, busca=busca, tamanho=tamanho)


@router.get("/qr/{codigo}.png")
async def imagem_qr(
    request: Request,
    codigo: str,
    sem_legenda: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """PNG do QR Code de um código, para a etiqueta e para reimpressão."""
    return await executar(request, req, controller.imagem_qr, codigo=codigo, sem_legenda=sem_legenda)


@router.get("/nf")
async def tela_nf(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/nf"""
    return await executar(request, req, controller.tela_nf)


@router.post("/nf")
async def importar_nf(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/nf"""
    return await executar(request, req, controller.importar_nf, arquivo=req.arquivo("arquivo"))


@router.post("/nf/{chave}/excluir")
async def excluir_nf(
    request: Request,
    chave: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """v17 — exclui uma NF importada por engano."""
    return await executar(request, req, controller.excluir_nf, chave=chave, motivo=req.campo("motivo", ""))


@router.get("/nf/{chave}/planilha-aghu")
async def planilha_aghu_nf(
    request: Request,
    chave: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Excel da entrada desta NF para lançar no AGHU (nov/2026)."""
    return await executar(request, req, controller.planilha_aghu_nf, chave=chave)


@router.get("/nf/{chave}")
async def detalhe_nf(
    request: Request,
    chave: str,
    mostrar_recebidos: int = 0,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/nf/{chave}"""
    return await executar(request, req, controller.detalhe_nf, chave=chave, mostrar_recebidos=mostrar_recebidos)


@router.post("/nf/{chave}/receber")
async def receber_item_nf(
    request: Request,
    chave: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/nf/{chave}/receber"""
    return await executar(request, req, controller.receber_item_nf, chave=chave)


@router.get("/envios")
async def envios_tela(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/envios"""
    return await executar(request, req, controller.envios_tela)


@router.post("/envios/novo")
async def envio_novo(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/envios/novo"""
    return await executar(request, req, controller.envio_novo, farmacia=req.campo("farmacia", ""))


@router.get("/envio/{id_remessa}")
async def envio_tela(
    request: Request,
    id_remessa: str,
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/envio/{id_remessa}"""
    return await executar(request, req, controller.envio_tela, id_remessa=id_remessa, busca=busca)


@router.post("/envio/{id_remessa}/bipar")
async def envio_bipar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/envio/{id_remessa}/bipar"""
    return await executar(request, req, controller.envio_bipar, id_remessa=id_remessa)


@router.post("/envio/item/{id_item}/tirar")
async def envio_tirar_json(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Tira um item do envio sem recarregar a tela (o "tirar" da lista)."""
    return await executar(request, req, controller.envio_tirar_json, id_item=id_item)


@router.get("/envio/{id_remessa}/consultar")
async def envio_consultar(
    request: Request,
    id_remessa: str,
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/envio/{id_remessa}/consultar"""
    return await executar(request, req, controller.envio_consultar, id_remessa=id_remessa, busca=busca)


@router.post("/envio/item/{id_item}/remover")
async def envio_remover(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/envio/item/{id_item}/remover"""
    return await executar(request, req, controller.envio_remover, id_item=id_item)


@router.post("/envio/{id_remessa}/finalizar")
async def envio_finalizar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/envio/{id_remessa}/finalizar"""
    return await executar(request, req, controller.envio_finalizar, id_remessa=id_remessa, observacao=req.campo("observacao", ""))


@router.post("/envio/{id_remessa}/cancelar")
async def envio_cancelar(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Cancela o envio enquanto a farmácia não deu ciência (nov/2026)."""
    return await executar(request, req, controller.envio_cancelar, id_remessa=id_remessa,
                          motivo=req.campo("motivo", ""))


@router.get("/devolucoes-farmacia")
async def devolucoes_farmacia_tela(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Devoluções das farmácias para o almoxarifado (nov/2026)."""
    return await executar(request, req, controller.devolucoes_farmacia_tela)


@router.get("/devolucao-farmacia/{id_remessa}")
async def devolucao_farmacia_tela(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Conferir a devolução da farmácia e dar ciência (nov/2026)."""
    return await executar(request, req, controller.devolucao_farmacia_tela, id_remessa=id_remessa)


@router.get("/devolucao-farmacia/{id_remessa}/identificar")
async def devolucao_farmacia_identificar(
    request: Request,
    id_remessa: str,
    codigo: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Identifica o item bipado na conferência da devolução (nov/2026)."""
    return await executar(request, req, controller.devolucao_farmacia_identificar, id_remessa=id_remessa, codigo=codigo)


@router.post("/devolucao-farmacia/{id_remessa}/conferir")
async def devolucao_farmacia_conferir(
    request: Request,
    id_remessa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Dá ciência da devolução da farmácia (nov/2026)."""
    return await executar(request, req, controller.devolucao_farmacia_conferir, id_remessa=id_remessa)


@router.post("/devolucao-farmacia/item/{id_item}/recebi")
async def devolucao_farmacia_recebi(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Item da devolução que chegou depois da conferência (nov/2026)."""
    return await executar(request, req, controller.devolucao_farmacia_recebi, id_item=id_item,
                          voltar=req.campo("voltar", ""))


@router.get("/consignado-aghu")
async def consignado_aghu_consultar(
    request: Request,
    codigo: str = "",
    aghu: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """AGHU associado ao código consignado (JSON) — preenche o cadastro sozinho (nov/2026)."""
    return await executar(request, req, controller.consignado_aghu_consultar, codigo=codigo, aghu=aghu)


@router.get("/romaneios-fornecedor")
async def romaneios_fornecedor_tela(
    request: Request,
    inicio: str = "",
    fim: str = "",
    fornecedor: str = "",
    status: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v18: devoluções ao fornecedor por número (período, fornecedor, situação)."""
    return await executar(request, req, controller.romaneios_fornecedor_tela, inicio=inicio, fim=fim,
                          fornecedor=fornecedor, status=status)


@router.get("/devolucoes-fornecedor/abertas")
async def devolucoes_fornecedor_abertas(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """v18: devoluções abertas de quem está bipando (painel da bipagem)."""
    return await executar(request, req, controller.devolucoes_fornecedor_abertas)


@router.get("/devolucao-fornecedor/{id_devolucao}")
async def devolucao_fornecedor_ficha(request: Request, id_devolucao: str,
                                     req: Requisicao = Depends(obter_requisicao)):
    """v18: ficha da devolução ao fornecedor (itens, romaneio, cancelar)."""
    return await executar(request, req, controller.devolucao_fornecedor_ficha, id_devolucao=id_devolucao)


@router.get("/devolucao-fornecedor/{id_devolucao}/pdf")
async def devolucao_fornecedor_pdf(request: Request, id_devolucao: str,
                                   req: Requisicao = Depends(obter_requisicao)):
    """v18: romaneio em PDF da devolução."""
    return await executar(request, req, controller.devolucao_fornecedor_pdf, id_devolucao=id_devolucao)


@router.post("/devolucao-fornecedor/{id_devolucao}/{acao}")
async def devolucao_fornecedor_acao(request: Request, id_devolucao: str, acao: str,
                                    req: Requisicao = Depends(obter_requisicao)):
    """v18: finalizar · cancelar (motivo) · cancelar_item (id_unidade, motivo)."""
    return await executar(request, req, controller.devolucao_fornecedor_acao, id_devolucao=id_devolucao,
                          acao=acao.replace("-", "_"), motivo=req.campo("motivo", ""),
                          id_unidade=req.campo("id_unidade", ""))


@router.get("/romaneio-fornecedor/pdf")
async def romaneio_fornecedor_pdf(
    request: Request,
    ids: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Romaneio da devolução ao fornecedor em PDF, com assinaturas (nov/2026)."""
    return await executar(request, req, controller.romaneio_fornecedor_pdf, ids=ids)


@router.post("/envio/item/{id_item}/tratar")
async def envio_tratar(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/envio/item/{id_item}/tratar"""
    return await executar(request, req, controller.envio_tratar, id_item=id_item, acao=req.campo("acao", ""), motivo=req.campo("motivo", ""))


@router.get("/planilha")
async def planilha_tela(
    request: Request,
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/planilha"""
    return await executar(request, req, controller.planilha_tela, busca=busca)


@router.post("/planilha")
async def planilha_importar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/planilha"""
    return await executar(request, req, controller.planilha_importar, arquivo=req.arquivo("arquivo"))


@router.post("/planilha/bipar")
async def planilha_bipar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/planilha/bipar"""
    return await executar(request, req, controller.planilha_bipar)


@router.post("/planilha/{id_item}/sem-codigo")
async def planilha_sem_codigo(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/planilha/{id_item}/sem-codigo"""
    return await executar(request, req, controller.planilha_sem_codigo, id_item=id_item, quantidade=req.campo("quantidade", "1"), tipo_entrada=req.campo("tipo_entrada", ""))


@router.post("/planilha/{id_item}/retirar")
async def planilha_retirar(
    request: Request,
    id_item: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/planilha/{id_item}/retirar"""
    return await executar(request, req, controller.planilha_retirar, id_item=id_item, motivo=req.campo("motivo", ""))


@router.get("/correcoes")
async def tela_correcoes(
    request: Request,
    busca: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/correcoes"""
    return await executar(request, req, controller.tela_correcoes, busca=busca)


@router.post("/correcoes-lote")
async def salvar_correcao_em_lote(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/correcoes-lote"""
    return await executar(request, req, controller.salvar_correcao_em_lote)


async def _estado_unidades(req: Requisicao) -> list[dict]:
    """Como as unidades estavam antes (dados_anteriores da auditoria)."""
    from starlette.concurrency import run_in_threadpool
    from ..providers.implementations.opme import db
    ids = [i for i in req.lista("ids") if i][:2000]
    if not ids:
        return []
    marcadores = ",".join("?" for _ in ids)
    return await run_in_threadpool(
        db.consultar,
        f"""SELECT id_unidade, codigo_barras, codigo_aghu, xProd, nLote, dVal, status, origem
            FROM unidades WHERE id_unidade IN ({marcadores})""", ids)


@router.post("/correcoes/excluir")
async def excluir_cadastro(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/correcoes/excluir (nov/2026)"""
    return await executar(request, req, controller.excluir_cadastro,
                          dados_anteriores=await _estado_unidades(req))


@router.post("/correcoes/quantidade")
async def ajustar_quantidade(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/correcoes/quantidade (nov/2026)"""
    return await executar(request, req, controller.ajustar_quantidade,
                          dados_anteriores=await _estado_unidades(req))


@router.post("/correcoes/{id_unidade}")
async def salvar_correcao(
    request: Request,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/correcoes/{id_unidade}"""
    return await executar(request, req, controller.salvar_correcao, id_unidade=id_unidade)


@router.get("/api/descritivo/{codigo_aghu}")
async def api_descritivo(
    request: Request,
    codigo_aghu: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Consulta ao vivo, usada pela tela de recebimento e de cadastro manual
    para mostrar o nome oficial do material assim que o código AGHU é digitado
    — também serve de conferência: se nada aparecer, ou aparecer algo muito
    diferente do esperado, é sinal de que o código foi digitado errado."""
    return await executar(request, req, controller.api_descritivo, codigo_aghu=codigo_aghu)


@router.get("/nao-cadastrados")
async def nao_cadastrados_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/nao-cadastrados"""
    return await executar(request, req, controller.nao_cadastrados_lista)


@router.post("/nao-cadastrados/{id_registro}/regularizar")
async def nao_cadastrados_regularizar(
    request: Request,
    id_registro: int,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/nao-cadastrados/{id_registro}/regularizar"""
    return await executar(request, req, controller.nao_cadastrados_regularizar, id_registro=id_registro)

# nov/2026 — caixas de consignado no almoxarifado

@router.get("/caixas")
async def caixas_lista(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/caixas"""
    return await executar(request, req, controller.caixas_lista)


@router.post("/caixas")
async def caixas_criar(
    request: Request,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: POST /almoxarifado/caixas"""
    return await executar(request, req, controller.caixas_criar)


@router.get("/reposicao-caixas")
async def reposicao_caixas(
    request: Request,
    de: str = "",
    ate: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.11.8: GET /almoxarifado/reposicao-caixas — o que repor nas caixas"""
    return await executar(request, req, controller.reposicao_caixas, de=de, ate=ate)


@router.get("/caixas/{id_caixa}/saidas")
async def caixa_saidas(
    request: Request,
    id_caixa: str,
    de: str = "",
    ate: str = "",
    req: Requisicao = Depends(obter_requisicao),
):
    """v18.11.7: GET /caixas/{id_caixa}/saidas — saídas da caixa por período"""
    return await executar(request, req, controller.caixa_saidas, id_caixa=id_caixa, de=de, ate=ate)


@router.get("/caixas/{id_caixa}")
async def caixa_ficha(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Almoxarifado: GET /almoxarifado/caixas/{id_caixa}"""
    return await executar(request, req, controller.caixa_ficha, id_caixa=id_caixa)


@router.post("/caixas/{id_caixa}/adicionar")
async def caixa_adicionar(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Coloca na caixa um item que está no almoxarifado."""
    return await executar(request, req, controller.caixa_adicionar, id_caixa=id_caixa, codigo=req.campo("codigo", ""), id_unidade=req.campo("id_unidade", ""), quantidade=req.campo("quantidade", "1"))


@router.post("/caixas/{id_caixa}/retirar/{id_unidade}")
async def caixa_retirar(
    request: Request,
    id_caixa: str,
    id_unidade: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Tira um item da caixa."""
    return await executar(request, req, controller.caixa_retirar, id_caixa=id_caixa, id_unidade=id_unidade, motivo=req.campo("motivo", ""))


@router.post("/caixas/{id_caixa}/conferir")
async def caixa_conferir(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Confere a caixa."""
    return await executar(request, req, controller.caixa_conferir, id_caixa=id_caixa)


@router.get("/caixas/{id_caixa}/etiqueta")
async def caixa_etiqueta(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Etiqueta da caixa."""
    return await executar(request, req, controller.caixa_etiqueta, id_caixa=id_caixa)


@router.get("/caixas/{id_caixa}/qr.png")
async def caixa_qr(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """QR da caixa."""
    return await executar(request, req, controller.caixa_qr, id_caixa=id_caixa)


@router.post("/caixas/{id_caixa}/enviar")
async def caixa_enviar(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Dispensa a caixa para uma farmácia."""
    return await executar(request, req, controller.caixa_enviar, id_caixa=id_caixa, farmacia=req.campo("farmacia", ""))


@router.post("/caixas/{id_caixa}/cancelar-envio")
async def caixa_cancelar_envio(
    request: Request,
    id_caixa: str,
    req: Requisicao = Depends(obter_requisicao),
):
    """Cancela o envio da caixa (volta ao almoxarifado)."""
    return await executar(request, req, controller.caixa_cancelar_envio, id_caixa=id_caixa, motivo=req.campo("motivo", ""))


# nov/2026 — lançamento da NF no AGHU (robô)
@router.post("/nf/{chave}/aghu/lancar")
async def aghu_lancar(request: Request, chave: str, req: Requisicao = Depends(obter_requisicao)):
    """Gera o link que abre o robô do AGHU no computador de quem clicou (JSON: servidor)."""
    return await executar(request, req, controller.aghu_lancar, chave=chave)


# v18.5 — robô do AGHU no servidor (tela do AGHU dentro do TraceOPME)
@router.get("/nf/{chave}/aghu/web")
async def aghu_web(request: Request, chave: str, req: Requisicao = Depends(obter_requisicao)):
    """Tela de lançamento no AGHU com o robô rodando no servidor."""
    return await executar(request, req, controller.aghu_web, chave=chave)


@router.post("/nf/{chave}/aghu/web/iniciar")
async def aghu_web_iniciar(request: Request, chave: str, req: Requisicao = Depends(obter_requisicao)):
    """Começa o lançamento no servidor (JSON)."""
    return await executar(request, req, controller.aghu_web_iniciar, chave=chave)


@router.get("/robo-web/{sessao}/estado")
async def aghu_web_estado(request: Request, sessao: str, desde: int = 0,
                          req: Requisicao = Depends(obter_requisicao)):
    """Situação, pergunta e log do robô (JSON)."""
    return await executar(request, req, controller.aghu_web_estado, sessao=sessao, desde=desde, auditar=False)


@router.get("/robo-web/{sessao}/tela")
async def aghu_web_tela(request: Request, sessao: str, req: Requisicao = Depends(obter_requisicao)):
    """Imagem atual da tela do AGHU (JPEG)."""
    return await executar(request, req, controller.aghu_web_tela, sessao=sessao, auditar=False)


@router.get("/robo-web/{sessao}/fluxo")
async def aghu_web_fluxo(request: Request, sessao: str, req: Requisicao = Depends(obter_requisicao)):
    """Tela do AGHU em fluxo contínuo (quadros JPEG com tamanho na frente)."""
    return await executar(request, req, controller.aghu_web_fluxo, sessao=sessao, auditar=False)


@router.post("/robo-web/{sessao}/entrada")
async def aghu_web_entrada(request: Request, sessao: str, req: Requisicao = Depends(obter_requisicao)):
    """Cliques e teclas na tela do AGHU — sem auditoria (pode ser a senha do AGHU)."""
    return await executar(request, req, controller.aghu_web_entrada, sessao=sessao, auditar=False)


@router.post("/robo-web/{sessao}/responder")
async def aghu_web_responder(request: Request, sessao: str, req: Requisicao = Depends(obter_requisicao)):
    """Resposta à pergunta do robô (Continuar, Sim/Não…)."""
    return await executar(request, req, controller.aghu_web_responder, sessao=sessao, auditar=False)


@router.post("/robo-web/{sessao}/cancelar")
async def aghu_web_cancelar(request: Request, sessao: str, req: Requisicao = Depends(obter_requisicao)):
    """Para o robô."""
    return await executar(request, req, controller.aghu_web_cancelar, sessao=sessao)


@router.get("/robo-aghu/instalador")
async def aghu_instalador(request: Request, req: Requisicao = Depends(obter_requisicao)):
    """Baixa o instalador do robô do AGHU (para o computador de quem lança)."""
    return await executar(request, req, controller.aghu_instalador)


@router.post("/nf/{chave}/aghu/marcar")
async def aghu_marcar(request: Request, chave: str, req: Requisicao = Depends(obter_requisicao)):
    """Marca à mão: acao=lancada (com o nº da nota de recebimento) ou desfazer/cancelar."""
    return await executar(request, req, controller.aghu_marcar, chave=chave, acao=req.campo("acao", ""),
                          numero_nr=req.campo("numero_nr", ""))


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
