"""Controller — Central de monitoramento das salas (v18.1)."""

from fastapi.responses import JSONResponse

from ..helpers.web_helper import Requisicao as Request

MODULO = "monitoramento"


def _unidade_padrao(request: Request, unidade: str) -> str:
    """Sem unidade escolhida na tela, usa a da farmácia/sala em que a pessoa trabalha."""
    if unidade:
        return "" if unidade == "todas" else unidade
    from ..providers.implementations.opme.config import UNIDADES_ATIVAS
    for chave in ("unidade_farmacia", "unidade_sala"):
        v = request.session.get(chave, "")
        if v in UNIDADES_ATIVAS:
            return v
    return ""


def central(request: Request, unidade: str = "", data: str = ""):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import monitoramento
    exigir_modulo(request, MODULO)
    return render(request, "monitoramento/central.html", monitoramento.painel(_unidade_padrao(request, unidade), data))


def dados(request: Request, unidade: str = "", data: str = ""):
    """O mesmo painel em JSON, para a tela se atualizar sozinha."""
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import monitoramento
    exigir_modulo(request, MODULO)
    return JSONResponse(monitoramento.painel(_unidade_padrao(request, unidade), data))


def procedimento(request: Request, id_atendimento: str):
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import monitoramento
    exigir_modulo(request, MODULO)
    return JSONResponse({"ok": True, "eventos": monitoramento.linha_do_tempo(id_atendimento)})
