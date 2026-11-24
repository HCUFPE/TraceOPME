"""Controller — Inventário (TraceOPME).

Regras de tela do módulo, portadas de app/routers/inventario.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/inventario.py.
Original:
    Módulo Inventário — contagem periódica do estoque, com relatório de pendências.
    
    A contagem é uma bipagem contínua, como as outras telas do sistema: escolhe-se o
    local, bipa-se material atrás de material, e no fim sai o relatório do que não
    fecha. O que muda em relação ao fluxo é que aqui nada se move — o inventário só
    compara e relata. Ver `services/inventario` para o porquê.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile
from fastapi.responses import JSONResponse, Response

from ..providers.implementations.opme.services import inventario, relatorios

MODULO = "inventario"


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, farmacia_atual
    usuario = exigir_modulo(request, MODULO)
    # Quem trabalha na farmácia conta a farmácia em que está: a tela já vem com
    # o local certo escolhido, para ninguém abrir contagem no estoque errado.
    from ..providers.implementations.opme.config import FARMACIAS
    local_sugerido = "almoxarifado"
    if usuario.get("papel") == "farmacia":
        local_sugerido = farmacia_atual(request)
    from ..providers.implementations.opme.services import relatorios
    return render(request, "inventario/hub.html", {
        "esperado": {"almoxarifado": sum(relatorios.contagem_por_status().get(k, 0)
                                         for k in ("em_estoque_recebimento", "divergencia")),
                     **relatorios.estoque_por_farmacia()},
        "contagens": inventario.listar(),
        "locais": inventario.locais(),
        "local_sugerido": local_sugerido,
    })


def novo(request: Request, local: str = (""), observacao: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem, id_inventario = inventario.abrir(local, usuario["username"], observacao)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    # Mesmo quando recusa por já existir contagem aberta, levamos para ela: é
    # o que a pessoa quer fazer — continuar contando, não ler um erro.
    return redirecionar(f"/inventario/{id_inventario}" if id_inventario else "/inventario")


def contagem(request: Request, id_inventario: str):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    dados = inventario.buscar(id_inventario)
    if not dados:
        return redirecionar("/inventario")
    if dados["status"] != "aberto":
        return redirecionar(f"/inventario/{id_inventario}/relatorio")
    return render(request, "inventario/contagem.html", {
        "inv": dados,
        "progresso": inventario.progresso(id_inventario),
        "leituras": inventario.leituras(id_inventario),
        "situacoes": inventario.SITUACOES,
    })


async def api_bipar(request: Request):
    from ..helpers.web_helper import exigir_login

    usuario = exigir_login(request)
    from ..providers.implementations.opme.security import pode_acessar
    if not pode_acessar(usuario["papel"], MODULO):
        return JSONResponse(
            {"ok": False, "mensagem": "Seu perfil não tem permissão para contar estoque."},
            status_code=403,
        )
    corpo = await request.json()
    resultado = inventario.bipar(
        corpo.get("id_inventario", ""), corpo.get("codigo", ""), usuario["username"],
        corpo.get("quantidade") or 1)
    resultado["progresso"] = inventario.progresso(corpo.get("id_inventario", ""))
    return JSONResponse(resultado)


def encerrar(request: Request, id_inventario: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = inventario.encerrar(id_inventario, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/inventario/{id_inventario}/relatorio")


def relatorio(request: Request, id_inventario: str, exportar: int = 0):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    dados = inventario.relatorio(id_inventario)
    if not dados:
        return redirecionar("/inventario")

    if exportar:
        linhas = (inventario.consolidado_para_exportar(id_inventario) if exportar == 2
                  else inventario.para_exportar(id_inventario))
        return Response(
            content=relatorios.para_csv(linhas).encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition":
                     f'attachment; filename="opme_inventario_{id_inventario}.csv"'},
        )
    return render(request, "inventario/relatorio.html", dados)
