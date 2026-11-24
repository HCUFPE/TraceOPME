"""Controller — Almoxarifado (TraceOPME).

Regras de tela do módulo, portadas de app/routers/almoxarifado.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/almoxarifado.py.
Original:
    Módulo Almoxarifado (antigo Recebimento).
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile
from fastapi.responses import Response

from ..providers.implementations.opme.config import ESPECIALIDADES_PADRAO
from ..providers.implementations.opme.domain import EM_ESTOQUE_RECEBIMENTO
from ..providers.implementations.opme.services import alertas, estoque, etiquetas, materiais, relatorios
from ..providers.implementations.opme.utils import normalizar_codigo

MODULO = "almoxarifado"


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    contagem = relatorios.contagem_por_status()
    return render(request, "almoxarifado/hub.html", {
        "em_estoque": contagem.get(EM_ESTOQUE_RECEBIMENTO, 0),
        "notas": estoque.notas_com_pendencia(),
        "alertas": [a | {"itens": alertas.itens(a)} for a in alertas.abertos_do_modulo(MODULO)],
        "nao_cadastrados": __import__("src.providers.implementations.opme.services.nao_cadastrados", fromlist=["x"]).contar_pendentes(),
        "pendentes_planilha": __import__("src.providers.implementations.opme.services.carga_planilha", fromlist=["x"]).total_pendente(),
        "envios_pendencias": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_pendencias(),
        "envios_aguardando": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_a_receber(),
        "devolucoes_farmacia": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_a_receber(sentido="farmacia_almox"),
        "devolucoes_farmacia_pendencias": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_pendencias(sentido="farmacia_almox"),
        "a_lancar_aghu": len(__import__("src.providers.implementations.opme.services.aghu_robo", fromlist=["x"]).a_lancar()),
        "a_repor_caixas": sum(l["faltam"] for l in __import__("src.providers.implementations.opme.services.reposicao_caixas", fromlist=["x"]).a_repor(
            __import__("datetime").date.fromordinal(__import__("datetime").date.today().toordinal() - 30).isoformat())),
        "caixas_a_caminho": len(__import__("src.providers.implementations.opme.services.caixas_almox", fromlist=["x"]).a_receber()),
    })


# ---------------------------------------------------------
# Cadastro manual
# ---------------------------------------------------------

def _contexto_manual(base: str, farmacia_atual: str = "") -> dict:
    """nov/2026: a mesma tela de cadastro manual serve ao almoxarifado e às farmácias."""
    contexto = {"tipos": estoque.TIPOS_ENTRADA, "base": base}
    if base == "/farmacia":
        from ..providers.implementations.opme.config import FARMACIAS
        contexto |= {"farmacias": FARMACIAS, "farmacia_atual": farmacia_atual}
    return contexto


def tela_manual(request: Request, modulo: str = MODULO, base: str = "/almoxarifado", farmacia_atual: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, modulo)
    return render(request, "almoxarifado/manual.html", _contexto_manual(base, farmacia_atual))


async def salvar_manual(request: Request, modulo: str = MODULO, base: str = "/almoxarifado", farmacia_atual: str = ""):
    from ..helpers.web_helper import avisar, render
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, modulo)

    # O código interno é gerado aqui para o router saber para qual etiqueta levar
    # o usuário depois de cadastrar.
    formulario = estoque.aplicar_codigo_interno(dict(await request.form()))
    farmacia = texto_campo(formulario.get("farmacia")) if base == "/farmacia" else ""
    from ..providers.implementations.opme.utils import data_br, data_iso, hoje_iso
    validade = data_iso(formulario.get("dVal"))
    if base == "/farmacia" and not farmacia:
        ok, mensagem = False, "Escolha a farmácia (Bloco Cirúrgico ou Hemodinâmica) onde o material vai ficar."
    elif not validade:
        # v18: validade obrigatória no cadastro manual.
        ok, mensagem = False, "Informe a validade do material (está na embalagem)."
    elif validade < hoje_iso():
        # nov/2026: no cadastro manual não entra material já vencido.
        ok, mensagem = False, (f"Validade {data_br(validade)} já passou. Não é possível cadastrar material vencido; "
                               "confira a data na etiqueta.")
    else:
        # v18.39: avisos que não impedem (código de caixa, possível duplicidade).
        alertas = estoque.avisos_do_cadastro(estoque.limpar_codigo_do_formulario(formulario))
        ok, mensagem = estoque.cadastrar_manual(formulario, usuario["username"], farmacia=farmacia)
        if ok and alertas:
            mensagem = mensagem + "  ⚠ " + "  ⚠ ".join(alertas)
    if ok:
        avisar(request, mensagem)
        from ..helpers.web_helper import redirecionar
        codigo = normalizar_codigo(formulario.get("codigo_barras"))
        # Item sem código de barras: leva direto para a etiqueta, que precisa
        # ser impressa e colada antes de o material ir para a prateleira.
        if etiquetas.e_codigo_interno(codigo):
            return redirecionar(f"{base}/etiquetas?codigo={codigo}")
        return redirecionar(f"{base}/manual")
    return render(request, "almoxarifado/manual.html", _contexto_manual(base, farmacia or farmacia_atual) | {
        "erro": mensagem, "valores": formulario,
    })


def texto_campo(valor) -> str:
    return str(valor or "").strip()


# ---------------------------------------------------------
# Etiquetas QR para material sem código de barras
# ---------------------------------------------------------

def tela_etiquetas(request: Request, codigo: str = "", busca: str = "", tamanho: str = "",
                   modulo: str = MODULO, base: str = "/almoxarifado"):
    """Folha de etiquetas pronta para imprimir (Ctrl+P)."""
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, modulo)

    termo = normalizar_codigo(codigo) or busca
    itens = estoque.buscar_unidades(termo, "ativos") if termo else []
    if normalizar_codigo(codigo):
        itens = [i for i in itens if i["codigo_barras"] == normalizar_codigo(codigo)]

    return render(request, "almoxarifado/etiquetas.html", {
        "itens": itens, "codigo": codigo, "busca": busca,
        # Etiqueta pequena (5 × 2,5 cm) por padrão; média (7 × 3,5 cm) se pedir.
        "tamanho": tamanho if tamanho in ("pequena", "media") else "pequena",
        "qr_disponivel": etiquetas.qr_disponivel(),
        "base": base,
    })


def imagem_qr(request: Request, codigo: str, sem_legenda: int = 0, modulo: str = MODULO):
    """PNG do QR Code de um código, para a etiqueta e para reimpressão."""
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, modulo)
    try:
        # Na etiqueta pequena o código já vem escrito ao lado: QR sem legenda e com
        # margem mínima, para caber em 2 cm.
        png = (etiquetas.gerar_png(codigo, borda=1) if sem_legenda
               else etiquetas.gerar_png(codigo, legenda=codigo))
    except etiquetas.QRIndisponivel as erro:
        return Response(str(erro), status_code=503, media_type="text/plain; charset=utf-8")
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------
# Nota fiscal
# ---------------------------------------------------------

def tela_nf(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    from ..providers.implementations.opme.services import aghu_robo
    return render(request, "almoxarifado/nf_lista.html", {"notas": estoque.notas_com_pendencia(),
                                                          "a_lancar_aghu": aghu_robo.a_lancar()})


async def importar_nf(request: Request, arquivo: UploadFile = None):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    conteudo = await arquivo.read()
    if not conteudo:
        avisar(request, "Selecione um arquivo XML da NF-e.", "erro")
        return redirecionar("/almoxarifado/nf")

    ok, mensagem, chave = estoque.importar_nfe(conteudo, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/nf/{chave}" if ok and chave else "/almoxarifado/nf")


def excluir_nf(request: Request, chave: str, motivo: str = ("")):
    """v17 — exclui uma NF importada por engano."""
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = estoque.excluir_nota(chave, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/almoxarifado/nf" if ok else f"/almoxarifado/nf/{chave}")


def detalhe_nf(request: Request, chave: str, mostrar_recebidos: int = 0):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)

    nota = estoque.nota(chave)
    if not nota:
        return redirecionar("/almoxarifado/nf")

    todos = estoque.itens_da_nota(chave)
    # Marcas/fabricantes e AGHUs já vistos antes para o mesmo código de barras
    # (cEAN) — a NF-e não traz esse dado. É só uma lista de sugestões: o mesmo
    # código pode legitimamente ter vindo de fabricantes diferentes em pregões
    # diferentes, então nada aqui é preenchido sozinho no formulário.
    todos = [i | {
        # Sugestão exige código de barras E descrição batendo — o mesmo
        # código sozinho pode pertencer a materiais diferentes.
        "marcas_conhecidas": estoque.marcas_conhecidas(i.get("cEAN"), i.get("xProd")),
        "aghus_conhecidos": estoque.aghus_conhecidos(i.get("cEAN"), i.get("xProd")),
        # O cEAN é o código de barras que a própria NF-e declara para este
        # item — diferente da marca/AGHU, não é um palpite: é o dado desta
        # nota. Ainda assim o campo continua editável, para quando a
        # embalagem física não bater com o que a nota diz.
        "codigo_sugerido": estoque.cean_utilizavel(i.get("cEAN")),
        # v17: a NF não trouxe lote/validade → a tela pede para digitar.
        "precisa_lote": not estoque.lote_informado(i.get("nLote")),
        "precisa_validade": not (i.get("dVal") or ""),
    } for i in todos]
    pendentes = [i for i in todos if (i["qtd_pendente"] or 0) > 0]
    concluidos = [i for i in todos if (i["qtd_pendente"] or 0) <= 0]

    return render(request, "almoxarifado/nf_detalhe.html", {
        "nota": nota,
        # Itens totalmente recebidos saem da lista: numa NF com dezenas de linhas,
        # o que interessa é o que ainda falta dar entrada.
        "itens": todos if mostrar_recebidos else pendentes,
        "pendentes": pendentes,
        "concluidos": concluidos,
        "mostrar_recebidos": bool(mostrar_recebidos),
        "tipos": estoque.TIPOS_ENTRADA,
        "exclusao": estoque.situacao_exclusao_nota(chave),
        # nov/2026: linhas (material + lote + validade) da planilha para o AGHU.
        "planilha_aghu": len(__import__("src.providers.implementations.opme.services.planilha_aghu",
                                        fromlist=["x"]).linhas(chave)),
        # nov/2026: lançamento desta NF no AGHU (robô ou à mão).
        "aghu": __import__("src.providers.implementations.opme.services.aghu_robo", fromlist=["x"]).situacao(chave),
    })


async def receber_item_nf(request: Request, chave: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    formulario = dict(await request.form())
    ok, mensagem = estoque.dar_entrada_item_nf(formulario, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")

    # Item sem código de barras: leva direto à etiqueta, que precisa ser
    # impressa e colada antes de o material ir para a prateleira.
    if ok:
        item = estoque.item_da_nota(formulario.get("id_item", ""))
        codigo = etiquetas.gerar_codigo_interno(
            formulario.get("codigo_aghu"), item["nLote"] if item else "")
        marcado = str(formulario.get("sem_codigo_barras", "")).lower() in ("1", "true", "on", "sim")
        if marcado and not normalizar_codigo(formulario.get("codigo_barras")):
            return redirecionar(f"/almoxarifado/etiquetas?codigo={codigo}")
        # nov/2026: terminou a entrada da NF → segue direto para o lançamento no AGHU.
        from ..providers.implementations.opme.services import aghu_robo
        sit = aghu_robo.situacao(chave)
        if sit["entrada_concluida"] and sit["status"] != "lancada":
            avisar(request, "Entrada da NF concluída no TraceOPME. Agora é lançar no AGHU: clique em "
                            "“Lançar no AGHU agora”.", "sucesso")
            return redirecionar(f"/almoxarifado/nf/{chave}#aghu")
    return redirecionar(f"/almoxarifado/nf/{chave}")


# ---------------------------------------------------------
# Envio para a farmácia (Bloco ou Hemodinâmica)
# ---------------------------------------------------------

def envios_tela(request: Request):
    from ..providers.implementations.opme.config import FARMACIAS
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "almoxarifado/envios.html", {
        "farmacias": FARMACIAS, "abertas": remessas.listar("aberta"),
        "enviadas": remessas.listar("enviada"), "conferidas": remessas.listar("conferida", limite=30),
        "canceladas": remessas.listar("cancelada", limite=10),
        "pendencias": remessas.pendencias(), "tratativas": remessas.TRATATIVAS,
        "devolucoes_a_conferir": remessas.contar_a_receber(sentido=remessas.DEVOLUCAO)})


def envio_novo(request: Request, farmacia: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, r = remessas.abrir(farmacia, usuario["username"])
    if not ok:
        avisar(request, r, "erro")
        return redirecionar("/almoxarifado/envios")
    return redirecionar(f"/almoxarifado/envio/{r}")


def envio_tela(request: Request, id_remessa: str, busca: str = ""):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem:
        return redirecionar("/almoxarifado/envios")
    if rem["sentido"] != remessas.ENVIO:
        return redirecionar(f"/almoxarifado/devolucao-farmacia/{id_remessa}")
    return render(request, "almoxarifado/envio.html", {
        "rem": rem, "tratativas": remessas.TRATATIVAS, "lista": remessas.lista_envio(id_remessa),
        "busca": busca, "resultados": remessas.disponiveis(busca) if busca else [],
        "disponiveis_total": db_total_almox(), "rotas": rotas_envio(id_remessa)})


def rotas_envio(id_remessa: str) -> dict:
    """Endereços da tela de montar o envio (a mesma tela serve à devolução da farmácia)."""
    return {"pagina": f"/almoxarifado/envio/{id_remessa}", "bipar": f"/almoxarifado/envio/{id_remessa}/bipar",
            "tirar": "/almoxarifado/envio/item/{id}/tirar", "finalizar": f"/almoxarifado/envio/{id_remessa}/finalizar",
            "cancelar": f"/almoxarifado/envio/{id_remessa}/cancelar", "voltar": "/almoxarifado/envios",
            "trocar": "/almoxarifado/envios"}


def db_total_almox() -> int:
    from ..providers.implementations.opme import db
    return int(db.escalar("SELECT COUNT(*) FROM unidades WHERE status = 'em_estoque_recebimento'") or 0)


async def envio_bipar(request: Request, id_remessa: str):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] != remessas.ENVIO:
        return JSONResponse({"ok": False, "mensagem": "Envio não encontrado."})
    c = await request.json()
    return JSONResponse(remessas.bipar(id_remessa, str(c.get("codigo") or ""), usuario["username"],
                                       c.get("quantidade", 1), str(c.get("grupo") or ""),
                                       ciencia_validade=bool(c.get("ciencia_validade"))))


def envio_tirar_json(request: Request, id_item: int):
    """Tira um item do envio sem recarregar a tela (o "tirar" da lista)."""
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) != remessas.ENVIO:
        return JSONResponse({"ok": False, "mensagem": "Item não encontrado neste envio.", "lista": []})
    ok, msg, id_rem = remessas.remover_item(id_item, usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": msg, "lista": remessas.lista_envio(id_rem) if id_rem else []})


def envio_consultar(request: Request, id_remessa: str, busca: str = ""):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import redirecionar
    return redirecionar(f"/almoxarifado/envio/{id_remessa}?busca={busca}")


def envio_remover(request: Request, id_item: int):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) != remessas.ENVIO:
        avisar(request, "Item não encontrado neste envio.", "erro")
        return redirecionar("/almoxarifado/envios")
    ok, msg, id_rem = remessas.remover_item(id_item, usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/envio/{id_rem}" if id_rem else "/almoxarifado/envios")


def envio_finalizar(request: Request, id_remessa: str, observacao: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] != remessas.ENVIO:
        return redirecionar("/almoxarifado/envios")
    ok, msg = remessas.finalizar_envio(id_remessa, usuario["username"], observacao)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/envio/{id_remessa}")


def envio_cancelar(request: Request, id_remessa: str, motivo: str = ("")):
    """nov/2026: cancela o envio enquanto a farmácia não deu ciência."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] != remessas.ENVIO:
        avisar(request, "Envio não encontrado.", "erro")
        return redirecionar("/almoxarifado/envios")
    ok, msg = remessas.cancelar(id_remessa, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/envio/{id_remessa}")


# ---------------------------------------------------------
# nov/2026 — devoluções das farmácias para o almoxarifado (dar ciência)
# ---------------------------------------------------------

def rotas_ciencia_devolucao(id_remessa: str) -> dict:
    return {"identificar": f"/almoxarifado/devolucao-farmacia/{id_remessa}/identificar",
            "conferir": f"/almoxarifado/devolucao-farmacia/{id_remessa}/conferir",
            "recebi": "/almoxarifado/devolucao-farmacia/item/{id}/recebi",
            "pagina": f"/almoxarifado/devolucao-farmacia/{id_remessa}",
            "voltar": "/almoxarifado/devolucoes-farmacia"}


def devolucoes_farmacia_tela(request: Request):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    d = remessas.DEVOLUCAO
    return render(request, "almoxarifado/devolucoes_farmacia.html", {
        "enviadas": remessas.listar("enviada", sentido=d), "abertas": remessas.listar("aberta", sentido=d),
        "conferidas": remessas.listar("conferida", limite=30, sentido=d),
        "canceladas": remessas.listar("cancelada", limite=10, sentido=d),
        "pendencias": remessas.pendencias(sentido=d), "tratativas": remessas.TRATATIVAS_DEVOLUCAO})


def devolucao_farmacia_tela(request: Request, id_remessa: str):
    from ..helpers.web_helper import exigir_modulo, redirecionar, render
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] != remessas.DEVOLUCAO:
        return redirecionar("/almoxarifado/devolucoes-farmacia")
    return render(request, "almoxarifado/devolucao_farmacia.html", {
        "rem": rem, "tratativas": rem["tratativas"], "rotas": rotas_ciencia_devolucao(id_remessa)})


def devolucao_farmacia_identificar(request: Request, id_remessa: str, codigo: str = ""):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    return JSONResponse(remessas.identificar(id_remessa, codigo))


async def devolucao_farmacia_conferir(request: Request, id_remessa: str):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] != remessas.DEVOLUCAO:
        return redirecionar("/almoxarifado/devolucoes-farmacia")
    form = await request.form()
    modo = "bipando" if form.get("modo") == "bipando" else "lista"
    recebidos = {str(v) for v in form.getlist("bipado" if modo == "bipando" else "recebido")}
    ok, msg = remessas.conferir(id_remessa, recebidos, usuario, modo, str(form.get("observacao") or ""))
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/devolucao-farmacia/{id_remessa}")


def devolucao_farmacia_recebi(request: Request, id_item: int, voltar: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) != remessas.DEVOLUCAO:
        avisar(request, "Pendência não encontrada.", "erro")
        return redirecionar("/almoxarifado/devolucoes-farmacia")
    ok, msg = remessas.tratar(id_item, "recebido_depois", usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(voltar if voltar.startswith("/almoxarifado") else "/almoxarifado/devolucoes-farmacia")


def envio_tratar(request: Request, id_item: int, acao: str = (""), motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) != remessas.ENVIO:
        avisar(request, "Pendência de devolução: quem trata é a farmácia (ou dê ciência com “recebi”).", "erro")
        return redirecionar("/almoxarifado/devolucoes-farmacia")
    if acao not in ("voltou_almoxarifado", "divergencia"):
        avisar(request, "Escolha: voltou ao almoxarifado ou divergência.", "erro")
        return redirecionar("/almoxarifado/envios#pendencias")
    ok, msg = remessas.tratar(id_item, acao, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/almoxarifado/envios#pendencias")


# ---------------------------------------------------------
# Planilha de lotes do AGHU (fica pendente até bipar)
# ---------------------------------------------------------

def planilha_tela(request: Request, busca: str = ""):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import carga_planilha
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "almoxarifado/planilha.html", {
        "cargas": carga_planilha.cargas(), "itens": carga_planilha.pendentes(busca, limite=2000),
        "tipos": estoque.TIPOS_ENTRADA,
        "total_pendente": carga_planilha.total_pendente(), "busca": busca})


async def planilha_importar(request: Request, arquivo: UploadFile = None):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import carga_planilha
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    conteudo = await arquivo.read()
    if not conteudo:
        avisar(request, "Selecione a planilha (CSV).", "erro")
        return redirecionar("/almoxarifado/planilha")
    ok, mensagem, _ = carga_planilha.importar(conteudo, arquivo.filename or "", usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/almoxarifado/planilha")


async def planilha_bipar(request: Request):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import carga_planilha
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    corpo = await request.json()
    return JSONResponse(carga_planilha.bipar(corpo.get("codigo", ""), usuario["username"],
                                             id_item=corpo.get("id_item"), quantidade=corpo.get("quantidade", 1),
                                             tipo_entrada=str(corpo.get("tipo_entrada") or "")))


def planilha_sem_codigo(request: Request, id_item: int, quantidade: str = ("1"),
                        tipo_entrada: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import carga_planilha
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem, codigo = carga_planilha.entrada_sem_codigo(id_item, quantidade, usuario["username"], tipo_entrada)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/etiquetas?codigo={codigo}" if ok else "/almoxarifado/planilha")


def planilha_retirar(request: Request, id_item: int, motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import carga_planilha
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = carga_planilha.cancelar_linha(id_item, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/almoxarifado/planilha")


# ---------------------------------------------------------
# Correções
# ---------------------------------------------------------

def tela_correcoes(request: Request, busca: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    # v18.17: itens e grupos saem juntos, coerentes com a etiqueta bipada.
    achado = estoque.para_correcao(busca)
    return render(request, "almoxarifado/correcoes.html", {
        "busca": busca,
        "itens": achado["itens"],
        # Unidades cadastradas com os mesmos dados, para corrigir de uma vez.
        "grupos": achado["grupos"],
        "etiqueta": achado["etiqueta"],
        "aviso_etiqueta": achado["aviso"],
        "tipos": estoque.TIPOS_ENTRADA,
        "campos": estoque.CAMPOS_EDITAVEIS,
    })


async def salvar_correcao_em_lote(request: Request):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    formulario = await request.form()
    ids = formulario.getlist("ids")
    # Cada campo vem com o valor que a tela mostrou (`original_<campo>`): só o
    # que a pessoa mudou é aplicado. Ver `estoque.corrigir_em_lote`.
    dados = {c: formulario.get(c, "") for c in estoque.CAMPOS_EM_LOTE if c in formulario}
    originais = {c: formulario.get(f"original_{c}", "") for c in estoque.CAMPOS_EM_LOTE}
    ok, mensagem = estoque.corrigir_em_lote(
        ids, dados, originais, usuario["username"], formulario.get("motivo", ""))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/correcoes?busca={formulario.get('busca', '')}")


async def salvar_correcao(request: Request, id_unidade: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    formulario = dict(await request.form())
    motivo = formulario.pop("motivo", "")
    busca = formulario.pop("busca", "")
    ok, mensagem = estoque.corrigir_unidade(id_unidade, formulario, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/correcoes?busca={busca}")


async def excluir_cadastro(request: Request):
    """nov/2026 — exclui do estoque unidades cadastradas por engano (Corrigir cadastro)."""
    from urllib.parse import quote
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    formulario = await request.form()
    ok, mensagem = estoque.excluir_unidades(formulario.getlist("ids"), usuario["username"],
                                            formulario.get("motivo", ""))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/correcoes?busca={quote(str(formulario.get('busca', '')))}")


async def ajustar_quantidade(request: Request):
    """nov/2026 — corrige a quantidade de um cadastro (Corrigir cadastro)."""
    from urllib.parse import quote
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    formulario = await request.form()
    ok, mensagem = estoque.ajustar_quantidade(formulario.getlist("ids"), formulario.get("quantidade", ""),
                                              usuario["username"], formulario.get("motivo", ""))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/correcoes?busca={quote(str(formulario.get('busca', '')))}")


# v17: caixas da especialidade removidas. As CAIXAS DE CONSIGNADO são montadas
# na farmácia — ver routers/farmacia.py e services/caixas_consignado.py.

# ---------------------------------------------------------
# Descritivo oficial do material (código AGHU -> nome que o hospital usa)
#
# Associação carregada uma vez a partir da planilha do hospital — estável, sem
# tela de gerenciamento: o mesmo AGHU sempre corresponde ao mesmo descritivo,
# e só muda quando um material novo é adquirido fora dessa lista.
# ---------------------------------------------------------

def api_descritivo(request: Request, codigo_aghu: str):
    """Consulta ao vivo, usada pela tela de recebimento e de cadastro manual
    para mostrar o nome oficial do material assim que o código AGHU é digitado
    — também serve de conferência: se nada aparecer, ou aparecer algo muito
    diferente do esperado, é sinal de que o código foi digitado errado.
    """
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return JSONResponse({"descritivo": materiais.descritivo_hospital(codigo_aghu)})



# v17 (out/2026) — material usado na sala sem cadastro: o almoxarifado regulariza.
def nao_cadastrados_lista(request: Request):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import nao_cadastrados
    from ..providers.implementations.opme.services.estoque import TIPOS_ENTRADA
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "almoxarifado/nao_cadastrados.html", {
        "pendentes": nao_cadastrados.listar("pendente"),
        "regularizados": nao_cadastrados.listar("regularizado")[:50],
        "tipos": TIPOS_ENTRADA,
    })


async def nao_cadastrados_regularizar(request: Request, id_registro: int):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import nao_cadastrados
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    dados = {k: str(v) for k, v in (await request.form()).items()}
    ok, mensagem = nao_cadastrados.regularizar(id_registro, dados, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/almoxarifado/nao-cadastrados")


# ---------------------------------------------------------
# nov/2026 — romaneio da devolução ao fornecedor
# ---------------------------------------------------------

def romaneios_fornecedor_tela(request: Request, inicio: str = "", fim: str = "", fornecedor: str = "",
                              status: str = ""):
    """v18: devoluções ao fornecedor por NÚMERO (período, fornecedor, situação)."""
    from datetime import date, timedelta
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import devolucoes_fornecedor as dvf
    from ..providers.implementations.opme.utils import data_iso
    exigir_modulo(request, MODULO)
    fim = data_iso(fim) or date.today().isoformat()
    inicio = data_iso(inicio) or (date.today() - timedelta(days=30)).isoformat()
    lista = dvf.listar(inicio, fim, fornecedor, status)
    return render(request, "almoxarifado/romaneios_fornecedor.html", {
        "inicio": inicio, "fim": fim, "fornecedor": fornecedor, "status": status, "devolucoes": lista,
        "fornecedores": dvf.fornecedores(), "situacoes": dvf.SITUACOES})


def devolucao_fornecedor_ficha(request: Request, id_devolucao: str):
    from ..helpers.web_helper import exigir_modulo, redirecionar, render
    from ..providers.implementations.opme.services import devolucoes_fornecedor as dvf
    exigir_modulo(request, MODULO)
    d = dvf.buscar(id_devolucao)
    if not d:
        return redirecionar("/almoxarifado/romaneios-fornecedor")
    return render(request, "almoxarifado/devolucao_fornecedor.html", {"dev": d, "itens": dvf.itens(id_devolucao)})


def devolucao_fornecedor_pdf(request: Request, id_devolucao: str):
    from fastapi.responses import Response
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import devolucoes_fornecedor as dvf
    usuario = exigir_modulo(request, MODULO)
    conteudo, nome = dvf.pdf(id_devolucao, usuario.get("nome") or usuario["username"])
    if conteudo is None:
        avisar(request, nome, "erro")
        return redirecionar(f"/almoxarifado/devolucao-fornecedor/{id_devolucao}")
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def devolucao_fornecedor_acao(request: Request, id_devolucao: str, acao: str = "", motivo: str = "",
                              id_unidade: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import devolucoes_fornecedor as dvf
    usuario = exigir_modulo(request, MODULO)
    if acao == "finalizar":
        ok, msg = dvf.finalizar(id_devolucao, usuario["username"])
    elif acao == "cancelar":
        ok, msg = dvf.cancelar(id_devolucao, usuario["username"], motivo)
    elif acao == "cancelar_item":
        ok, msg = dvf.cancelar_item(id_devolucao, id_unidade, usuario["username"], motivo)
    else:
        ok, msg = False, "Ação inválida."
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/devolucao-fornecedor/{id_devolucao}")


def devolucoes_fornecedor_abertas(request: Request):
    """JSON para o painel da bipagem: devoluções abertas de quem está bipando."""
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import devolucoes_fornecedor as dvf
    usuario = exigir_modulo(request, MODULO)
    return JSONResponse({"abertas": dvf.abertas(usuario["username"])})


def romaneio_fornecedor_pdf(request: Request, ids: str = ""):
    from fastapi.responses import Response
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import romaneio_fornecedor as rom
    usuario = exigir_modulo(request, MODULO)
    conteudo, nome = rom.pdf([i for i in ids.split(",") if i.strip()], usuario.get("nome") or usuario["username"])
    if conteudo is None:
        avisar(request, nome, "erro")
        return redirecionar("/almoxarifado/romaneios-fornecedor")
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def consignado_aghu_consultar(request: Request, codigo: str = "", modulo: str = MODULO, aghu: str = ""):
    """nov/2026: AGHU associado ao código consignado, para preencher o cadastro sozinho (JSON).
    v18.4.7: com `aghu`, devolve os códigos consignados daquele AGHU."""
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import consignado_aghu
    exigir_modulo(request, modulo)
    if aghu:
        return JSONResponse({"ok": True, "opcoes": [dict(o) for o in consignado_aghu.de_aghu(aghu)]})
    linha = consignado_aghu.buscar(codigo)
    if not linha:
        return JSONResponse({"ok": False, "codigo": consignado_aghu.normalizar(codigo)})
    return JSONResponse({"ok": True, "codigo": linha["codigo_consignado"], "codigo_aghu": linha["codigo_aghu"],
                         "descricao": linha["descritivo_hospital"] or linha["descricao"] or ""})


def planilha_aghu_nf(request: Request, chave: str):
    """nov/2026: Excel da entrada desta NF (uma linha por material + lote + validade) para lançar no AGHU."""
    from fastapi.responses import Response
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import planilha_aghu
    exigir_modulo(request, MODULO)
    conteudo, nome = planilha_aghu.xlsx(chave)
    if conteudo is None:
        avisar(request, nome, "erro")
        return redirecionar(f"/almoxarifado/nf/{chave}")
    return Response(conteudo, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# ---------------------------------------------------------
# nov/2026 — caixas de consignado no almoxarifado
# ---------------------------------------------------------

BASE_CAIXAS = "/almoxarifado/caixas"


def caixas_lista(request: Request):
    from . import farmacia_controller as f
    return f.caixas_consignado_lista(request, modulo=MODULO, base=BASE_CAIXAS)


async def caixas_criar(request: Request):
    from . import farmacia_controller as f
    return await f.caixas_consignado_criar(request, modulo=MODULO, base=BASE_CAIXAS)


def caixa_ficha(request: Request, id_caixa: str):
    from . import farmacia_controller as f
    return f.caixa_consignado_ficha(request, id_caixa, modulo=MODULO, base=BASE_CAIXAS)


def reposicao_caixas(request: Request, de: str = "", ate: str = ""):
    """v18.11.8: o que saiu das caixas por uso e ainda não foi reposto."""
    from datetime import date, timedelta
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.config import rotulo_farmacia
    from ..providers.implementations.opme.services import reposicao_caixas as rep
    exigir_modulo(request, MODULO)
    if not de and not ate:
        de, ate = (date.today() - timedelta(days=30)).isoformat(), date.today().isoformat()
    linhas = rep.a_repor(de, ate)
    for l in linhas:
        l["farmacia_rotulo"] = ("Almoxarifado" if l.get("local") == "almoxarifado" else
                                ("A caminho · " if l.get("local") == "transito" else "")
                                + (rotulo_farmacia(l["farmacia"]) if l.get("farmacia") else "Farmácia"))
    return render(request, "almoxarifado/reposicao_caixas.html", {"de": de, "ate": ate, "linhas": linhas})


def caixa_saidas(request: Request, id_caixa: str, de: str = "", ate: str = ""):
    from . import farmacia_controller as f
    return f.caixa_consignado_saidas(request, id_caixa, de=de, ate=ate, modulo=MODULO, base=BASE_CAIXAS)


def caixa_adicionar(request: Request, id_caixa: str, codigo: str = "", id_unidade: str = "", quantidade: str = "1"):
    from . import farmacia_controller as f
    return f.caixa_consignado_adicionar(request, id_caixa, codigo, id_unidade, modulo=MODULO, base=BASE_CAIXAS,
                                        quantidade=quantidade)


def caixa_retirar(request: Request, id_caixa: str, id_unidade: str, motivo: str = ""):
    from . import farmacia_controller as f
    return f.caixa_consignado_retirar(request, id_caixa, id_unidade, motivo, modulo=MODULO, base=BASE_CAIXAS)


async def caixa_conferir(request: Request, id_caixa: str):
    from . import farmacia_controller as f
    return await f.caixa_consignado_conferir(request, id_caixa, modulo=MODULO, base=BASE_CAIXAS)


def caixa_etiqueta(request: Request, id_caixa: str):
    from . import farmacia_controller as f
    return f.caixa_consignado_etiqueta(request, id_caixa, modulo=MODULO, base=BASE_CAIXAS)


def caixa_qr(request: Request, id_caixa: str):
    from . import farmacia_controller as f
    return f.caixa_consignado_qr(request, id_caixa, modulo=MODULO)


def caixa_enviar(request: Request, id_caixa: str, farmacia: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import caixas_almox
    usuario = exigir_modulo(request, MODULO)
    ok, msg = caixas_almox.enviar(id_caixa, farmacia, usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"{BASE_CAIXAS}/{id_caixa}")


def caixa_cancelar_envio(request: Request, id_caixa: str, motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import caixas_almox
    usuario = exigir_modulo(request, MODULO)
    ok, msg = caixas_almox.cancelar_envio(id_caixa, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"{BASE_CAIXAS}/{id_caixa}")


# ---------------------------------------------------------
# nov/2026 — lançamento da NF no AGHU (robô)
# ---------------------------------------------------------

async def aghu_lancar(request: Request, chave: str):
    """Gera o link traceopme-aghu:// que a tela entrega ao robô deste computador."""
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import aghu_robo
    usuario = exigir_modulo(request, MODULO)
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    servidor = str((corpo or {}).get("servidor") or "")
    ok, msg, link = aghu_robo.iniciar(chave, usuario["username"], servidor)
    return JSONResponse({"ok": ok, "mensagem": msg, "link": link})


def aghu_instalador(request: Request):
    """Pacote para instalar o robô no computador de quem lança a nota."""
    from fastapi.responses import Response
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import aghu_robo
    exigir_modulo(request, MODULO)
    return Response(aghu_robo.instalador_zip(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="robo_nota_aghu.zip"'})


def aghu_marcar(request: Request, chave: str, acao: str = "", numero_nr: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import aghu_robo
    usuario = exigir_modulo(request, MODULO)
    ok, msg = aghu_robo.marcar(chave, acao, usuario["username"], numero_nr)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/almoxarifado/nf/{chave}#aghu")


# ---------------------------------------------------------
# v18.5 — robô do AGHU no servidor, com a tela do AGHU dentro do TraceOPME
# ---------------------------------------------------------

def _sessao_robo(request: Request, sessao: str):
    """v18.6: a sessão do robô serve a NF (almoxarifado) e a nota de consumo (farmácia)."""
    from ..helpers.web_helper import Redirecionamento, exigir_login
    from ..providers.implementations.opme.security import pode_acessar
    from ..providers.implementations.opme.services import aghu_remoto
    usuario = exigir_login(request)
    s = aghu_remoto.buscar(sessao, usuario["username"], admin=usuario["papel"] == "admin")
    modulo = "farmacia" if s is not None and s.tipo == "consumo" else MODULO
    if not pode_acessar(usuario["papel"], modulo):
        raise Redirecionamento("/?sem_permissao=1")
    return s


def aghu_web(request: Request, chave: str):
    """Tela "Lançar no AGHU" (robô no servidor) — nota fiscal de entrada."""
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import aghu_remoto, aghu_robo, planilha_aghu
    from ..providers.implementations.opme import db as _db
    usuario = exigir_modulo(request, MODULO)
    nota = _db.consultar_um("SELECT chave_nf, numero_nf, fornecedor FROM notas_fiscais WHERE chave_nf = ?", (chave,))
    ativa = aghu_remoto.ativa_da_nota(chave)
    situacao = aghu_robo.situacao(chave) if nota else {}
    linhas = len(planilha_aghu.linhas(chave)) if nota else 0
    voltar = f"/almoxarifado/nf/{chave}#aghu"
    return render(request, "almoxarifado/aghu_web.html", {
        "nota": nota, "situacao": situacao, "linhas": linhas,
        "sessao": ativa.id if ativa and (ativa.usuario == usuario["username"] or usuario["papel"] == "admin") else "",
        "ocupada_por": ativa.nome if ativa and ativa.usuario != usuario["username"] else "",
        "robo": {
            "titulo": f"Lançar no AGHU — NF {nota['numero_nf']}" if nota else "Lançar no AGHU",
            "rotulo": f"NF {nota['numero_nf']}" if nota else "",
            "existe": bool(nota), "voltar": voltar,
            "iniciar": f"/almoxarifado/nf/{chave}/aghu/web/iniciar",
            "ja_lancada": (f"Esta NF já está lançada no AGHU ({situacao.get('lancada_por') or ''})."
                           if situacao.get("status") == "lancada" else ""),
            "pode_iniciar": linhas > 0,
            "passos": ["A NF precisa estar <strong>cadastrada no AGHU</strong> (o cadastro da nota continua manual).",
                       f"Clique em <strong>Iniciar</strong>: a tela do AGHU abre ocupando a janela toda ({linhas} linha(s) da planilha).",
                       "Faça o login, abra <em>Estoque → Gerar Nota de Recebimento sem AF</em> e escolha a NF.",
                       "Clique em <strong>Pronto, continuar</strong> (barra de cima): o robô inclui materiais e lotes. "
                       "No fim, confira e clique em <strong>Gravar</strong> no AGHU."],
        },
    })


async def aghu_web_iniciar(request: Request, chave: str):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import aghu_remoto
    usuario = exigir_modulo(request, MODULO)
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    corpo = corpo if isinstance(corpo, dict) else {}
    ok, msg, sid = aghu_remoto.iniciar(chave, usuario["username"], usuario.get("nome") or "",
                                       corpo.get("largura") or aghu_remoto.LARGURA, corpo.get("altura") or aghu_remoto.ALTURA)
    return JSONResponse({"ok": ok, "mensagem": msg, "sessao": sid})


def aghu_web_estado(request: Request, sessao: str, desde: int = 0):
    from fastapi.responses import JSONResponse
    s = _sessao_robo(request, sessao)
    if not s:
        return JSONResponse({"ok": False, "mensagem": "Este lançamento não existe mais (o servidor pode ter reiniciado)."})
    return JSONResponse(s.estado(desde))


def aghu_web_tela(request: Request, sessao: str):
    from fastapi.responses import Response
    s = _sessao_robo(request, sessao)
    if not s or not s.quadro:
        return Response(status_code=204)
    return Response(s.quadro, media_type="image/jpeg")


def aghu_web_fluxo(request: Request, sessao: str):
    """v18.5.1: a tela do AGHU em fluxo contínuo (um quadro a cada mudança)."""
    from fastapi.responses import Response, StreamingResponse
    s = _sessao_robo(request, sessao)
    if not s:
        return Response(status_code=404)
    return StreamingResponse(s.fluxo(), media_type="application/octet-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


async def aghu_web_entrada(request: Request, sessao: str):
    """Clique / tecla na tela do AGHU. NÃO é auditado nem registrado: pode ser a senha."""
    from fastapi.responses import JSONResponse
    s = _sessao_robo(request, sessao)
    if not s:
        return JSONResponse({"ok": False})
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    eventos = corpo.get("eventos") if isinstance(corpo, dict) else None
    aceitos = sum(1 for ev in (eventos or [])[:200] if isinstance(ev, dict) and s.entrada(ev))
    return JSONResponse({"ok": True, "aceitos": aceitos})


async def aghu_web_responder(request: Request, sessao: str):
    from fastapi.responses import JSONResponse
    s = _sessao_robo(request, sessao)
    if not s:
        return JSONResponse({"ok": False})
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    s.responder(str((corpo or {}).get("resposta") or ""))
    return JSONResponse({"ok": True})


def aghu_web_cancelar(request: Request, sessao: str):
    from fastapi.responses import JSONResponse
    s = _sessao_robo(request, sessao)
    if s:
        s.cancelar()
    return JSONResponse({"ok": bool(s)})


def saidas_outros(request: Request, de: str = "", ate: str = "", destino: str = ""):
    """v18.14: saídas do estoque do almoxarifado para outros procedimentos."""
    from . import farmacia_controller as f
    return f.saidas_outros(request, de=de, ate=ate, destino=destino,
                           modulo=MODULO, base="/almoxarifado")


def saida_outros_desfazer(request: Request, id_unidade: str, motivo: str = ""):
    """v18.14: desfaz uma saída do almoxarifado bipada por engano."""
    from . import farmacia_controller as f
    return f.saida_outros_desfazer(request, id_unidade, motivo, modulo=MODULO, base="/almoxarifado")
