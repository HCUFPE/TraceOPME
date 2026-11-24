"""Controller — Dispensações (TraceOPME).

Regras de tela do módulo, portadas de app/routers/dispensacoes.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/dispensacoes.py.
Original:
    v17 — confirmação da dispensação pela sala (com o usuário logado, sem bipar).
    
    A farmácia bipa o OPME do paciente em "Dispensar para a sala". O recebimento é
    esta página: a sala confere e confirma com o próprio usuário (v18.4.3). Abre
    pela tela da farmácia (entrega na hora) ou pela ficha do atendimento na sala.
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
    from ..providers.implementations.opme.services import dispensacoes
    from ..helpers.web_helper import redirecionar
    usuario = _exigir(request)
    disp = dispensacoes.pendente_do_atendimento(id_atendimento)
    if disp and dispensacoes.itens(disp["id_dispensacao"], so_pendentes=True):
        return redirecionar(f"/dispensacoes/{disp['id_dispensacao']}")
    avisar(request, "Não há dispensação aguardando a ciência da sala neste atendimento.", "erro")
    if pode_acessar(usuario["papel"], "farmacia"):
        return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")


def do_atendimento_acao(request: Request, id_atendimento: str, acao: str):
    """v17 — "Finalizar dispensa" e "Baixar PDF" a partir da tela de bipagem."""
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import dispensacoes
    from ..helpers.web_helper import redirecionar
    _exigir(request)
    disp = dispensacoes.ultima_do_atendimento(id_atendimento)
    if not disp or not dispensacoes.itens(disp["id_dispensacao"]) or acao not in ("finalizada", "pdf"):
        avisar(request, "Nenhum material foi bipado para este paciente ainda.", "erro")
        return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}")
    return redirecionar(f"/dispensacoes/{disp['id_dispensacao']}/{acao}")


def ficha(request: Request, id_dispensacao: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import atendimentos, dispensacoes
    from ..helpers.web_helper import redirecionar
    usuario = _exigir(request)
    disp = dispensacoes.buscar(id_dispensacao)
    if not disp:
        return redirecionar("/")
    da_sala = usuario["papel"] in dispensacoes.PAPEIS_QUE_RECEBEM
    recebedores = db_recebedores()
    return render(request, "dispensacoes/confirmar.html", {
        "disp": disp,
        "descricao": atendimentos.descrever(atendimentos.buscar(disp["id_atendimento"])),
        "recebedores": recebedores,
        "eu": usuario["username"] if da_sala else "",
        "pode_dar_ciencia": da_sala, "nome_logado": usuario.get("nome") or usuario["username"],
        # v18.3: a sala abre a sala ANTES de dar ciência do material.
        "sala_aberta": bool((atendimentos.buscar(disp["id_atendimento"]) or {}).get("sala_aberta_em")),
        **_cancelamento_pela_sala(usuario, disp),
        "voltar": (f"/sala-procedimento/atendimento/{disp['id_atendimento']}" if da_sala
                   else f"/bipagem/dispensar_sala?atendimento={disp['id_atendimento']}"),
    })


def _cancelamento_pela_sala(usuario: dict, disp: dict) -> dict:
    """No lugar de dar ciência, a sala pode cancelar o procedimento e devolver
    tudo à farmácia. Só aparece para quem é da sala e se nada foi usado."""
    from ..providers.implementations.opme.config import MOTIVOS_CANCELAMENTO
    from ..providers.implementations.opme.security import pode_acessar
    from ..providers.implementations.opme.services import atendimentos
    if disp["status"] != "pendente" or not pode_acessar(usuario["papel"], "sala-procedimento"):
        return {}
    at = atendimentos.buscar(disp["id_atendimento"])
    if not at or at["status"] != "aberto" or at.get("uso_finalizado_em"):
        return {}
    r = atendimentos.resumo(disp["id_atendimento"])
    if r["utilizados"]:
        return {}
    return {"cancelar_sala": r["transito_sala"] + r["na_sala"],
            "motivos_cancelamento": MOTIVOS_CANCELAMENTO}


def db_recebedores() -> list[dict]:
    from ..providers.implementations.opme import db
    return db.consultar(
        """SELECT username, nome, setor FROM usuarios
           WHERE papel IN ('sala-procedimento', 'supervisao') AND status = 'ativo' ORDER BY nome""")


def pdf_dispensacao(request: Request, id_dispensacao: str):
    """v17 — lista do material dispensado, em PDF, para acompanhar o material à sala."""
    from fastapi.responses import Response
    from ..providers.implementations.opme.services import dispensacoes
    from ..helpers.web_helper import redirecionar
    _exigir(request)
    disp = dispensacoes.buscar(id_dispensacao)
    conteudo = dispensacoes.pdf(id_dispensacao) if disp else None
    if conteudo is None:
        return redirecionar("/")
    nome = f"dispensacao_{disp.get('prontuario') or ''}_{id_dispensacao}.pdf".replace("/", "-")
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def finalizada(request: Request, id_dispensacao: str):
    """v17 — "Finalizar dispensa": resumo do que saiu para a sala, com o PDF."""
    from ..helpers.web_helper import avisar, render
    from ..providers.implementations.opme.services import atendimentos, dispensacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, "farmacia")
    disp = dispensacoes.buscar(id_dispensacao)
    if not disp:
        return redirecionar("/farmacia/atendimentos")
    if not disp["itens"]:
        avisar(request, "Nenhum material foi bipado nesta dispensação.", "erro")
        return redirecionar(f"/bipagem/dispensar_sala?atendimento={disp['id_atendimento']}")
    return render(request, "dispensacoes/confirmar.html", {
        "disp": disp,
        "descricao": atendimentos.descrever(atendimentos.buscar(disp["id_atendimento"])),
        "recebedores": [], "eu": "", "finalizada": True,
        "voltar": f"/bipagem/dispensar_sala?atendimento={disp['id_atendimento']}",
    })


async def confirmar(request: Request, id_dispensacao: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import dispensacoes
    from ..helpers.web_helper import redirecionar
    logado = _exigir(request)
    form = await request.form()
    modo = str(form.get("modo") or "")
    if modo == "bipando":
        recebidos = set(form.getlist("bipado"))
    elif modo == "lista":
        # Caixa vem como uma linha só: "12,13,14" = todos os itens dela.
        recebidos = {x for v in form.getlist("recebido") for x in str(v).split(",") if x}
    else:
        recebidos = None
    disp0 = dispensacoes.buscar(id_dispensacao)
    if disp0 and logado["papel"] in dispensacoes.PAPEIS_QUE_RECEBEM:
        from ..providers.implementations.opme.services import atendimentos
        at0 = atendimentos.buscar(disp0["id_atendimento"]) or {}
        if not at0.get("sala_aberta_em"):
            avisar(request, "Abra a sala antes de dar ciência do material (botão “Abrir sala”).", "erro")
            return redirecionar(f"/dispensacoes/{id_dispensacao}")
    ok, mensagem = dispensacoes.confirmar(
        id_dispensacao=id_dispensacao, recebidos=recebidos, modo=modo, logado=logado)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    if ok:
        # v17: confirmou o recebimento → já vai para o registro de uso deste paciente.
        usuario = _exigir(request)
        disp = dispensacoes.buscar(id_dispensacao)
        if disp and pode_acessar(usuario["papel"], "sala-procedimento"):
            return redirecionar(f"/bipagem/registrar_uso?atendimento={disp['id_atendimento']}")
    return redirecionar(f"/dispensacoes/{id_dispensacao}")


def identificar(request: Request, id_dispensacao: str, codigo: str = ""):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import dispensacoes
    _exigir(request)
    return JSONResponse(dispensacoes.identificar(id_dispensacao, codigo))


async def remover(request: Request, id_item: int):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import dispensacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, "farmacia")
    form = await request.form()
    ok, mensagem, id_atendimento = dispensacoes.remover_item(id_item, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/bipagem/dispensar_sala?atendimento={id_atendimento}" if id_atendimento
                        else "/farmacia/dispensacoes")
