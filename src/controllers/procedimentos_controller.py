"""Controller — Procedimentos (TraceOPME).

Regras de tela do módulo, portadas de app/routers/procedimentos.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/procedimentos.py.
Original:
    v17 (out/2026) — Procedimentos: abrir e ver os procedimentos do dia.
    
    Antes ficava dentro da Sala de procedimento. Agora é geral, porque a farmácia
    precisa do procedimento aberto para dispensar o OPME ao paciente antes de a
    sala começar. Daqui cada perfil segue para o que faz: a farmácia dispensa, a
    sala registra o uso.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

from ..providers.implementations.opme.config import UNIDADES_ATIVAS, locais
from ..providers.implementations.opme.services import atendimentos
from ..providers.implementations.opme.utils import data_iso, hoje_iso

MODULO = "procedimentos"


def lista(request: Request, data: str = "", unidade: str = "", sala: str = "", prontuario: str = "",
          so_opme: int = 0):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    data = data or hoje_iso()
    # nov/2026: a tela mostra todos os procedimentos importados, de todas as
    # unidades, com ou sem OPME (o filtro "só com OPME" saiu da tela).
    lista_ = atendimentos.listar(data, sala, prontuario, unidade=unidade, so_com_opme=bool(so_opme),
                                 todas_unidades=True)
    return render(request, "procedimentos/lista.html", {
        "solicitacoes": __import__("src.providers.implementations.opme.services.solicitacoes", fromlist=["x"]).resumo_lista(
            [x["id_atendimento"] for x in lista_]),
        "atendimentos": lista_, "data": data, "unidade": unidade, "sala": sala,
        "prontuario": prontuario, "so_opme": bool(so_opme),
        "locais": locais(), "especialidades": atendimentos.especialidades(),
        "especialidades_hospital": __import__("src.providers.implementations.opme.config", fromlist=["x"]).ESPECIALIDADES_HOSPITAL,
        "agenda_metabase": __import__("src.providers.implementations.opme.services.agenda_metabase",
                                      fromlist=["x"]).situacao(),
    })


async def abrir(request: Request):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    formulario = dict(await request.form())
    local = formulario.pop("local", "")
    if local and "|" in local:
        formulario["unidade"], formulario["sala"] = local.split("|", 1)
    seguir = formulario.pop("seguir", "")
    ok, resultado = atendimentos.abrir(formulario, usuario["username"])
    if not ok:
        avisar(request, resultado, "erro")
        return redirecionar("/procedimentos#novo")
    avisar(request, "Procedimento aberto.", "sucesso")
    if seguir == "solicitar" and ok:
        return redirecionar(f"/sala-procedimento/atendimento/{resultado}/solicitacao")
    if seguir == "dispensar":
        return redirecionar(f"/bipagem/dispensar_sala?atendimento={resultado}")
    if seguir == "uso":
        return redirecionar(f"/bipagem/registrar_uso?atendimento={resultado}")
    return redirecionar(f"/procedimentos?data={data_iso(formulario.get('data_procedimento')) or hoje_iso()}")


async def importar_agenda(request: Request, arquivo: UploadFile = None):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    conteudo = await arquivo.read()
    if not conteudo:
        avisar(request, "Selecione um arquivo CSV.", "erro")
        return redirecionar("/procedimentos")
    ok, mensagem = atendimentos.importar_agenda_csv(conteudo, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/procedimentos")


def buscar_agenda_metabase(request: Request, data: str = "", usuario_rede: str = "", senha: str = ""):
    """nov/2026: busca a agenda do dia no relatórios (Metabase) e importa — sem baixar CSV."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import agenda_metabase
    usuario = exigir_modulo(request, MODULO)
    dia = data_iso(data) or hoje_iso()
    if not agenda_metabase.configurada() and not usuario_rede:
        usuario_rede = usuario["username"]
    ok, mensagem = agenda_metabase.buscar_e_importar(dia, usuario["username"], "manual", usuario_rede, senha)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/procedimentos?data={dia}")
