"""Controller — Farmácia (TraceOPME).

Regras de tela do módulo, portadas de app/routers/farmacia.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/farmacia.py.
Original:
    Módulo Farmácia (v17).
    
    A farmácia não movimenta estoque no sistema: o material continua no estoque
    do almoxarifado até ser usado. Aqui ela monta e confere as CAIXAS DE CONSIGNADO
    e, com a própria senha, confirma as devoluções (na tela de devolução da sala).
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

MODULO = "farmacia"
BASE_CAIXAS = "/farmacia/caixas-consignado"


def unidade_da_farmacia(request: Request) -> str:
    """v17: unidade em que a farmácia está trabalhando (Bloco ou Hemodinâmica)."""
    from ..providers.implementations.opme.config import UNIDADES_ATIVAS
    valor = request.session.get("unidade_farmacia", "")
    return valor if valor in UNIDADES_ATIVAS else ""


def _contexto_unidade(request: Request) -> dict:
    from ..providers.implementations.opme.config import UNIDADES_ATIVAS
    return {"unidade_atual": unidade_da_farmacia(request), "unidades": UNIDADES_ATIVAS,
            "acao_unidade": "/farmacia/unidade",
            "pergunta_unidade": "Para qual unidade a farmácia está trabalhando?"}


def escolher_unidade(request: Request, unidade: str = (""), proximo: str = ("")):
    from ..providers.implementations.opme.config import UNIDADES_ATIVAS, rotulo_unidade
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    if unidade in UNIDADES_ATIVAS:
        request.session["unidade_farmacia"] = unidade
        # A unidade é também o estoque da farmácia (Bloco / Hemodinâmica): é dele
        # que a dispensação sai e é nele que entra o que o almoxarifado envia.
        from ..providers.implementations.opme.config import FARMACIAS
        if unidade in FARMACIAS:
            request.session["farmacia"] = unidade
        avisar(request, f"Farmácia trabalhando agora em: {rotulo_unidade(unidade)}.", "sucesso")
    return redirecionar(proximo if proximo.startswith("/farmacia") else "/farmacia")


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import alertas, caixas_consignado
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    from ..providers.implementations.opme import db
    from ..providers.implementations.opme.services import devolucoes, dispensacoes
    from ..providers.implementations.opme.services import usos_sem_dispensacao
    lista = caixas_consignado.listar()
    unidade = unidade_da_farmacia(request)
    from ..providers.implementations.opme.services import relatorios as _rel
    _epf = _rel.estoque_por_farmacia()
    return render(request, "farmacia/hub.html", _contexto_unidade(request) | {
        "dispensacoes_pendentes": len([d for d in dispensacoes.listar_pendentes()
                                       if not unidade or d["unidade"] == unidade]),
        "usos_sem_dispensacao": len([u for u in usos_sem_dispensacao.pendentes()
                                     if not unidade or u["unidade"] == unidade]),
        "devolucoes_pendentes": len(devolucoes.listar_pendentes()),
        "envios_a_receber": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_a_receber(unidade),
        "envios_pendencias": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_pendencias(unidade),
        "devolucoes_almox_aguardando": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_a_receber(unidade, "farmacia_almox"),
        "nao_recebidos": __import__("src.providers.implementations.opme.services.dispensacoes", fromlist=["x"]).contar_nao_recebidos(unidade),
        # v18.6: prontuários de hoje com uso e nota de consumo ainda não lançada no AGHU
        "nota_consumo_pendentes": len(__import__("src.providers.implementations.opme.services.nota_consumo", fromlist=["x"])
                                      .prontuarios_com_uso(__import__("src.providers.implementations.opme.utils", fromlist=["x"]).hoje_iso(),
                                                           unidade, pendentes=True)),
        "transferencias_a_receber": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_a_receber(unidade, "farmacia_farmacia"),
        "devolucoes_almox_pendencias": __import__("src.providers.implementations.opme.services.remessas", fromlist=["x"]).contar_pendencias(unidade, "farmacia_almox"),
        "a_concluir": len([a for a in __import__("src.providers.implementations.opme.services.fechamento", fromlist=["x"]).a_concluir(unidade)
                           if not a["a_conferir"]]),
        "caixas": lista,
        "caixas_sala": __import__("src.providers.implementations.opme.services.caixas_sala", fromlist=["x"]).contar(unidade),
        "estoque_por_farmacia": _epf,
        "estoque_farmacia": _epf.get(unidade, 0) if unidade in _epf else sum(_epf.values()),
        "nomes_farmacias": {"BLOCO CIRURGICO": "Bloco", "HEMODINAMICA - PDT": "Hemodinâmica"},
        "bloqueadas": sum(1 for c in lista if c["bloqueada"]),
        "caixas_chegando": len(__import__("src.providers.implementations.opme.services.caixas_almox", fromlist=["x"]).a_receber(unidade)),
        "alertas": alertas.abertos_do_modulo(MODULO),
    })


def caixas_consignado_lista(request: Request, modulo: str = MODULO, base: str = BASE_CAIXAS):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas_consignado
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, modulo)
    from ..providers.implementations.opme.config import FARMACIAS
    from ..providers.implementations.opme.services import caixas_almox
    if base != BASE_CAIXAS:
        # nov/2026: caixas do almoxarifado (montando e a caminho da farmácia).
        return render(request, "farmacia/caixas_consignado.html", {
            "modo": "almoxarifado", "base": base, "farmacias": FARMACIAS,
            "caixas": caixas_almox.listar((caixas_almox.ALMOX, caixas_almox.TRANSITO)),
            "nas_farmacias": caixas_almox.listar((caixas_almox.FARMACIA,))})
    return render(request, "farmacia/caixas_consignado.html", {
        "modo": "farmacia", "base": base, "caixas": caixas_consignado.listar(),
        "chegando": caixas_almox.a_receber(unidade_da_farmacia(request))})


async def caixas_consignado_criar(request: Request, modulo: str = MODULO, base: str = BASE_CAIXAS):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_consignado
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, modulo)
    from ..providers.implementations.opme.services import caixas_almox
    criar = caixas_almox.criar if base != BASE_CAIXAS else caixas_consignado.criar
    ok, mensagem, id_caixa = criar(dict(await request.form()), usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"{base}/{id_caixa}" if ok
                        else base)


def _render_ficha(request: Request, id_caixa: str, base: str = BASE_CAIXAS, **extra):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas, caixas_consignado
    from ..helpers.web_helper import redirecionar
    caixa = caixas_consignado.buscar(id_caixa)
    if not caixa:
        return redirecionar(base)
    from ..providers.implementations.opme.config import FARMACIAS, rotulo_farmacia
    from ..providers.implementations.opme.services import caixas_almox
    local = caixas_almox.local(caixa)
    return render(request, "farmacia/caixa_consignado.html", {
        "base": base, "modo": "almoxarifado" if base != BASE_CAIXAS else "farmacia", "local": local,
        "farmacias": FARMACIAS, "farmacia_rotulo": rotulo_farmacia(caixa["farmacia"]) if caixa.get("farmacia") else "",
        "somente_leitura": bool(_bloqueio_de_local(caixa, base)), "motivo_leitura": _bloqueio_de_local(caixa, base),
        "caixa": caixa,
        "itens": caixas.conteudo(caixa["id_caixa"]),
        "resumo": caixas_consignado.resumo_conteudo(caixa["id_caixa"]),
        "escolha": [], "codigo_digitado": "",
    } | extra)


def caixa_consignado_saidas(request: Request, id_caixa: str, de: str = "", ate: str = "",
                            modulo: str = MODULO, base: str = BASE_CAIXAS):
    """v18.11.7: saídas da caixa numa tela própria (botão "Saídas" na lista), com período."""
    from ..helpers.web_helper import exigir_modulo, redirecionar, render
    from ..providers.implementations.opme.services import caixas, caixas_consignado
    from ..providers.implementations.opme.utils import texto
    exigir_modulo(request, modulo)
    caixa = caixas_consignado.buscar(id_caixa)
    if not caixa:
        return redirecionar(base)
    if not texto(de) and not texto(ate):
        from datetime import date, timedelta
        de = (date.today() - timedelta(days=30)).isoformat()
        ate = date.today().isoformat()
    return render(request, "farmacia/caixa_saidas.html", {
        "base": base, "caixa": caixa, "de": de, "ate": ate,
        "saidas": caixas.saidas(caixa["id_caixa"], 2000, de=de, ate=ate),
    })


def _bloqueio_de_local(caixa: dict | None, base: str) -> str:
    """nov/2026: quem pode mexer na caixa depende de onde ela está."""
    from ..providers.implementations.opme.services import caixas_almox
    if not caixa:
        return ""
    local = caixas_almox.local(caixa)
    if local == caixas_almox.TRANSITO:
        return "A caixa está a caminho da farmácia, aguardando a ciência do recebimento."
    if base == BASE_CAIXAS and local == caixas_almox.ALMOX:
        return "A caixa está no almoxarifado. Ela chega à farmácia quando o almoxarifado dispensar."
    if base != BASE_CAIXAS and local == caixas_almox.FARMACIA:
        return "A caixa está na farmácia; quem completa e movimenta agora é a farmácia."
    return ""


def caixa_consignado_ficha(request: Request, id_caixa: str, modulo: str = MODULO, base: str = BASE_CAIXAS):
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, modulo)
    return _render_ficha(request, id_caixa, base=base)


def caixa_consignado_adicionar(request: Request, id_caixa: str, codigo: str = (""),
                               id_unidade: str = (""), modulo: str = MODULO, base: str = BASE_CAIXAS,
                               quantidade: str = "1"):
    """Coloca um item na caixa. Aceita código de barras, série ou o código AGHU.

    Quando o código responde a mais de um lote/validade, a tela mostra as opções
    para a pessoa escolher — o sistema não escolhe sozinho.
    """
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas, caixas_consignado
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, modulo)
    caixa_atual = caixas_consignado.buscar(id_caixa)
    recusa = _bloqueio_de_local(caixa_atual, base)
    if recusa:
        avisar(request, recusa, "erro")
        return redirecionar(f"{base}/{id_caixa}")
    alvo = id_unidade
    if not alvo:
        grupos = caixas_consignado.candidatos_para_caixa(codigo, so_almoxarifado=base != BASE_CAIXAS,
                                                         farmacia=(caixa_atual or {}).get("farmacia") or "")
        if not grupos:
            onde = ("no estoque do almoxarifado" if base != BASE_CAIXAS else
                    "no estoque desta farmácia (material do almoxarifado precisa ser enviado e recebido "
                    "na farmácia antes de entrar na caixa)")
            avisar(request, (f"Nenhum item {onde} responde a “{codigo}”. Item que já está em outra "
                             f"caixa, usado ou vencido também não entra."), "erro")
            return redirecionar(f"{base}/{id_caixa}")
        if len(grupos) > 1 or grupos[0].get("lote_nao_encontrado"):
            return _render_ficha(request, id_caixa, base=base, escolha=grupos, codigo_digitado=codigo,
                                 lote_nao_encontrado=grupos[0].get("lote_nao_encontrado") or "")
        alvo = grupos[0]["id_unidade"]
    # v18.12: "Unidades por bip" — várias unidades iguais (mesmo lote) num bip só.
    try:
        qtd = max(1, min(200, int(quantidade or 1)))
    except (TypeError, ValueError):
        qtd = 1
    extras = caixas_consignado.iguais_livres(alvo, qtd - 1) if qtd > 1 else []
    if qtd > 1 and len(extras) < qtd - 1:
        avisar(request, (f"Só há {len(extras) + 1} unidade(s) deste lote disponível(is) no estoque — "
                         f"nada entrou na caixa. Ajuste a quantidade e bipe de novo."), "erro")
        return redirecionar(f"{base}/{id_caixa}")
    r = caixas.adicionar_item(id_caixa, alvo, usuario["username"])
    entraram = 1 if r.get("ok") else 0
    if r.get("ok"):
        for outro in extras:
            r2 = caixas.adicionar_item(id_caixa, outro, usuario["username"])
            if not r2.get("ok"):
                break
            entraram, r = entraram + 1, r2
    avisar(request, (f"{f'{entraram}× ' if entraram > 1 else ''}{r['item']['xProd']} (lote {r['item'].get('nLote') or '—'}) "
                     f"entrou na caixa — {r['total']} item(ns) dentro.") if r.get("ok") else r["mensagem"],
           "sucesso" if r.get("ok") else "erro")
    return redirecionar(f"{base}/{id_caixa}")


def caixa_consignado_retirar(request: Request, id_caixa: str, id_unidade: str,
                             motivo: str = (""), modulo: str = MODULO, base: str = BASE_CAIXAS):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, modulo)
    from ..providers.implementations.opme.services import caixas_consignado
    recusa = _bloqueio_de_local(caixas_consignado.buscar(id_caixa), base)
    if recusa:
        avisar(request, recusa, "erro")
        return redirecionar(f"{base}/{id_caixa}")
    ok, mensagem = caixas.retirar_item(id_caixa, id_unidade, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"{base}/{id_caixa}")


async def caixa_consignado_conferir(request: Request, id_caixa: str, modulo: str = MODULO, base: str = BASE_CAIXAS):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_consignado
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, modulo)
    recusa = _bloqueio_de_local(caixas_consignado.buscar(id_caixa), base)
    if recusa:
        avisar(request, recusa, "erro")
        return redirecionar(f"{base}/{id_caixa}")
    formulario = await request.form()
    ok, mensagem = caixas_consignado.conferir(
        id_caixa, usuario["username"], formulario.get("motivo", ""), formulario.getlist("faltantes"))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"{base}/{id_caixa}")


def caixa_consignado_etiqueta(request: Request, id_caixa: str, modulo: str = MODULO, base: str = BASE_CAIXAS):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas_consignado, etiquetas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, modulo)
    caixa = caixas_consignado.buscar(id_caixa)
    if not caixa:
        return redirecionar(base)
    return render(request, "farmacia/caixa_consignado_etiqueta.html",
                  {"caixa": caixa, "base": base, "qr_disponivel": etiquetas.qr_disponivel()})


def caixa_consignado_qr(request: Request, id_caixa: str, modulo: str = MODULO):
    from fastapi.responses import Response
    from ..providers.implementations.opme.services import caixas_consignado, etiquetas
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, modulo)
    caixa = caixas_consignado.buscar(id_caixa)
    if not caixa:
        return Response("Caixa não encontrada.", status_code=404)
    try:
        png = etiquetas.gerar_png(caixa["id_caixa"], legenda=caixa["id_caixa"])
    except etiquetas.QRIndisponivel as erro:
        return Response(str(erro), status_code=503, media_type="text/plain; charset=utf-8")
    return Response(png, media_type="image/png")





# ---------------------------------------------------------------- caixa na sala pelo dia
def caixas_sala_lista(request: Request):
    from ..providers.implementations.opme.config import locais
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas_consignado, caixas_sala
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    unidade = unidade_da_farmacia(request)
    ativos = caixas_sala.listar(unidade)
    return render(request, "farmacia/caixas_sala.html", _contexto_unidade(request) | {
        "ativos": ativos,
        "recentes": caixas_sala.listar(unidade, status=("conferida", "cancelada"), limite=20),
        "locais": [l for l in locais() if not unidade or l[0] == unidade],
        "caixas_livres": [c for c in caixas_consignado.listar()
                          if not c["bloqueada"] and not caixas_sala.ativo_da_caixa(c["id_caixa"])],
    })


def caixas_sala_enviar(request: Request, codigo: str = (""), local: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_sala
    from ..providers.implementations.opme.utils import normalizar_codigo
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    unidade, _, sala = local.partition("|")
    ok, msg, _id = caixas_sala.enviar(normalizar_codigo(codigo), unidade, sala, usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/farmacia/caixas-sala")


def caixas_sala_cancelar(request: Request, id_turno: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, msg = caixas_sala.cancelar_envio(id_turno, usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/farmacia/caixas-sala")


def caixa_sala_ficha(request: Request, id_turno: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    turno = caixas_sala.buscar(id_turno)
    if not turno:
        return redirecionar("/farmacia/caixas-sala")
    return render(request, "farmacia/caixa_sala.html", {"t": turno, "itens": caixas_sala.itens(id_turno)})


def caixa_sala_identificar(request: Request, id_turno: str, codigo: str = ""):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import caixas_sala
    exigir_modulo(request, MODULO)
    return JSONResponse(caixas_sala.identificar_item(id_turno, codigo))


async def caixa_sala_conferir(request: Request, id_turno: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    presentes = None if str(form.get("modo") or "") == "confere" else set(form.getlist("presente"))
    ok, msg = caixas_sala.conferir(id_turno, usuario, presentes)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/caixas-sala/{id_turno}")


def devolucoes_lista(request: Request):
    """v17 — devoluções bipadas pela sala aguardando a senha da farmácia."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import devolucoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    # v18.12: com duas farmácias, a lista mostra a unidade de cada paciente e traz
    # primeiro os da unidade em que a pessoa está trabalhando.
    from ..providers.implementations.opme.config import farmacia_da_unidade, rotulo_unidade
    minha = unidade_da_farmacia(request)
    pendentes = devolucoes.listar_pendentes()
    for x in pendentes:
        x["unidade_rotulo"] = rotulo_unidade(x.get("unidade")) if x.get("unidade") else ""
        x["outra_unidade"] = bool(minha and farmacia_da_unidade(x.get("unidade"))
                                  and farmacia_da_unidade(x.get("unidade")) != farmacia_da_unidade(minha))
    pendentes.sort(key=lambda x: x["outra_unidade"])
    return render(request, "farmacia/devolucoes.html", _contexto_unidade(request) | {
        "pendentes": pendentes,
        "confirmadas": devolucoes.recentes_confirmadas(),
    })


def devolucao_ficha(request: Request, id_devolucao: str):
    from ..helpers.web_helper import redirecionar
    return redirecionar(f"/devolucoes/{id_devolucao}")


# ---------------------------------------------------------
# v17 (out/2026) — procedimentos a concluir (a farmácia encerra)
# ---------------------------------------------------------

def procedimentos_a_concluir(request: Request):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import fechamento
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "farmacia/a_concluir.html", _contexto_unidade(request) | {
        "lista": fechamento.a_concluir(unidade_da_farmacia(request)),
    })


def procedimento(request: Request, id_atendimento: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.domain import UTILIZADO
    from ..providers.implementations.opme.services import atendimentos, devolucoes, fechamento
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    at = atendimentos.buscar(id_atendimento)
    if not at:
        return redirecionar("/farmacia/procedimentos-a-concluir")
    dev = devolucoes.pendente_do_atendimento(id_atendimento)
    return render(request, "farmacia/procedimento.html", {
        "atendimento": at,
        "descricao": atendimentos.descrever(at),
        "finalizado": fechamento.finalizado(at),
        "usados": [m for m in atendimentos.materiais(id_atendimento) if m["status"] == UTILIZADO],
        "devolucao": dev if dev and devolucoes.itens(dev["id_devolucao"], so_pendentes=True) else None,
        "pendencias": fechamento.pendencias(id_atendimento),
    })


def procedimento_receber(request: Request, id_atendimento: str, id_unidade: str = (""),
                         id_caixa: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import fechamento
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = fechamento.receber_pendencia(id_atendimento, usuario, id_unidade=id_unidade,
                                                id_caixa=id_caixa)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/procedimento/{id_atendimento}")


def procedimento_concluir(request: Request, id_atendimento: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import fechamento
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = fechamento.concluir(id_atendimento, usuario)
    avisar(request, ("Procedimento concluído pela farmácia. " + mensagem) if ok else mensagem,
           "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/procedimento/{id_atendimento}")


# ---------------------------------------------------------
# v17 — dispensação para a sala (por paciente)
# ---------------------------------------------------------

def atendimentos_para_dispensar(request: Request, data: str = "", unidade: str = "",
                                prontuario: str = "", operacao: str = ""):
    """Escolha do paciente para dispensar. Mostra os atendimentos abertos do dia."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import atendimentos
    from ..providers.implementations.opme.utils import hoje_iso
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    data = data or hoje_iso()
    if not unidade and "unidade" not in request.query_params:
        unidade = unidade_da_farmacia(request)
    return render(request, "farmacia/atendimentos.html", _contexto_unidade(request) | {
        "atendimentos": (lista := atendimentos.listar(data=data, unidade=unidade, prontuario=prontuario,
                                                      somente_abertos=True)),
        "solicitacoes": __import__("src.providers.implementations.opme.services.solicitacoes", fromlist=["x"]).resumo_lista(
            [a["id_atendimento"] for a in lista]),
        "data": data, "unidade": unidade, "prontuario": prontuario,
    })


def atendimento_farmacia(request: Request, id_atendimento: str):
    from ..helpers.web_helper import redirecionar
    return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}")


def atendimento_cancelar(request: Request, id_atendimento: str, motivo: str = (""),
                         detalhe: str = (""), voltar: str = ("")):
    """Procedimento cancelado antes de a sala receber o material: a farmácia
    cancela e o que ela dispensou volta direto para o estoque dela."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import atendimentos
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = atendimentos.cancelar(id_atendimento, usuario["username"], motivo, detalhe,
                                         pela="farmacia")
    avisar(request, mensagem, "sucesso" if ok else "erro")
    if ok:
        return redirecionar("/farmacia/atendimentos")
    destino = voltar if voltar.startswith("/") and not voltar.startswith("//") else \
        f"/bipagem/dispensar_sala?atendimento={id_atendimento}"
    return redirecionar(destino)


def estoque_farmacia(request: Request, farmacia: str = "", busca: str = ""):
    """Estoque de cada farmácia (Bloco e Hemodinâmica), por material, lote e validade."""
    from ..providers.implementations.opme.config import FARMACIAS
    from ..providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, TRANSITO_FARMACIA
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import estoque, relatorios
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    if farmacia not in FARMACIAS:
        farmacia = unidade_da_farmacia(request) if unidade_da_farmacia(request) in FARMACIAS else next(iter(FARMACIAS))
    achado = estoque.estoque_consolidado_detalhado(EM_ESTOQUE_FARMACIA, busca, farmacia)
    linhas = achado["linhas"]
    return render(request, "farmacia/estoque.html", {
        "farmacia": farmacia, "farmacias": FARMACIAS, "busca": busca, "linhas": linhas,
        "aviso_lote": achado["aviso"], "onde_esta": achado["onde"],
        "total": sum(l["quantidade"] for l in linhas),
        "por_farmacia": relatorios.estoque_por_farmacia(),
        "a_caminho": len(estoque.estoque_consolidado(TRANSITO_FARMACIA, "", farmacia)) and
                     sum(l["quantidade"] for l in estoque.estoque_consolidado(TRANSITO_FARMACIA, "", farmacia)),
    })


def recebimentos(request: Request, todas: int = 0):
    """Envios do almoxarifado para esta farmácia: conferir e dar ciência."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    farmacia = "" if todas else unidade_da_farmacia(request)
    t = remessas.TRANSFERENCIA

    def _de(linhas, sentido):
        for l in linhas:
            l["sentido"] = sentido
            l["de"] = (l.get("farmacia_origem_rotulo") or "Farmácia") if sentido == t else "Almoxarifado"
        return linhas

    def _juntar(*listas):
        tudo = [x for lista in listas for x in lista]
        return sorted(tudo, key=lambda l: l.get("enviada_em") or l.get("conferida_em") or "", reverse=True)
    # v18: o que outra farmácia transferiu para esta também é recebido aqui.
    return render(request, "farmacia/recebimentos.html", _contexto_unidade(request) | {
        "enviadas": _juntar(_de(remessas.listar("enviada", farmacia), remessas.ENVIO),
                            _de(remessas.listar("enviada", farmacia, sentido=t), t)),
        "pendencias": _juntar(_de(remessas.pendencias(farmacia), remessas.ENVIO),
                              _de(remessas.pendencias(farmacia, sentido=t), t)),
        "conferidas": _juntar(_de(remessas.listar("conferida", farmacia, limite=20), remessas.ENVIO),
                              _de(remessas.listar("conferida", farmacia, limite=10, sentido=t), t))[:25],
        "filtrando": bool(farmacia)})


def recebimento_tela(request: Request, id_remessa: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem:
        return redirecionar("/farmacia/recebimentos")
    if rem["sentido"] == remessas.DEVOLUCAO:
        return redirecionar(f"/farmacia/devolucao-almox/{id_remessa}")
    if rem["sentido"] == remessas.TRANSFERENCIA and rem["status"] == "aberta":
        return redirecionar(f"/farmacia/transferencia/{id_remessa}")
    return render(request, "farmacia/recebimento.html", {
        "rem": rem, "tratativas": rem["tratativas"],
        # v18.35: o que já foi bipado nesta conferência, para a tela voltar
        # exatamente onde parou.
        "conferidos": remessas.conferidos(id_remessa),
        "rotas": {"identificar": f"/farmacia/recebimento/{id_remessa}/identificar",
                  "conferir": f"/farmacia/recebimento/{id_remessa}/conferir",
                  "marcar": f"/farmacia/recebimento/{id_remessa}/conferido",
                  "recebi": "/farmacia/recebimento/item/{id}/recebi",
                  "pagina": f"/farmacia/recebimento/{id_remessa}", "voltar": "/farmacia/recebimentos"}})


async def recebimento_conferido(request: Request, id_remessa: str):
    """v18.35: grava (ou desfaz) o bipe da conferência, item a item."""
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    ids = [v for v in form.getlist("id_item")]
    marcar = str(form.get("marcar") or "1") != "0"
    ok, dados = remessas.marcar_conferido(id_remessa, ids, usuario, marcar)
    return JSONResponse({"ok": ok, **dados})


def recebimento_identificar(request: Request, id_remessa: str, codigo: str = ""):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] not in (remessas.ENVIO, remessas.TRANSFERENCIA):
        return JSONResponse({"ok": False, "mensagem": "Envio não encontrado."})
    return JSONResponse(remessas.identificar(id_remessa, codigo))


async def recebimento_conferir(request: Request, id_remessa: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    rem = remessas.buscar(id_remessa)
    if not rem or rem["sentido"] not in (remessas.ENVIO, remessas.TRANSFERENCIA):
        return redirecionar("/farmacia/recebimentos")
    form = await request.form()
    modo = "bipando" if form.get("modo") == "bipando" else "lista"
    recebidos = {str(v) for v in form.getlist("recebido")}
    if modo == "bipando":
        # v18.35: a conferência fica gravada no servidor; a tela é só o espelho.
        # Se a página estiver velha, o que vale é o que foi bipado de verdade.
        guardados = set(remessas.conferidos(id_remessa))
        recebidos = guardados or {str(v) for v in form.getlist("bipado")}
    ok, msg = remessas.conferir(id_remessa, recebidos, usuario, modo, str(form.get("observacao") or ""))
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/recebimento/{id_remessa}")


def recebimento_recebi_depois(request: Request, id_item: int, voltar: str = ("/farmacia/recebimentos")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import remessas
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) not in (remessas.ENVIO, remessas.TRANSFERENCIA):
        avisar(request, "Esta pendência é de uma devolução ao almoxarifado — quem dá ciência é o almoxarifado.", "erro")
        return redirecionar("/farmacia/devolucoes-almox#pendencias")
    ok, msg = remessas.tratar(id_item, "recebido_depois", usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(voltar if voltar.startswith("/farmacia") else "/farmacia/recebimentos")


def solicitacoes_em_aberto(request: Request, todas: int = 0):
    """Pedidos de OPME da sala ainda não atendidos (qualquer data), da unidade
    que esta farmácia atende — ou de todas, se pedir."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    unidade = "" if todas else unidade_da_farmacia(request)
    return render(request, "farmacia/solicitacoes.html", _contexto_unidade(request) | {
        "pedidos": solicitacoes.em_aberto(unidade), "filtrando": bool(unidade), "todas": bool(todas)})


def solicitacao_imprimir(request: Request, id_atendimento: str):
    """v18.28: folha de separação do pedido, para a farmácia imprimir e separar
    o material com a lista na mão (pedido da Camila, 18/11/2026)."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import atendimentos, solicitacoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    from ..providers.implementations.opme import db
    from ..providers.implementations.opme.utils import data_hora_br
    atendimento = atendimentos.buscar(id_atendimento) or {}
    return render(request, "farmacia/solicitacao_imprimir.html", {
        "atendimento": atendimento,
        "descricao": atendimentos.descrever(atendimento) if atendimento else "",
        "sol": solicitacoes.situacao(id_atendimento),
        "unidade_atual": unidade_da_farmacia(request),
        "impresso_em": data_hora_br(db.agora()),
    })


def solicitacao_painel(request: Request, id_atendimento: str):
    """Pedaço da tela de dispensar redesenhado a cada bip (a lista com os checks)."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import atendimentos, solicitacoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "_solicitacao_painel.html", {
        "sol": solicitacoes.situacao(id_atendimento), "modo": "farmacia",
        "motivos_outro_codigo": solicitacoes.MOTIVOS_OUTRO_CODIGO,
        "motivos_falta": solicitacoes.MOTIVOS_FALTA,
        "atendimento": atendimentos.buscar(id_atendimento) or {}})


def solicitacao_manual(request: Request, id_atendimento: str, id_item: int, atendido: str = ("1")):
    """Linha sem código AGHU (ex.: cateter diagnóstico, tipo escrito pela sala)."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = solicitacoes.marcar_manual(id_atendimento, id_item, usuario["username"], atendido != "0")
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}")


async def solicitacao_outro_codigo(request: Request, id_atendimento: str, id_item: int):
    """Item com AGHU atendido por material bipado com outro código (com motivo)."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    dados = await request.form()
    ids = [i for i in str(dados.get("unidades") or "").split(",") if i]
    if dados.get("desfazer"):
        ok, mensagem = solicitacoes.desfazer_vinculos(id_atendimento, id_item, usuario["username"])
    else:
        ok, mensagem = solicitacoes.vincular_outro_codigo(id_atendimento, id_item, ids,
                                                          str(dados.get("motivo") or ""), usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}")


async def solicitacao_falta(request: Request, id_atendimento: str, id_item: int):
    """v18.43: linha que a farmácia não tem como atender — falta de estoque."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    dados = await request.form()
    ok, mensagem = solicitacoes.marcar_falta(
        id_atendimento, id_item, str(dados.get("motivo") or ""), usuario["username"],
        falta=not dados.get("desfazer"))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}")


def finalizar_dispensa(request: Request, id_atendimento: str, motivo: str = ("")):
    """"Finalizar dispensa": confere a solicitação da sala antes do resumo/PDF.
    Faltando item, exige o motivo (fica registrado e a sala vê)."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = solicitacoes.finalizar(id_atendimento, usuario["username"], motivo)
    if not ok:
        avisar(request, mensagem, "erro")
        return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}#finalizar")
    return redirecionar(f"/dispensacoes/atendimento/{id_atendimento}/finalizada")


def dispensacoes_lista(request: Request):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import dispensacoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    unidade = unidade_da_farmacia(request)
    return render(request, "farmacia/dispensacoes.html", _contexto_unidade(request) | {
        "pendentes": [d for d in dispensacoes.listar_pendentes() if not unidade or d["unidade"] == unidade],
        "confirmadas": dispensacoes.recentes_confirmadas(),
    })


def usos_sem_dispensacao_lista(request: Request):
    """v17 — material usado na sala sem dispensação: a farmácia dá ciência."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import usos_sem_dispensacao
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    unidade = unidade_da_farmacia(request)
    return render(request, "farmacia/usos_sem_dispensacao.html", _contexto_unidade(request) | {
        "pendentes": [u for u in usos_sem_dispensacao.pendentes() if not unidade or u["unidade"] == unidade],
        "cientes": usos_sem_dispensacao.com_ciencia(),
    })


async def usos_sem_dispensacao_ciencia(request: Request):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import usos_sem_dispensacao
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    ok, mensagem = usos_sem_dispensacao.dar_ciencia(form.getlist("ids"), usuario,
                                                    str(form.get("observacao") or ""))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/farmacia/usos-sem-dispensacao")


def conciliacao(request: Request, inicio: str = "", fim: str = "", sala: str = "", unidade: str = "",
                prontuario: str = "", atendimento: str = "", formato: str = ""):
    """v17 — conciliação por sala: dispensado × usado × devolvido."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import dispensacoes
    from ..providers.implementations.opme.utils import data_iso, hoje_iso
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio = data_iso(inicio) or hoje_iso()
    fim = data_iso(fim) or inicio
    if not unidade and "unidade" not in request.query_params:
        unidade = unidade_da_farmacia(request)
    dados = dispensacoes.conciliacao(inicio, fim, unidade, sala, prontuario, atendimento)
    if formato == "csv":
        import csv, io
        from fastapi.responses import Response
        from ..providers.implementations.opme.config import rotulo_unidade
        from ..providers.implementations.opme.utils import data_br, data_hora_br
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(["Data do procedimento", "Unidade", "Sala", "Prontuário", "Paciente", "Material", "AGHU",
                    "Lote", "Caixa", "Dispensado em", "Dispensado por", "Recebido na sala por", "Desfecho"])
        for i in dados["itens"]:
            w.writerow([data_br(i["data_procedimento"]), rotulo_unidade(i["unidade"]), i["sala"], i["prontuario"],
                        i["paciente"] or "", i["descritivo_hospital"] or i["xProd"] or "", i["codigo_aghu"] or "",
                        i["nLote"] or "", i["id_caixa"] or "", data_hora_br(i["bipado_em"]), i["bipado_por"] or "",
                        i["recebido_por"] or "", i["rotulo_desfecho"]])
        for s in dados["sem_dispensacao"]:
            w.writerow([data_br(s["data_procedimento"]), rotulo_unidade(s["unidade"]), s["sala"], s["prontuario"],
                        s["paciente"] or "", s["descritivo_hospital"] or s["xProd"] or "", s["codigo_aghu"] or "",
                        s["nLote"] or "", "", "", "", "",
                        "Usado SEM dispensação" + (" — farmácia ciente" if s["situacao"] == "ciente" else " — sem ciência")])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="conciliacao_{inicio}_{fim}.csv"'})
    return render(request, "farmacia/conciliacao.html", _contexto_unidade(request) | dados | {
        "inicio": inicio, "fim": fim, "sala": sala, "unidade": unidade, "prontuario": prontuario,
        "atendimento": atendimento,
    })


# ---------------------------------------------------------
# nov/2026 — devolver material ao almoxarifado
# ---------------------------------------------------------

def _rotas_devolucao_almox(id_remessa: str) -> dict:
    return {"pagina": f"/farmacia/devolucao-almox/{id_remessa}", "bipar": f"/farmacia/devolucao-almox/{id_remessa}/bipar",
            "tirar": "/farmacia/devolucao-almox/item/{id}/tirar",
            "finalizar": f"/farmacia/devolucao-almox/{id_remessa}/finalizar",
            "cancelar": f"/farmacia/devolucao-almox/{id_remessa}/cancelar", "voltar": "/farmacia/devolucoes-almox",
            "trocar": "/farmacia/devolucoes-almox"}


def _devolucao_da_farmacia(id_remessa: str):
    from ..providers.implementations.opme.services import remessas
    rem = remessas.buscar(id_remessa)
    return rem if rem and rem["sentido"] == remessas.DEVOLUCAO else None


def devolucoes_almox(request: Request, todas: int = 0):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.config import FARMACIAS
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    farmacia = "" if todas else unidade_da_farmacia(request)
    d = remessas.DEVOLUCAO
    return render(request, "farmacia/devolucoes_almox.html", _contexto_unidade(request) | {
        "farmacias": FARMACIAS, "filtrando": bool(farmacia),
        "abertas": remessas.listar("aberta", farmacia, sentido=d),
        "enviadas": remessas.listar("enviada", farmacia, sentido=d),
        "conferidas": remessas.listar("conferida", farmacia, limite=20, sentido=d),
        "canceladas": remessas.listar("cancelada", farmacia, limite=10, sentido=d),
        "pendencias": remessas.pendencias(farmacia, sentido=d), "tratativas": remessas.TRATATIVAS_DEVOLUCAO})


def devolucao_almox_nova(request: Request, farmacia: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    ok, r = remessas.abrir(farmacia or unidade_da_farmacia(request), usuario["username"], remessas.DEVOLUCAO)
    if not ok:
        avisar(request, r, "erro")
        return redirecionar("/farmacia/devolucoes-almox")
    return redirecionar(f"/farmacia/devolucao-almox/{r}")


def devolucao_almox_tela(request: Request, id_remessa: str, busca: str = ""):
    from ..helpers.web_helper import exigir_modulo, redirecionar, render
    from ..providers.implementations.opme import db
    from ..providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    rem = _devolucao_da_farmacia(id_remessa)
    if not rem:
        return redirecionar("/farmacia/devolucoes-almox")
    total = int(db.escalar("SELECT COUNT(*) FROM unidades WHERE status = ? AND farmacia = ? AND COALESCE(id_caixa,'') = ''",
                           (EM_ESTOQUE_FARMACIA, rem["farmacia"])) or 0)
    return render(request, "farmacia/devolucao_almox.html", {
        "rem": rem, "tratativas": rem["tratativas"], "lista": remessas.lista_envio(id_remessa),
        "busca": busca, "resultados": remessas.disponiveis(busca, farmacia=rem["farmacia"]) if busca else [],
        "disponiveis_total": total, "rotas": _rotas_devolucao_almox(id_remessa)})


async def devolucao_almox_bipar(request: Request, id_remessa: str):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if not _devolucao_da_farmacia(id_remessa):
        return JSONResponse({"ok": False, "mensagem": "Devolução não encontrada."})
    c = await request.json()
    return JSONResponse(remessas.bipar(id_remessa, str(c.get("codigo") or ""), usuario["username"],
                                       c.get("quantidade", 1), str(c.get("grupo") or "")))


def devolucao_almox_tirar(request: Request, id_item: int):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme import db
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    sentido = db.escalar("SELECT r.sentido FROM remessa_itens i JOIN remessas r ON r.id_remessa = i.id_remessa "
                         "WHERE i.id_item = ?", (id_item,))
    if sentido != remessas.DEVOLUCAO:
        return JSONResponse({"ok": False, "mensagem": "Item não encontrado nesta devolução.", "lista": []})
    ok, msg, id_rem = remessas.remover_item(id_item, usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": msg, "lista": remessas.lista_envio(id_rem) if id_rem else []})


def devolucao_almox_finalizar(request: Request, id_remessa: str, observacao: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if not _devolucao_da_farmacia(id_remessa):
        return redirecionar("/farmacia/devolucoes-almox")
    ok, msg = remessas.finalizar_envio(id_remessa, usuario["username"], observacao)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/devolucao-almox/{id_remessa}")


def devolucao_almox_cancelar(request: Request, id_remessa: str, motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if not _devolucao_da_farmacia(id_remessa):
        return redirecionar("/farmacia/devolucoes-almox")
    ok, msg = remessas.cancelar(id_remessa, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/devolucao-almox/{id_remessa}")


def devolucao_almox_tratar(request: Request, id_item: int, acao: str = "", motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if acao not in ("voltou_farmacia", "divergencia"):
        avisar(request, "Escolha: voltou à farmácia ou divergência.", "erro")
        return redirecionar("/farmacia/devolucoes-almox#pendencias")
    ok, msg = remessas.tratar(id_item, acao, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/farmacia/devolucoes-almox#pendencias")


# ---------------------------------------------------------
# v18.4.3 — itens que a sala disse não ter recebido
# ---------------------------------------------------------

def nao_recebidos(request: Request, todas: int = 0):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import dispensacoes
    exigir_modulo(request, MODULO)
    farmacia = "" if todas else unidade_da_farmacia(request)
    return render(request, "farmacia/nao_recebidos.html", _contexto_unidade(request) | {
        "itens": dispensacoes.nao_recebidos(farmacia), "acoes": dispensacoes.ACOES_NAO_RECEBIDO,
        "filtrando": bool(farmacia)})


def tratar_nao_recebido(request: Request, id_unidade: str, acao: str = "", motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import dispensacoes
    usuario = exigir_modulo(request, MODULO)
    # v18.4.5: só a farmácia dona do material confere (a farmácia em que o usuário está trabalhando).
    ok, msg = dispensacoes.tratar_nao_recebido(id_unidade, acao, usuario["username"], motivo,
                                               farmacia=unidade_da_farmacia(request))
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/farmacia/nao-recebidos")


# ---------------------------------------------------------
# v18 — transferir material para a outra farmácia (Bloco ↔ Hemodinâmica)
# ---------------------------------------------------------

def _rotas_transferencia(id_remessa: str) -> dict:
    return {"pagina": f"/farmacia/transferencia/{id_remessa}", "bipar": f"/farmacia/transferencia/{id_remessa}/bipar",
            "tirar": "/farmacia/transferencia/item/{id}/tirar",
            "finalizar": f"/farmacia/transferencia/{id_remessa}/finalizar",
            "cancelar": f"/farmacia/transferencia/{id_remessa}/cancelar", "voltar": "/farmacia/transferencias",
            "trocar": "/farmacia/transferencias"}


def _transferencia(id_remessa: str):
    from ..providers.implementations.opme.services import remessas
    rem = remessas.buscar(id_remessa)
    return rem if rem and rem["sentido"] == remessas.TRANSFERENCIA else None


def transferencias(request: Request, todas: int = 0):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.config import FARMACIAS
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    atual = unidade_da_farmacia(request)
    origem = "" if todas or atual not in FARMACIAS else atual
    t = remessas.TRANSFERENCIA
    return render(request, "farmacia/transferencias.html", _contexto_unidade(request) | {
        "farmacias": FARMACIAS, "filtrando": bool(origem), "origem": origem,
        "destino": remessas.outra_farmacia(origem) if origem else "",
        "destino_rotulo": remessas.rotulo_farmacia(remessas.outra_farmacia(origem)) if origem else "",
        "abertas": remessas.listar("aberta", sentido=t, farmacia_origem=origem),
        "enviadas": remessas.listar("enviada", sentido=t, farmacia_origem=origem),
        "conferidas": remessas.listar("conferida", limite=20, sentido=t, farmacia_origem=origem),
        "canceladas": remessas.listar("cancelada", limite=10, sentido=t, farmacia_origem=origem),
        "a_receber": remessas.contar_a_receber(atual if atual in FARMACIAS else "", t),
        "pendencias": remessas.pendencias(sentido=t, farmacia_origem=origem),
        "tratativas": remessas.TRATATIVAS_TRANSFERENCIA})


def transferencia_nova(request: Request, farmacia: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    ok, r = remessas.abrir(farmacia or unidade_da_farmacia(request), usuario["username"], remessas.TRANSFERENCIA)
    if not ok:
        avisar(request, r, "erro")
        return redirecionar("/farmacia/transferencias")
    return redirecionar(f"/farmacia/transferencia/{r}")


def transferencia_tela(request: Request, id_remessa: str, busca: str = ""):
    from ..helpers.web_helper import exigir_modulo, redirecionar, render
    from ..providers.implementations.opme import db
    from ..providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
    from ..providers.implementations.opme.services import remessas
    exigir_modulo(request, MODULO)
    rem = _transferencia(id_remessa)
    if not rem:
        return redirecionar("/farmacia/transferencias")
    total = int(db.escalar("SELECT COUNT(*) FROM unidades WHERE status = ? AND farmacia = ? AND COALESCE(id_caixa,'') = ''",
                           (EM_ESTOQUE_FARMACIA, rem["farmacia_origem"])) or 0)
    return render(request, "farmacia/transferencia.html", {
        "rem": rem, "tratativas": rem["tratativas"], "lista": remessas.lista_envio(id_remessa),
        "busca": busca, "resultados": remessas.disponiveis(busca, farmacia=rem["farmacia_origem"]) if busca else [],
        "disponiveis_total": total, "rotas": _rotas_transferencia(id_remessa)})


async def transferencia_bipar(request: Request, id_remessa: str):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if not _transferencia(id_remessa):
        return JSONResponse({"ok": False, "mensagem": "Transferência não encontrada."})
    c = await request.json()
    return JSONResponse(remessas.bipar(id_remessa, str(c.get("codigo") or ""), usuario["username"],
                                       c.get("quantidade", 1), str(c.get("grupo") or "")))


def transferencia_tirar(request: Request, id_item: int):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) != remessas.TRANSFERENCIA:
        return JSONResponse({"ok": False, "mensagem": "Item não encontrado nesta transferência.", "lista": []})
    ok, msg, id_rem = remessas.remover_item(id_item, usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": msg, "lista": remessas.lista_envio(id_rem) if id_rem else []})


def transferencia_finalizar(request: Request, id_remessa: str, observacao: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if not _transferencia(id_remessa):
        return redirecionar("/farmacia/transferencias")
    ok, msg = remessas.finalizar_envio(id_remessa, usuario["username"], observacao)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/transferencia/{id_remessa}")


def transferencia_cancelar(request: Request, id_remessa: str, motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if not _transferencia(id_remessa):
        return redirecionar("/farmacia/transferencias")
    ok, msg = remessas.cancelar(id_remessa, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/transferencia/{id_remessa}")


def transferencia_tratar(request: Request, id_item: int, acao: str = "", motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import remessas
    usuario = exigir_modulo(request, MODULO)
    if remessas.sentido_do_item(id_item) != remessas.TRANSFERENCIA or acao not in ("voltou_origem", "divergencia"):
        avisar(request, "Escolha: voltou à farmácia de origem ou divergência.", "erro")
        return redirecionar("/farmacia/transferencias#pendencias")
    ok, msg = remessas.tratar(id_item, acao, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/farmacia/transferencias#pendencias")


# ---------------------------------------------------------
# nov/2026 — cadastro manual direto no estoque da farmácia
# ---------------------------------------------------------

def tela_manual(request: Request):
    from . import almoxarifado_controller as almox
    return almox.tela_manual(request, modulo=MODULO, base="/farmacia", farmacia_atual=unidade_da_farmacia(request))


async def salvar_manual(request: Request):
    from . import almoxarifado_controller as almox
    return await almox.salvar_manual(request, modulo=MODULO, base="/farmacia",
                                     farmacia_atual=unidade_da_farmacia(request))


def tela_etiquetas(request: Request, codigo: str = "", busca: str = "", tamanho: str = ""):
    from . import almoxarifado_controller as almox
    return almox.tela_etiquetas(request, codigo, busca, tamanho, modulo=MODULO, base="/farmacia")


def imagem_qr(request: Request, codigo: str, sem_legenda: int = 0):
    from . import almoxarifado_controller as almox
    return almox.imagem_qr(request, codigo, sem_legenda, modulo=MODULO)


def consignado_aghu_consultar(request: Request, codigo: str = "", aghu: str = ""):
    from . import almoxarifado_controller as almox
    return almox.consignado_aghu_consultar(request, codigo, modulo=MODULO, aghu=aghu)


# ---------------------------------------------------------
# nov/2026 — caixa vinda do almoxarifado: ciência do recebimento
# ---------------------------------------------------------

def caixa_consignado_receber(request: Request, id_caixa: str):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import caixas_almox
    usuario = exigir_modulo(request, MODULO)
    ok, msg = caixas_almox.receber(id_caixa, usuario, unidade_da_farmacia(request))
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"{BASE_CAIXAS}/{id_caixa}" if ok else BASE_CAIXAS)


# ---------------------------------------------------------
# v18.6 — Nota de Consumo no AGHU (o que foi bipado no paciente)
# ---------------------------------------------------------

def nota_consumo(request: Request, data: str = "", pendentes: int = 0):
    """Prontuários com uso no dia e o que foi bipado em cada um."""
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import nota_consumo as nc
    from ..providers.implementations.opme.utils import hoje_iso
    exigir_modulo(request, MODULO)
    data = data or hoje_iso()
    unidade = unidade_da_farmacia(request)
    lista = nc.prontuarios_com_uso(data, unidade, bool(pendentes))
    for at in lista:
        at["itens"] = nc.itens(at["id_atendimento"])
        # v18.8: lote a lote (a RM precisa do lote)
        lotes = {i["codigo"]: i["lotes"] for i in nc.itens_por_lote(at["id_atendimento"])}
        for i in at["itens"]:
            i["lotes_qtd"] = lotes.get(i["codigo_aghu"], [])
    return render(request, "farmacia/nota_consumo.html", _contexto_unidade(request) | {
        "data": data, "pendentes": bool(pendentes), "atendimentos": lista,
        "total_lancadas": sum(1 for a in lista if a["consumo_status"] == "lancada"),
        "total_rm": sum(1 for a in lista if a["rm_status"] == "lancada")})


def nota_consumo_marcar(request: Request, id_atendimento: str, acao: str = "", data: str = "", tipo: str = "consumo"):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import nota_consumo as nc
    usuario = exigir_modulo(request, MODULO)
    ok, msg = nc.marcar(id_atendimento, acao, usuario["username"], tipo if tipo in nc.DOCUMENTOS else "consumo")
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/farmacia/nota-consumo?data={data}" if data else "/farmacia/nota-consumo")


def nota_consumo_aghu(request: Request, id_atendimento: str):
    """Tela do robô (tela do AGHU dentro do TraceOPME) para a nota de consumo."""
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import aghu_remoto
    from ..providers.implementations.opme.services import nota_consumo as nc
    from ..providers.implementations.opme.utils import data_br
    import html as _html
    usuario = exigir_modulo(request, MODULO)
    at = nc.atendimento(id_atendimento)
    itens = [i for i in nc.itens(id_atendimento) if i["codigo_aghu"]] if at else []
    ativa = aghu_remoto.ativa_da_nota(f"consumo:{id_atendimento}")
    data = at.get("data_procedimento") if at else ""
    voltar = f"/farmacia/nota-consumo?data={data}" if data else "/farmacia/nota-consumo"
    rot = f"{at['prontuario']} · {at.get('paciente') or ''}" if at else ""
    return render(request, "almoxarifado/aghu_web.html", {
        "sessao": ativa.id if ativa and (ativa.usuario == usuario["username"] or usuario["papel"] == "admin") else "",
        "ocupada_por": ativa.nome if ativa and ativa.usuario != usuario["username"] else "",
        "robo": {
            "titulo": f"Nota de consumo no AGHU — {rot}", "rotulo": f"Pront. {at['prontuario']}" if at else "",
            "existe": bool(at), "voltar": voltar,
            "iniciar": f"/farmacia/nota-consumo/{id_atendimento}/aghu/iniciar",
            "ja_lancada": ("A nota de consumo deste paciente já está lançada no AGHU."
                           if at and at.get("aghu_consumo_status") == "lancada" else ""),
            "pode_iniciar": bool(itens),
            "passos": [f"Clique em <strong>Iniciar</strong>: a tela do AGHU abre ocupando a janela toda "
                       f"({len(itens)} material(is) para lançar).",
                       f"Faça o login, abra a <em>Nota de Consumo</em>, pesquise o prontuário <strong>{_html.escape(str(at['prontuario'])) if at else ''}</strong>"
                       f"{' de ' + data_br(data) if data else ''}, abra a cirurgia e clique em <em>Materiais Consumidos</em>.",
                       "Clique em <strong>Pronto, continuar</strong> (barra de cima): o robô inclui cada material com a quantidade.",
                       "No fim, confira a lista e clique em <strong>Gravar</strong> no AGHU."],
        },
    })


async def nota_consumo_aghu_iniciar(request: Request, id_atendimento: str):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import aghu_remoto
    usuario = exigir_modulo(request, MODULO)
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    corpo = corpo if isinstance(corpo, dict) else {}
    ok, msg, sid = aghu_remoto.iniciar_consumo(id_atendimento, usuario["username"], usuario.get("nome") or "",
                                               corpo.get("largura") or aghu_remoto.LARGURA,
                                               corpo.get("altura") or aghu_remoto.ALTURA)
    return JSONResponse({"ok": ok, "mensagem": msg, "sessao": sid})


async def nota_consumo_aghu_lancar(request: Request, id_atendimento: str):
    """v18.7: gera o link traceopme-aghu:// que a tela entrega ao robô deste computador."""
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import nota_consumo as nc
    usuario = exigir_modulo(request, MODULO)
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    tipo = str((corpo or {}).get("tipo") or "consumo")
    ok, msg, link = nc.iniciar_local(id_atendimento, usuario["username"], str((corpo or {}).get("servidor") or ""),
                                     tipo if tipo in nc.DOCUMENTOS else "consumo")
    return JSONResponse({"ok": ok, "mensagem": msg, "link": link})


def robo_instalador(request: Request):
    """Instalador do robô do AGHU (o mesmo da NF) para os computadores da farmácia."""
    from fastapi.responses import Response
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import aghu_robo
    exigir_modulo(request, MODULO)
    return Response(aghu_robo.instalador_zip(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="robo_nota_aghu.zip"'})


def saidas_outros(request: Request, de: str = "", ate: str = "", destino: str = "",
                  *, modulo: str = MODULO, base: str = "/farmacia"):
    """v18.14: saídas de OPME para outros procedimentos (farmácia ou almoxarifado)."""
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import saidas_outros as serv
    exigir_modulo(request, modulo)
    de, ate = serv.periodo_padrao(de, ate)
    origem = "almoxarifado" if modulo == "almoxarifado" else "farmacia"
    linhas = serv.listar(de, ate, destino, origem=origem)
    return render(request, "comum/saidas_outros.html", {
        "de": de, "ate": ate, "destino": destino, "linhas": linhas,
        "resumo": serv.resumo(linhas), "destinos": serv.DESTINOS,
        "base": base, "base_modulo": modulo,
        "operacao": "saida_outros_almox" if modulo == "almoxarifado" else "saida_outros",
        "total_itens": len([l for l in linhas if not l["desfeita"]]),
    })


def saida_outros_desfazer(request: Request, id_unidade: str, motivo: str = "",
                          *, modulo: str = MODULO, base: str = "/farmacia"):
    """v18.14: desfaz uma saída bipada por engano — o item volta ao estoque."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import saidas_outros as serv
    usuario = exigir_modulo(request, modulo)
    ok, msg = serv.desfazer(id_unidade, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"{base}/saidas-outros")
