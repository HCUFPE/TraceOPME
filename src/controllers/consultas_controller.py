"""Controller — Consultas (TraceOPME).

Regras de tela do módulo, portadas de app/routers/consultas.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/consultas.py.
Original:
    Consultas, rastreabilidade e exportações.
"""

from datetime import date, timedelta

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile
from fastapi.responses import Response

from ..providers.implementations.opme.config import todas_as_salas
from ..providers.implementations.opme.domain import TRANSITO_FARMACIA, TRANSITO_RETORNO, TRANSITO_SALA, UTILIZADO
from ..providers.implementations.opme.services import atendimentos, caixas, documentos, estoque, fluxo, recall, relatorios
from ..providers.implementations.opme.utils import hoje_iso, texto

MODULO = "consultas"


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio = (date.today() - timedelta(days=30)).isoformat()
    return render(request, "consultas/hub.html", {
        "indicadores": relatorios.indicadores_periodo(inicio, hoje_iso()),
        "top": relatorios.top_produtos(inicio, hoje_iso()),
        "inicio": inicio, "fim": hoje_iso(),
    })


def itens(request: Request, busca: str = "", status: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)

    if status == "transito":
        linhas = []
        for st in (TRANSITO_FARMACIA, TRANSITO_SALA, TRANSITO_RETORNO, "transito_almoxarifado"):
            linhas += estoque.buscar_unidades(busca, st)
    else:
        linhas = estoque.buscar_unidades(busca, status or "ativos")
    for l in linhas:
        l["local"] = estoque.local_da_unidade(l)

    return render(request, "consultas/itens.html", {
        "itens": linhas, "busca": busca, "status": status,
        "lote_nao_encontrado": _lote_nao_encontrado(busca, linhas),
        "opcoes": relatorios.opcoes_status(),
    })


def _lote_nao_encontrado(termo: str, linhas: list[dict]) -> str:
    """v18.11: etiqueta GS1 com lote que NÃO existe no cadastro — avisa em vez de
    mostrar, sem explicação, as unidades de outros lotes do mesmo produto.

    v18.17: a comparação vale nos dois sentidos e considera a segunda leitura do
    lote. Sem o separador FNC1, o lote lido engole a validade colada
    (`SP1124082036` + `17270904` chega como `SP112408203617270904`): o cadastro
    não começa pelo lido, mas o lido começa pelo cadastro — e a tela dizia "não
    encontrado" mostrando logo abaixo exatamente as unidades certas.
    """
    from ..providers.implementations.opme import busca, gs1
    et = busca.interpretar(termo) if texto(termo) else None
    if not et or not et.get("lote"):
        return ""
    lidos = [gs1.lote_normalizado(et["lote"])]
    if et.get("lote_curto"):
        lidos.append(gs1.lote_normalizado(et["lote_curto"]))
    for linha in linhas:
        cadastrado = gs1.lote_normalizado(linha.get("nLote"))
        if cadastrado and any(lido and (lido.startswith(cadastrado) or cadastrado.startswith(lido))
                              for lido in lidos):
            return ""
    return et["lote"]


def item(request: Request, id_unidade: str):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)

    unidade = fluxo.buscar_unidade(id_unidade)
    if not unidade:
        return redirecionar("/consultas/itens")
    # As duas descrições convivem: a do fornecedor (da NF, `xProd`) e a do
    # hospital. Material que entrou antes da planilha ser carregada não tem a do
    # hospital gravada — nesse caso ela é buscada pelo código AGHU na hora.
    from ..providers.implementations.opme.services import materiais
    descritivo_hc = (unidade.get("descritivo_hospital")
                     or materiais.descritivo_hospital(unidade.get("codigo_aghu")))
    return render(request, "consultas/item.html", {
        "item": unidade,
        "descritivo_hc": descritivo_hc,
        "codigo_master": materiais.codigo_master(unidade.get("codigo_aghu")),
        "historico": fluxo.historico(id_unidade),
        "alertas": fluxo.alertas_do_item(unidade),
        # Quando o item está numa caixa, "onde ele está" é a caixa — sem isso a
        # ficha diz "em trânsito para a farmácia" e não diz dentro de quê.
        "caixa": caixas.caixa_da_unidade(id_unidade),
        "caixas_anteriores": caixas.caixas_por_onde_passou(id_unidade),
    })


def prontuario(request: Request, numero: str = "", formato: str = "", data: str | None = None,
               inicio: str = "", fim: str = ""):
    """Ficha do paciente. Em `formato=txt` ou `pdf`, sai o descritivo cirúrgico.

    `data` recorta por procedimento. Sem ela (primeira consulta), abre no
    procedimento mais recente — é a cirurgia que está sendo documentada.
    `data=todas` mostra o histórico completo do paciente.
    """
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)

    datas = relatorios.datas_do_prontuario(numero) if texto(numero) else []
    if data is None:
        data = datas[0]["data"] if datas else ""
    recorte = "" if data == "todas" else data

    if texto(numero) and formato in ("txt", "pdf"):
        conteudo = relatorios.descritivo_prontuario(numero, recorte)
        nome = f"opme_prontuario_{texto(numero)}" + (f"_{recorte}" if recorte else "")
        if formato == "txt":
            return Response(
                content=conteudo.encode("utf-8-sig"),
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{nome}.txt"'},
            )
        return Response(
            content=documentos.pdf_de_texto(conteudo.splitlines()),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{nome}.pdf"'},
        )

    # v18: sem prontuário, lista quem teve material registrado no dia/período.
    from ..providers.implementations.opme.utils import hoje_iso
    if not texto(numero):
        inicio = texto(inicio) or hoje_iso()
        fim = texto(fim) or inicio
    periodo = relatorios.atendimentos_com_uso(inicio, fim) if not texto(numero) else []
    return render(request, "consultas/prontuario.html", {
        "inicio": inicio, "fim": fim, "periodo": periodo,
        "numero": numero,
        "datas": datas,
        "data": data or "todas",
        "linhas": relatorios.rastrear_por_prontuario(numero, recorte) if texto(numero) else [],
        "devolucoes": relatorios.devolucoes_por_prontuario(numero, recorte) if texto(numero) else [],
        "resumo": relatorios.resumo_prontuario(numero, recorte) if texto(numero) else [],
        "descritivo": relatorios.descritivo_prontuario(numero, recorte) if texto(numero) else "",
    })


def classificacao(request: Request, inicio: str = "", fim: str = "", tipo_entrada: str = "",
                  fornecedor: str = "", base: str = "entrada", detalhado: int = 1,
                  exportar: int = 0):
    """Material por classificação (consignado, aquisição própria…) em um período.

    Duas leituras dos mesmos filtros: o resumo agrupa por produto e serve à
    prestação de contas; o detalhado abre uma linha por material, com paciente,
    lote, validade e série — é o que se manda ao fornecedor para ele emitir a
    nota do consignado. A tela abre no detalhado porque é esse o uso do dia a
    dia; o resumo fica a um clique.
    """
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)

    inicio = inicio or (date.today() - timedelta(days=30)).isoformat()
    fim = fim or hoje_iso()
    somente_utilizados = base == "uso"

    cortada = False
    if detalhado:
        linhas, cortada = relatorios.detalhe_por_classificacao(
            inicio, fim, tipo_entrada, fornecedor, somente_utilizados)
        totais = []
    else:
        linhas = relatorios.por_classificacao(inicio, fim, tipo_entrada, fornecedor,
                                              somente_utilizados)
        totais = relatorios.totais_por_classificacao(linhas)

    if exportar:
        nome = "detalhe" if detalhado else "classificacao"
        return Response(
            content=relatorios.para_csv(linhas).encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition":
                     f'attachment; filename="opme_{nome}_{inicio}_{fim}.csv"'},
        )

    return render(request, "consultas/classificacao.html", {
        "linhas": linhas, "totais": totais,
        "inicio": inicio, "fim": fim, "tipo_entrada": tipo_entrada,
        "fornecedor": fornecedor, "base": base,
        "detalhado": bool(detalhado), "cortada": cortada,
        "somente_utilizados": somente_utilizados,
        "limite_detalhe": relatorios.LIMITE_DETALHE,
        "tipos": estoque.TIPOS_ENTRADA,
    })


def lote(request: Request, termo: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "consultas/lote.html", {
        "termo": termo,
        "linhas": relatorios.rastrear_por_lote(termo) if texto(termo) else [],
        "bloqueios": recall.listar(somente_ativos=True),
    })


# ---------------------------------------------------------
# Recall: bloqueio de lote
# ---------------------------------------------------------

def lista_recall(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "consultas/recall.html", {"bloqueios": recall.listar()})


async def criar_recall(request: Request):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = recall.bloquear(dict(await request.form()), usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/consultas/recall")


def detalhe_recall(request: Request, id_bloqueio: str):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    bloqueio = recall.buscar(id_bloqueio)
    if not bloqueio:
        return redirecionar("/consultas/recall")
    unidades = recall.unidades_do_lote(bloqueio["nLote"], bloqueio["codigo_aghu"] or "")
    return render(request, "consultas/recall_detalhe.html", {
        "bloqueio": bloqueio,
        "em_circulacao": [u for u in unidades if u["status"] != UTILIZADO],
        "implantadas": [u for u in unidades if u["status"] == UTILIZADO],
    })


def liberar_recall(request: Request, id_bloqueio: str, motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = recall.liberar(id_bloqueio, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/consultas/recall/{id_bloqueio}")


def utilizados(request: Request, inicio: str = "", fim: str = "", prontuario: str = "",
               sala: str = "", especialidade: str = "", produto: str = "", exportar: int = 0):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)

    inicio = inicio or (date.today() - timedelta(days=30)).isoformat()
    fim = fim or hoje_iso()
    filtros = {"prontuario": prontuario, "sala": sala,
               "especialidade": especialidade, "produto": produto}
    linhas = relatorios.itens_utilizados(inicio, fim, filtros)

    if exportar:
        return Response(
            content=relatorios.para_csv(linhas).encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="opme_utilizados_{inicio}_{fim}.csv"'},
        )

    return render(request, "consultas/utilizados.html", {
        "linhas": linhas, "inicio": inicio, "fim": fim, "filtros": filtros,
        "salas": todas_as_salas(), "especialidades": atendimentos.especialidades(),
    })


def dispensas(request: Request, inicio: str = "", fim: str = "", tipo: str = "",
              farmacia: str = "", busca: str = "", exportar: str = ""):
    """Relatório de todas as movimentações de dispensa no período:
    almoxarifado → farmácia e farmácia → sala."""
    from ..providers.implementations.opme.config import FARMACIAS
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import rel_dispensas
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio = inicio or date.today().replace(day=1).isoformat()
    fim = fim or hoje_iso()
    linhas = rel_dispensas.movimentacoes(inicio, fim, tipo, farmacia, busca)
    filtros_txt = " · ".join(x for x in (
        rel_dispensas.TIPOS.get(tipo, "Todas") if tipo else "Todas as movimentações",
        FARMACIAS.get(farmacia, "Todas as farmácias"), f"busca: {busca}" if busca else "") if x)
    nome = f"opme_dispensas_{inicio}_{fim}"
    if exportar == "csv":
        return Response(
            content=relatorios.para_csv(rel_dispensas.para_exportar(linhas)).encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})
    if exportar == "pdf":
        return Response(content=rel_dispensas.pdf(linhas, inicio, fim, filtros_txt), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})
    return render(request, "consultas/dispensas.html", {
        "linhas": linhas, "resumo": rel_dispensas.resumo(linhas), "inicio": inicio, "fim": fim,
        "tipo": tipo, "farmacia": farmacia, "busca": busca, "tipos": rel_dispensas.TIPOS,
        "farmacias": FARMACIAS, "filtros_txt": filtros_txt,
    })


def validades(request: Request, exportar: int = 0):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    linhas = relatorios.validades_criticas(365)
    if exportar:
        return Response(
            content=relatorios.para_csv(linhas).encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="opme_validades.csv"'},
        )
    return render(request, "consultas/validades.html", {"linhas": linhas})


def eventos(request: Request, inicio: str = "", fim: str = "", unidade: str = "", sala: str = "",
            prontuario: str = "", tipo: str = "", usuario: str = "", formato: str = ""):
    """v17 — histórico de movimentações com filtros (antes: só os últimos 200)."""
    from ..providers.implementations.opme.config import UNIDADES_ATIVAS
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    filtrou = any(texto(v) for v in (inicio, fim, unidade, sala, prontuario, tipo, usuario))
    if not filtrou:
        inicio = (date.today() - timedelta(days=30)).isoformat()
        fim = hoje_iso()
    linhas = relatorios.movimentacoes(inicio=inicio, fim=fim, unidade=unidade, sala=sala,
                                      prontuario=prontuario, tipo=tipo, usuario=usuario,
                                      agrupar_caixas=(formato != "csv"))
    if formato == "csv":
        nome = f"movimentacoes_{inicio or 'inicio'}_{fim or 'hoje'}.csv"
        return Response(
            content=relatorios.movimentacoes_para_csv(linhas).encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    return render(request, "consultas/eventos.html", {
        "eventos": linhas[:1000], "total": len(linhas),
        "inicio": inicio, "fim": fim, "unidade": unidade, "sala": sala,
        "prontuario": prontuario, "tipo": tipo, "usuario_filtro": usuario,
        "tipos": relatorios.TIPOS_MOVIMENTO, "unidades": UNIDADES_ATIVAS,
        "query": str(request.url.query),
    })



def caixa_no_momento(request: Request, id_caixa: str, evento: int = 0):
    """v17 — situação de uma caixa de consignado no momento de um movimento
    (ex.: a devolução), e a situação de agora."""
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas_consignado
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    dados = caixas_consignado.situacao_no_momento(id_caixa, evento)
    if not dados:
        return redirecionar("/consultas/eventos")
    return render(request, "consultas/caixa.html", dados)
