"""Controller — Consignados (TraceOPME).

Regras de tela do módulo, portadas de app/routers/consignados.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/consignados.py.
Original:
    Módulo Consignados — saldo de empenho para materiais consignados.
    
    Depois que um material consignado é usado no paciente, o uso precisa ser
    vinculado a um empenho antes de o fornecedor poder cobrar a nota. Este módulo
    controla o saldo (quantas unidades ainda cabem em cada empenho) e recusa o
    vínculo quando o saldo acabar — como um limite de cartão de crédito.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

from ..providers.implementations.opme.services import alertas, empenhos

MODULO = "consignados"


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "consignados/hub.html", {
        "pendentes": empenhos.contar_pendentes_de_vinculo(),
        "ativos": empenhos.listar(status="ativo"),
        "alertas": alertas.abertos_do_modulo(MODULO),
    })


def pendentes(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    itens = empenhos.itens_pendentes_de_vinculo()
    for item in itens:
        item["candidatos"] = empenhos.disponiveis(fornecedor=item.get("fornecedor"))
    return render(request, "consignados/pendentes.html", {"itens": itens})


def vincular(request: Request, id_unidade: str = "", id_empenho: str = "",
            observacao: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = empenhos.vincular(id_unidade, id_empenho, usuario["username"], observacao)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/consignados/pendentes")


def lista_empenhos(request: Request, fornecedor: str = "", status: str = "", termo: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "consignados/empenhos.html", {
        "empenhos": empenhos.listar(fornecedor=fornecedor, status=status, termo=termo),
        "fornecedor": fornecedor, "status": status, "termo": termo,
    })


def novo_empenho(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return render(request, "consignados/empenho_novo.html", {})


async def criar_empenho(request: Request):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    formulario = dict(form)
    # nov/2026: linhas "código consignado | AGHU" da tabela do formulário.
    formulario["pares"] = list(zip(form.getlist("consignado"), form.getlist("aghu")))
    ok, resultado = empenhos.cadastrar(formulario, usuario["username"])
    if not ok:
        avisar(request, resultado, "erro")
        return redirecionar("/consignados/empenhos/novo")
    avisar(request, "Empenho cadastrado.", "sucesso")
    return redirecionar(f"/consignados/empenhos/{resultado}")


async def importar_empenhos(request: Request):
    """v17 — cadastra empenhos a partir de uma planilha (.xlsx ou .csv)."""
    from ..helpers.web_helper import avisar, render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    formulario = await request.form()
    arquivo = formulario.get("arquivo")
    if not arquivo or not getattr(arquivo, "filename", ""):
        avisar(request, "Escolha a planilha.", "erro")
        return redirecionar("/consignados/empenhos/novo")
    conteudo = await arquivo.read()
    ok, mensagem, resultado = empenhos.importar_planilha(conteudo, arquivo.filename, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok and not resultado.get("erros") else "erro")
    if not ok:
        return redirecionar("/consignados/empenhos/novo")
    return render(request, "consignados/empenho_novo.html", {"resultado_importacao": resultado})


def pdf_empenho(request: Request, id_empenho: str, inicio: str = "", fim: str = ""):
    """v17 — materiais vinculados ao empenho, em PDF, no período escolhido."""
    from fastapi.responses import Response
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    conteudo = empenhos.pdf_vinculos(id_empenho, inicio, fim)
    if conteudo is None:
        return redirecionar("/consignados/empenhos")
    nome = f"empenho_{id_empenho}_{inicio or 'inicio'}_{fim or 'hoje'}.pdf".replace("/", "-")
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def detalhe_empenho(request: Request, id_empenho: str, inicio: str = "", fim: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    empenho = empenhos.buscar(id_empenho)
    if not empenho:
        return redirecionar("/consignados/empenhos")
    return render(request, "consignados/empenho.html", {
        "empenho": empenho,
        "vinculos": empenhos.vinculos_do_empenho(id_empenho, inicio=inicio, fim=fim),
        "inicio": inicio, "fim": fim,
    })


def encerrar_empenho(request: Request, id_empenho: str, motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = empenhos.encerrar(id_empenho, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/consignados/empenhos/{id_empenho}")


def cancelar_vinculo(request: Request, id_vinculo: str, motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    vinculo = empenhos.buscar_vinculo(id_vinculo)
    ok, mensagem = empenhos.cancelar_vinculo(id_vinculo, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    destino = f"/consignados/empenhos/{vinculo['id_empenho']}" if vinculo else "/consignados/empenhos"
    return redirecionar(destino)


# ---------------------------------------------------------
# nov/2026 — associação código consignado ↔ AGHU
# ---------------------------------------------------------

def associacoes(request: Request, termo: str = "", editar: str = ""):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import consignado_aghu
    exigir_modulo(request, MODULO)
    return render(request, "consignados/associacoes.html", {
        "associacoes": consignado_aghu.listar(termo), "termo": termo,
        "editando": consignado_aghu.buscar(editar) if editar else None})


def associacao_salvar(request: Request, codigo_consignado: str = "", codigo_aghu: str = "",
                      fornecedor: str = "", descricao: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import consignado_aghu
    usuario = exigir_modulo(request, MODULO)
    ok, msg = consignado_aghu.salvar(codigo_consignado, codigo_aghu, usuario["username"], fornecedor, descricao)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/consignados/associacoes")


def associacao_excluir(request: Request, codigo_consignado: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import consignado_aghu
    usuario = exigir_modulo(request, MODULO)
    ok, msg = consignado_aghu.excluir(codigo_consignado, usuario["username"])
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/consignados/associacoes")


async def associacoes_importar(request: Request):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import consignado_aghu
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    arquivo = form.get("arquivo")
    if not arquivo or not getattr(arquivo, "filename", ""):
        avisar(request, "Escolha a planilha.", "erro")
        return redirecionar("/consignados/associacoes")
    ok, msg, resultado = consignado_aghu.importar_planilha(await arquivo.read(), arquivo.filename, usuario["username"])
    if resultado.get("erros"):
        msg += " " + "; ".join(f"linha {e['linha']}: {e['mensagem']}" for e in resultado["erros"][:5])
    avisar(request, msg, "sucesso" if ok and not resultado.get("erros") else "erro")
    return redirecionar("/consignados/associacoes")


def associacao_consultar(request: Request, codigo: str = ""):
    """JSON para o formulário do empenho: o AGHU associado ao código consignado."""
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import consignado_aghu
    exigir_modulo(request, MODULO)
    linha = consignado_aghu.buscar(codigo)
    if not linha:
        return JSONResponse({"ok": False, "codigo": consignado_aghu.normalizar(codigo)})
    return JSONResponse({"ok": True, "codigo": linha["codigo_consignado"], "codigo_aghu": linha["codigo_aghu"],
                         "descricao": linha["descritivo_hospital"] or linha["descricao"] or "",
                         "fornecedor": linha["fornecedor"] or ""})
