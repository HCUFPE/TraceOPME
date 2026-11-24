"""Controller — Devoluções (TraceOPME).

Regras de tela do módulo, portadas de app/routers/devolucoes.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/devolucoes.py.
Original:
    v17 — confirmação das devoluções pela farmácia.
    
    A sala bipa o que voltou sem uso na tela "Devolver não utilizados". A
    confirmação é esta página: a farmácia confere a lista, desmarca o que não
    recebeu e confirma com a própria senha. Abre tanto a partir da tela da sala
    (farmácia junto, na porta) quanto de Farmácia → Devoluções a confirmar.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

from ..providers.implementations.opme.security import pode_acessar



def _exigir(request: Request) -> dict:
    from fastapi import HTTPException
    from ..helpers.web_helper import exigir_login
    usuario = exigir_login(request)
    if not (pode_acessar(usuario["papel"], "sala-procedimento")
            or pode_acessar(usuario["papel"], "farmacia")):
        raise HTTPException(status_code=303, headers={"Location": "/?sem_permissao=1"})
    return usuario


def do_atendimento(request: Request, id_atendimento: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import devolucoes
    from ..helpers.web_helper import redirecionar
    _exigir(request)
    dev = devolucoes.pendente_do_atendimento(id_atendimento)
    if dev and devolucoes.itens(dev["id_devolucao"], so_pendentes=True):
        return redirecionar(f"/devolucoes/{dev['id_devolucao']}")
    avisar(request, "Não há lista de não utilizados aguardando a farmácia neste atendimento.", "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")


def ficha(request: Request, id_devolucao: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import atendimentos, devolucoes, usuarios
    from ..helpers.web_helper import redirecionar
    usuario = _exigir(request)
    dev = devolucoes.buscar(id_devolucao)
    if not dev:
        return redirecionar("/")
    eh_farmacia = usuario["papel"] in ("farmacia", "admin")
    return render(request, "devolucoes/confirmar.html", {
        "dev": dev,
        # v18.2: o que foi para o paciente e o que aconteceu com cada item.
        "balanco": devolucoes.balanco(id_devolucao),
        "descricao": atendimentos.descrever(atendimentos.buscar(dev["id_atendimento"])),
        # A farmacêutica logada confirma com a própria senha; na tela da sala
        # (login da sala) a lista traz todas as pessoas da farmácia.
        "confirmadores": usuarios.confirmadores("farmacia", ""),
        "eu": usuario["username"] if eh_farmacia else "",
        "eh_farmacia": eh_farmacia,
        "voltar": ("/farmacia/devolucoes" if eh_farmacia else
                   f"/sala-procedimento/atendimento/{dev['id_atendimento']}"),
    })


def identificar(request: Request, id_devolucao: str, codigo: str = ""):
    """Conferência bipando: a tela pergunta qual linha o código lido atende."""
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import devolucoes
    _exigir(request)
    return JSONResponse(devolucoes.identificar_bip(id_devolucao, codigo))


async def confirmar(request: Request, id_devolucao: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import devolucoes
    from ..helpers.web_helper import redirecionar
    usuario = _exigir(request)
    form = await request.form()
    recebidos = {str(v) for v in form.getlist("recebido")}
    pendentes = devolucoes.itens(id_devolucao, so_pendentes=True)
    nao_recebidos = [i["id_item"] for i in pendentes if str(i["id_item"]) not in recebidos]
    # Conferência bipando: registra que a volta foi confirmada pelo bip.
    observacao = str(form.get("observacao") or "")
    bipados = set()
    if form.get("modo") == "bipando":
        bipados = {str(v) for v in form.getlist("bipado")} & recebidos
        observacao = (f"Conferido bipando: {len(bipados)} de {len(pendentes)} item(ns) bipado(s) na farmácia."
                      + (f" {observacao}" if observacao else ""))
    # v17 (out/2026): na Farmácia, a ciência é de quem está logado (sem senha).
    eh_farmacia = usuario["papel"] in ("farmacia", "admin")
    ok, mensagem = devolucoes.confirmar(
        id_devolucao=id_devolucao, operador=usuario["username"],
        usuario_farmacia=str(form.get("usuario_farmacia") or ""),
        senha=str(form.get("senha") or ""), nao_recebidos=nao_recebidos,
        observacao=observacao, bipados=bipados,
        responsavel=usuario if eh_farmacia else None)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    dev = devolucoes.buscar(id_devolucao)
    if ok and eh_farmacia and dev:
        return redirecionar(f"/farmacia/procedimento/{dev['id_atendimento']}")
    return redirecionar(f"/devolucoes/{id_devolucao}")


async def incluir_sem_destino(request: Request, id_devolucao: str):
    """v18.22: a farmácia recebeu de volta um item que ficou "sem destino"."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import devolucoes
    from ..helpers.web_helper import redirecionar
    usuario = _exigir(request)
    form = await request.form()
    ok, mensagem = devolucoes.incluir_sem_destino(
        id_devolucao, str(form.get("id_unidade") or ""), usuario)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/devolucoes/{id_devolucao}")


async def remover(request: Request, id_item: int):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import devolucoes
    from ..helpers.web_helper import redirecionar
    usuario = _exigir(request)
    form = await request.form()
    ok, mensagem, id_atendimento = devolucoes.remover_item(
        id_item, usuario["username"], str(form.get("motivo") or ""))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    destino = str(form.get("voltar") or "")
    if not destino.startswith("/"):
        destino = f"/sala-procedimento/atendimento/{id_atendimento}" if id_atendimento else "/"
    return redirecionar(destino)
