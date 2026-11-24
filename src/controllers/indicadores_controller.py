"""Controller — Indicadores (TraceOPME).

Regras de tela do módulo, portadas de app/routers/indicadores.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/indicadores.py.
Original:
    Módulo de indicadores.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile
from fastapi.responses import Response

from ..providers.implementations.opme.indicadores import CATALOGO, GRUPOS
from ..providers.implementations.opme.services import indicadores as calc
from ..providers.implementations.opme.services import relatorios

MODULO = "indicadores"


def _local(calc_mod, unidade: str) -> dict:
    """v18.15: dados do seletor de unidade, iguais em todas as telas."""
    return {"unidade": unidade,
            "unidades": calc_mod.unidades_disponiveis(),
            "unidade_rotulo": calc_mod.rotulo_do_filtro(unidade)}


def _periodo(inicio: str, fim: str) -> tuple[str, str]:
    padrao_inicio, padrao_fim = calc.periodo_padrao(30)
    return (inicio or padrao_inicio), (fim or padrao_fim)


def hub(request: Request, inicio: str = "", fim: str = "", unidade: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio, fim = _periodo(inicio, fim)
    unidade = calc.chave_unidade(unidade)

    todos = calc.montar(inicio, fim, unidade=unidade)
    destaque = [i for i in todos if i["codigo"] in (
        "ciclo_total", "taxa_cancelamento", "procedimentos_cancelados", "procedimentos_criados",
        "taxa_utilizacao_dispensado", "pendentes_ciencia_farmacia", "taxa_selecao_manual", "materiais_nao_cadastrados",
        "taxa_uso_sem_dispensacao", "ciencia_uso_sem_dispensacao",
        "valor_consumido", "custo_medio_cirurgia",
        "itens_por_cirurgia", "itens_vencidos",
        "valor_vencido")]

    return render(request, "indicadores/hub.html", {
        "inicio": inicio, "fim": fim, **_local(calc, unidade),
        "destaque": destaque,
        "criticos": [i for i in todos if i["situacao"] == "vermelho"],
        "atencao": [i for i in todos if i["situacao"] == "amarelo"],
        "grupos": GRUPOS,
        "evolucao": calc.evolucao_mensal(12, unidade),
        "por_grupo": {chave: [i for i in todos if i["indicador"].grupo == chave]
                      for chave in GRUPOS},
    })


def fluxo(request: Request, inicio: str = "", fim: str = "", unidade: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio, fim = _periodo(inicio, fim)
    unidade = calc.chave_unidade(unidade)
    return render(request, "indicadores/fluxo.html", {
        "inicio": inicio, "fim": fim, "grupo": "fluxo", **_local(calc, unidade),
        "indicadores": calc.montar(inicio, fim, "fluxo", unidade),
        "etapas": calc.tempos_por_etapa(inicio, fim, unidade),
        "gargalos": calc.gargalos_abertos(unidade),
        "produtividade": calc.produtividade(inicio, fim, unidade),
        "cancelamentos": calc.cancelamentos(inicio, fim, unidade),
        "parados": relatorios.itens_parados(2),
    })


def desperdicio(request: Request, inicio: str = "", fim: str = "", unidade: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio, fim = _periodo(inicio, fim)
    unidade = calc.chave_unidade(unidade)
    return render(request, "indicadores/desperdicio.html", {
        "inicio": inicio, "fim": fim, "grupo": "desperdicio", **_local(calc, unidade),
        "indicadores": calc.montar(inicio, fim, "desperdicio", unidade),
        "especialidades": calc.aproveitamento_por_especialidade(inicio, fim, unidade),
        "devolvidos": calc.produtos_mais_devolvidos(inicio, fim, unidade=unidade),
        "vencimentos": calc.vencimentos_por_faixa(unidade),
        "baixas": calc.baixas_por_motivo(inicio, fim, unidade),
    })


def financeiro(request: Request, inicio: str = "", fim: str = "", unidade: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio, fim = _periodo(inicio, fim)
    unidade = calc.chave_unidade(unidade)
    return render(request, "indicadores/financeiro.html", {
        "inicio": inicio, "fim": fim, "grupo": "financeiro", **_local(calc, unidade),
        "indicadores": calc.montar(inicio, fim, "financeiro", unidade),
        "por_especialidade": calc.consumo_por("especialidade", inicio, fim, unidade=unidade),
        "por_sala": calc.consumo_por("sala", inicio, fim, unidade=unidade),
        "por_fornecedor": calc.consumo_por("fornecedor", inicio, fim, unidade=unidade),
        "por_tipo": calc.consumo_por("tipo_entrada", inicio, fim, unidade=unidade),
        "por_produto": calc.consumo_por("produto", inicio, fim, unidade=unidade),
        "cobertura": calc.cobertura_por_produto(inicio, fim, unidade=unidade),
        "evolucao": calc.evolucao_mensal(12, unidade),
    })


def qualidade(request: Request, inicio: str = "", fim: str = "", unidade: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio, fim = _periodo(inicio, fim)
    unidade = calc.chave_unidade(unidade)
    return render(request, "indicadores/qualidade.html", {
        "inicio": inicio, "fim": fim, "grupo": "qualidade", **_local(calc, unidade),
        "indicadores": calc.montar(inicio, fim, "qualidade", unidade),
        "fornecedores": calc.divergencias_por_fornecedor(inicio, fim, unidade),
        "fora_do_fluxo": calc.itens_sem_conferencia_sala(inicio, fim, unidade),
        "problemas_sala": calc.problemas_na_sala(inicio, fim, unidade),
    })


def exportar(request: Request, inicio: str = "", fim: str = "", unidade: str = ""):
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    inicio, fim = _periodo(inicio, fim)
    unidade = calc.chave_unidade(unidade)
    conteudo = relatorios.para_csv(calc.exportar(inicio, fim, unidade))
    sufixo = f"_{unidade.split()[0].lower()}" if unidade else ""
    return Response(
        content=conteudo.encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="opme_indicadores{sufixo}_{inicio}_{fim}.csv"'},
    )


# ---------------------------------------------------------
# Metas (somente administrador)
# ---------------------------------------------------------

def metas(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, "admin")
    configuracao = calc.metas_atuais()
    return render(request, "indicadores/metas.html", {
        "grupos": GRUPOS,
        "catalogo": CATALOGO,
        "config": configuracao,
        "por_grupo": {chave: [i for i in CATALOGO.values() if i.grupo == chave]
                      for chave in GRUPOS},
    })


def salvar_meta(request: Request, codigo: str, meta: str = (""),
                atencao: str = (""), acao: str = ("salvar")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, "admin")

    if acao == "restaurar":
        ok, mensagem = calc.restaurar_padrao(codigo)
    else:
        ok, mensagem = calc.salvar_meta(codigo, meta, atencao, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/indicadores/metas")
