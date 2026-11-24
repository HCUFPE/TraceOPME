"""Controller — Painel (TraceOPME).

Regras de tela do módulo, portadas de app/routers/painel.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/painel.py.
Original:
    Painel de situação — a primeira tela de todo mundo.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

from ..providers.implementations.opme.security import pode_acessar
from ..providers.implementations.opme.services import alertas, relatorios



def inicio(request: Request, sem_permissao: int = 0):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_login

    usuario = exigir_login(request)
    dados = relatorios.painel()

    # Mostra apenas as pendências que o usuário pode resolver, mas sempre
    # exibe o panorama geral do estoque.
    dados["pendencias"] = [
        p for p in dados["pendencias"] if pode_acessar(usuario["papel"], p["modulo"])
    ]
    # Alertas de devolução (farmácia→recebimento, bloco→farmácia): só os do
    # módulo que este usuário atende.
    dados["alertas"] = [
        a for a in alertas.listar_abertos() if pode_acessar(usuario["papel"], a["modulo_destino"])
    ]
    # Framework: a tela (Vue) recebe pronto o que o template chamava como
    # `itens_alerta(a)` — as unidades de cada alerta, para abrir item a item.
    for a in dados["alertas"]:
        a["itens"] = alertas.itens(a)
    return render(request, "painel.html", {
        "painel": dados,
        "sem_permissao": bool(sem_permissao),
    })


def resolver_alerta(request: Request, id_alerta: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_login, redirecionar

    usuario = exigir_login(request)
    alerta = None
    for a in alertas.listar_abertos():
        if a["id_alerta"] == id_alerta:
            alerta = a
            break
    if alerta and not pode_acessar(usuario["papel"], alerta["modulo_destino"]):
        return redirecionar("/?sem_permissao=1")

    ok, mensagem = alertas.resolver(id_alerta, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    destino = request.headers.get("referer") or "/"
    return redirecionar(destino)
