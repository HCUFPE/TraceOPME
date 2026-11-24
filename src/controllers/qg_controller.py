"""Controller — QG da enfermagem: chamados das salas (maqueiro / limpeza) — v18.3."""

from fastapi.responses import JSONResponse

from ..helpers.web_helper import Requisicao as Request

MODULO = "qg"


def painel(request: Request, unidade: str = ""):
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import chamados_sala as chamados
    exigir_modulo(request, MODULO)
    return render(request, "qg/painel.html", chamados.painel_qg(unidade))


def dados(request: Request, unidade: str = ""):
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import chamados_sala as chamados
    exigir_modulo(request, MODULO)
    return JSONResponse(chamados.painel_qg(unidade))


async def acao(request: Request, id_chamado: str, acao: str):
    """direcionar / atender / cancelar (JSON — a tela não recarrega)."""
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import chamados_sala as chamados
    usuario = exigir_modulo(request, MODULO)
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    if acao == "direcionar":
        ok, msg = chamados.direcionar(id_chamado, str(corpo.get("responsavel") or ""), usuario["username"])
    elif acao == "atender":
        ok, msg = chamados.atender(id_chamado, usuario["username"])
    elif acao == "cancelar":
        ok, msg = chamados.cancelar(id_chamado, usuario["username"], str(corpo.get("motivo") or ""))
    else:
        ok, msg = False, "Ação desconhecida."
    return JSONResponse({"ok": ok, "mensagem": msg})
