"""Controller — Sala de procedimento (TraceOPME).

Regras de tela do módulo, portadas de app/routers/sala_procedimento.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/sala_procedimento.py.
Original:
    Módulo Sala de procedimento.
    
    Versão 17: não há mais farmácia nem dispensação. A sala abre o atendimento do
    paciente (à mão ou importando a agenda do AGHU) e bipa o material no momento do
    uso — o item sai direto do estoque do almoxarifado para o prontuário.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile

from ..providers.implementations.opme.config import MOTIVOS_CANCELAMENTO, UNIDADES_ATIVAS, locais, salas_da_unidade
from ..providers.implementations.opme.domain import EM_ESTOQUE_RECEBIMENTO, UTILIZADO
from ..providers.implementations.opme.services import fechamento, atendimentos, correcoes_uso, entrega_paciente, fluxo, relatorios
from ..providers.implementations.opme.utils import TURNOS, hoje_iso, texto

MODULO = "sala-procedimento"


def unidade_da_sessao(request: Request) -> str:
    """Onde a pessoa está trabalhando: Bloco Cirúrgico ou Hemodinâmica.

    Escolhido uma vez na entrada do módulo e lembrado na sessão. Filtra a lista
    de atendimentos e já preenche o local do novo atendimento.
    """
    valor = request.session.get("unidade_sala", "")
    return valor if valor in UNIDADES_ATIVAS else ""


def escolher_unidade(request: Request, unidade: str = (""), proximo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.config import rotulo_unidade
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    if unidade in UNIDADES_ATIVAS:
        request.session["unidade_sala"] = unidade
        avisar(request, f"Trabalhando agora em: {rotulo_unidade(unidade)}.", "sucesso")
    destino = proximo if proximo.startswith("/sala-procedimento") else "/sala-procedimento"
    return redirecionar(destino)


def hub(request: Request):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    unidade = unidade_da_sessao(request)
    return render(request, "sala_procedimento/hub.html", {
        "unidade_atual": unidade,
        "unidades": UNIDADES_ATIVAS,
        "cirurgias": len(atendimentos.listar(hoje_iso(), so_com_opme=True, unidade=unidade)),
        "disp_pendentes": _dispensacoes_pendentes(unidade),
        "a_concluir": atendimentos.a_concluir(unidade),
        "nao_recebidos": fechamento.pendencias_da_sala(unidade),
        "caixas_sala": __import__("src.providers.implementations.opme.services.caixas_sala", fromlist=["x"]).contar(unidade),
        # v18.3: salas abertas agora (aberta e ainda não finalizada pela sala).
        "salas_abertas": int(__import__("src.providers.implementations.opme.db", fromlist=["x"]).escalar(
            "SELECT COUNT(DISTINCT unidade || '|' || sala) FROM atendimentos WHERE status = 'aberto' "
            "AND COALESCE(sala_aberta_em,'') <> '' AND COALESCE(uso_finalizado_em,'') = ''"
            + (" AND unidade = ?" if unidade else ""), (unidade,) if unidade else ()) or 0),
    })


# ---------------------------------------------------------------- caixas na sala pelo dia
def caixas_na_sala(request: Request):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    unidade = unidade_da_sessao(request)
    ts = caixas_sala.listar(unidade)
    pend = [t for t in ts if t["status"] == "divergente" and t["faltaram"]]
    return render(request, "sala_procedimento/caixas.html", {
        "unidade_atual": unidade, "unidades": UNIDADES_ATIVAS,
        "chegando": [t for t in ts if t["status"] == "enviada"],
        "na_sala": [t for t in ts if t["status"] == "na_sala"],
        "devolvidas": [t for t in ts if t["status"] == "devolvida"],
        "pendencias": [(t, [i for i in caixas_sala.itens(t["id_turno"])
                            if i["situacao"] == "faltou" and i["status"] == "na_sala"]) for t in pend],
        "pode_dar_ciencia": usuario["papel"] in caixas_sala.PAPEIS_DA_SALA,
        "nome_logado": usuario.get("nome") or usuario["username"],
    })


def caixas_identificar(request: Request, codigo: str = ""):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return JSONResponse(caixas_sala.identificar(codigo, unidade_da_sessao(request)))


async def caixas_receber(request: Request):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    ok, msg = caixas_sala.receber(form.getlist("turno"), usuario)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/sala-procedimento/caixas")


def caixas_devolver(request: Request, id_turno: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import caixas_sala
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, msg = caixas_sala.devolver(id_turno, usuario)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/sala-procedimento/caixas")


def lista_atendimentos(request: Request, data: str = "", sala: str = "",
                       unidade: str | None = None,
                       prontuario: str = "", operacao: str = "registrar_uso",
                       so_opme: int = 1, turno: str = "", mostrar: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    # v18.30: um seletor só, com três opções. Os links antigos (so_opme=0/1)
    # continuam valendo quando "mostrar" não vem na URL.
    if mostrar == "pendente":
        pendentes, so_opme = True, 0
    elif mostrar == "todas":
        pendentes, so_opme = False, 0
    elif mostrar == "opme":
        pendentes, so_opme = False, 1
    else:
        pendentes = False
    data = data or hoje_iso()
    unidade_atual = unidade_da_sessao(request)
    # Sem filtro explícito na URL, vale a unidade escolhida na entrada.
    if unidade is None:
        unidade = unidade_atual
    lista = atendimentos.listar(data, sala, prontuario, unidade=unidade,
                                so_com_opme=bool(so_opme), turno=turno)
    todos_locais = locais()
    from ..providers.implementations.opme.services import solicitacoes
    resumo = solicitacoes.resumo_lista([a["id_atendimento"] for a in lista])
    if pendentes:
        # v18.30: "só com pedido pendente" — quem ainda espera material da farmácia.
        lista = [a for a in lista if resumo.get(a["id_atendimento"], {}).get("pendente")]
    return render(request, "sala_procedimento/atendimentos.html", {
        "atendimentos": atendimentos.marcar_conflitos(lista),
        # v18.29: a sala também vê quais procedimentos já têm OPME solicitado.
        "solicitacoes": resumo, "mostrar": ("pendente" if pendentes else "opme" if so_opme else "todas"),
        "data": data, "sala": sala, "unidade": unidade, "prontuario": prontuario,
        "so_opme": bool(so_opme), "turno": turno, "turnos": TURNOS,
        "unidades": UNIDADES_ATIVAS, "salas": salas_da_unidade(unidade) if unidade else [],
        "unidade_atual": unidade_atual,
        "locais": ([l for l in todos_locais if l[0] == unidade_atual]
                   if unidade_atual else todos_locais),
        "especialidades": atendimentos.especialidades(),
        "operacao": operacao, "base_modulo": MODULO,
        # v17: dispensações aguardando a senha da sala — de qualquer data, para o
        # procedimento não "sumir" da tela quando a data filtrada é outra.
        "disp_pendentes": _dispensacoes_pendentes(unidade_atual),
        "a_concluir": atendimentos.a_concluir(unidade_atual),
        "nao_recebidos": fechamento.pendencias_da_sala(unidade_atual),
    })


def _dispensacoes_pendentes(unidade: str) -> list[dict]:
    from ..providers.implementations.opme.services import dispensacoes
    return [d for d in dispensacoes.listar_pendentes() if not unidade or d["unidade"] == unidade]


async def criar_atendimento(request: Request):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    formulario = dict(await request.form())
    local = formulario.pop("local", "")
    if local and "|" in local:
        formulario["unidade"], formulario["sala"] = local.split("|", 1)
    ir_bipar = formulario.pop("ir_bipar", "")

    ok, resultado = atendimentos.abrir(formulario, usuario["username"])
    if not ok:
        avisar(request, resultado, "erro")
        return redirecionar("/sala-procedimento/atendimentos")
    if ir_bipar:
        return redirecionar(f"/bipagem/registrar_uso?atendimento={resultado}")
    return redirecionar(f"/sala-procedimento/atendimento/{resultado}")


async def importar_agenda(request: Request, arquivo: UploadFile = None):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    conteudo = await arquivo.read()
    if not conteudo:
        avisar(request, "Selecione um arquivo CSV.", "erro")
        return redirecionar("/sala-procedimento/atendimentos")
    ok, mensagem = atendimentos.importar_agenda_csv(conteudo, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar("/sala-procedimento/atendimentos")


def passar_sala(request: Request, id_atendimento: str, destino: str = "", motivo: str = ""):
    """v18.13.1: POST — entrou outro paciente na frente: a sala passa para ele (cada um com o seu material)."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, msg = atendimentos.passar_sala(id_atendimento, destino, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{destino if ok else id_atendimento}")


def detalhe_atendimento(request: Request, id_atendimento: str):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)

    atendimento = atendimentos.buscar(id_atendimento)
    if not atendimento:
        return redirecionar("/sala-procedimento/atendimentos")
    return render(request, "sala_procedimento/atendimento.html", {
        "atendimento": atendimento,
        "descricao": atendimentos.descrever(atendimento),
        "resumo": atendimentos.resumo(id_atendimento),
        # Dispensado ainda não usado aparece no bloco "Dispensado pela farmácia".
        "materiais": [m for m in atendimentos.materiais(id_atendimento)
                      if m["status"] not in ("transito_sala", "em_sala")],
        "entregas": entrega_paciente.do_atendimento(id_atendimento),
        "devolvidos": atendimentos.devolvidos(id_atendimento),
        # v18.34: dispensado para este paciente e usado em outro prontuário.
        "usados_em_outro": atendimentos.materiais_usados_em_outro(id_atendimento),
        # v18.37: usos que podem ter pegado a peça errada.
        "usos_a_corrigir": len(correcoes_uso.pendencias(id_atendimento)),
        # v17: o que a farmácia dispensou para este paciente.
        "dispensados": __import__("src.providers.implementations.opme.services.dispensacoes", fromlist=["x"]).do_atendimento(id_atendimento),
        "historico_encerramento": atendimentos.historico_encerramento(id_atendimento),
        # v17 (out/2026): finalização dos utilizados pela sala.
        "finalizado": fechamento.finalizado(atendimento),
        "lista_na_farmacia": fechamento.tem_devolucao_pendente(id_atendimento),
        "pendencias": fechamento.pendencias(id_atendimento),
        "solicitacao": __import__("src.providers.implementations.opme.services.solicitacoes", fromlist=["x"]).situacao(id_atendimento),
        "motivos_cancelamento": MOTIVOS_CANCELAMENTO,
        # v18.13.1: entrou outro paciente na frente — quem pode assumir a sala (o material não muda de dono).
        "sala_ocupada_por": atendimentos.quem_esta_na_sala(id_atendimento),
        "troca_candidatos": atendimentos.candidatos_troca(id_atendimento) if atendimento["status"] == "aberto" else [],
        "troca_itens": len([m for m in atendimentos.materiais(id_atendimento)
                            if m["status"] in ("transito_sala", "em_sala")]),
        "locais": locais(),
        "base_modulo": MODULO,
        "UTILIZADO": UTILIZADO,
        # v18.3: chamados (maqueiro / limpeza) desta sala, hoje.
        "chamados": _chamados().da_sala(atendimento["unidade"], atendimento["sala"]),
        "tipos_chamado": _chamados().TIPOS,
        "etapas_sala": __import__("src.providers.implementations.opme.services.monitoramento", fromlist=["x"]).do_atendimento(id_atendimento),
        "etapas_rotulos": __import__("src.providers.implementations.opme.services.monitoramento", fromlist=["x"]).ETAPAS,
    })


def _chamados():
    from ..providers.implementations.opme.services import chamados_sala as chamados
    return chamados


def abrir_sala(request: Request, id_atendimento: str, voltar: str = ""):
    """v18.3 — "Abrir sala". Em seguida, a ciência do material recebido (se a
    farmácia já mandou); senão, a ficha do procedimento."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import dispensacoes
    usuario = exigir_modulo(request, MODULO)
    ok, msg = atendimentos.abrir_sala(id_atendimento, usuario["username"])
    if not ok:
        avisar(request, msg, "erro")
        return redirecionar(voltar if texto(voltar).startswith("/sala-procedimento") else
                            f"/sala-procedimento/atendimento/{id_atendimento}")
    disp = dispensacoes.pendente_do_atendimento(id_atendimento)
    if disp and dispensacoes.itens(disp["id_dispensacao"], so_pendentes=True):
        avisar(request, f"{msg} Agora dê ciência do material que a farmácia mandou.", "sucesso")
        return redirecionar(f"/dispensacoes/{disp['id_dispensacao']}")
    avisar(request, f"{msg} Quando a farmácia mandar o material, a ciência aparece aqui.", "sucesso")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")


def salas(request: Request):
    """v18.3 — aba "Salas": abrir a sala para o paciente e seguir o fluxo de cada sala."""
    from ..helpers.web_helper import exigir_modulo, render
    from ..providers.implementations.opme.services import monitoramento
    exigir_modulo(request, MODULO)
    unidade = unidade_da_sessao(request)
    painel = monitoramento.painel(unidade) if unidade else {"salas": [], "etapas": monitoramento.ETAPAS}
    return render(request, "sala_procedimento/salas.html", {
        "unidade_atual": unidade, "unidades": UNIDADES_ATIVAS,
        "salas": painel["salas"], "etapas": painel["etapas"], "tipos_chamado": _chamados().TIPOS,
    })


def chamar(request: Request, id_atendimento: str, tipo: str = "", motivo: str = "", observacao: str = ""):
    """v18.3 — chamar maqueiro / limpeza para a sala deste procedimento."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    at = atendimentos.buscar(id_atendimento)
    if not at:
        return redirecionar("/sala-procedimento")
    ok, msg = _chamados().chamar(tipo=tipo, unidade=at["unidade"], sala=at["sala"], usuario=usuario["username"],
                                 motivo=motivo, observacao=observacao, id_atendimento=id_atendimento)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}#chamados")


def chamar_sala(request: Request, sala: str = "", tipo: str = "", motivo: str = "", observacao: str = ""):
    """v18.3 — chamar maqueiro / limpeza pela aba Salas (sem precisar abrir a ficha)."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, msg = _chamados().chamar(tipo=tipo, unidade=unidade_da_sessao(request), sala=sala,
                                 usuario=usuario["username"], motivo=motivo, observacao=observacao)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar("/sala-procedimento/salas")


def cancelar_chamado(request: Request, id_chamado: str, voltar: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, msg = _chamados().cancelar(id_chamado, usuario["username"], "cancelado pela sala")
    avisar(request, msg, "sucesso" if ok else "erro")
    destino = voltar if texto(voltar).startswith("/sala-procedimento/") else "/sala-procedimento"
    return redirecionar(destino)


async def salvar_atendimento(request: Request, id_atendimento: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    formulario = dict(await request.form())
    local = formulario.pop("local", "")
    if local and "|" in local:
        formulario["unidade"], formulario["sala"] = local.split("|", 1)
    ok, mensagem = atendimentos.atualizar(id_atendimento, formulario, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")


def tela_estorno(request: Request, prontuario: str = "", atendimento: str = "",
                 inicio: str = "", fim: str = ""):
    """v18: o estorno é por PACIENTE. Primeiro a lista de procedimentos (prontuário
    e/ou dia/período); ao abrir a ficha de um, os implantes dele com "estornar"."""
    from datetime import date, timedelta
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo
    from ..providers.implementations.opme.services import relatorios
    exigir_modulo(request, MODULO)
    fim = texto(fim) or date.today().isoformat()
    inicio = texto(inicio) or ("" if texto(prontuario) else (date.today() - timedelta(days=30)).isoformat())
    ficha = atendimentos.buscar(atendimento) if texto(atendimento) else None
    return render(request, "sala_procedimento/estorno.html", {
        "prontuario": prontuario, "inicio": inicio, "fim": fim,
        "id_atendimento": atendimento,
        "ficha": ficha,
        "pacientes": [] if ficha else relatorios.atendimentos_com_uso(inicio, fim, prontuario),
        "usos": fluxo.usos_estornaveis(id_atendimento=atendimento) if ficha else [],
        "destinos": fluxo.DESTINOS_ESTORNO,
        "recentes": fluxo.estornos_recentes(20),
    })


def tela_correcao_uso(request: Request, atendimento: str = ""):
    """v18.37: trocar a peça registrada num uso, quando o bipe pegou a errada."""
    from ..helpers.web_helper import render, exigir_modulo
    from ..providers.implementations.opme.services import correcoes_uso
    exigir_modulo(request, MODULO)
    ficha = atendimentos.buscar(atendimento) if texto(atendimento) else None
    return render(request, "sala_procedimento/correcao_uso.html", {
        "atendimento": ficha or {},
        "descricao": atendimentos.descrever(ficha) if ficha else "",
        "pendencias": correcoes_uso.pendencias(atendimento) if ficha else [],
    })


def executar_correcao_uso(request: Request, id_usado: str, id_na_sala: str = "",
                          motivo: str = ""):
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import correcoes_uso
    usuario = exigir_modulo(request, MODULO)
    ida = atendimentos.buscar_por_unidade(id_usado) if hasattr(atendimentos, "buscar_por_unidade") else None
    from ..providers.implementations.opme import db as _db
    ida = ida or _db.escalar("SELECT id_atendimento FROM unidades WHERE id_unidade = ?", (id_usado,))
    ok, mensagem = correcoes_uso.trocar(id_usado, id_na_sala, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/correcao-uso?atendimento={ida or ''}")


def executar_estorno(request: Request, id_unidade: str, motivo: str = (""),
                     destino: str = (EM_ESTOQUE_RECEBIMENTO), prontuario: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)

    antes = fluxo.buscar_unidade(id_unidade) or {}
    ok, mensagem = fluxo.estornar_uso(id_unidade, usuario["username"], motivo, destino)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    if texto(antes.get("id_atendimento")):
        return redirecionar(f"/sala-procedimento/estorno?atendimento={antes['id_atendimento']}")
    return redirecionar(f"/sala-procedimento/estorno?prontuario={prontuario}")


async def finalizar_uso(request: Request, id_atendimento: str):
    """v17 (out/2026): a sala finaliza os materiais utilizados. O que sobrou do
    que a farmácia dispensou vai, sozinho, para a lista de não utilizados; o
    encerramento é da farmácia, depois da ciência."""
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    form = await request.form()
    # Lista (desmarcando) ou bipando: vai para a farmácia só o que está em
    # "devolver". Sem o campo (tela antiga / sem não utilizados), vai tudo.
    devolver = ({str(v) for v in form.getlist("devolver")}
                if form.get("modo_sobras") in ("lista", "bipando") else None)
    ok, mensagem, _encerrou = fechamento.finalizar_uso(
        id_atendimento, usuario, ciencia_complemento=form.get("ciencia_complemento") == "1",
        devolver=devolver)
    if ok:
        avisar(request, mensagem, "sucesso")
        return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")
    # O bloqueio aparece numa janela vermelha, não numa faixa que passa batido.
    acoes = None
    if "dispensou" in mensagem:
        disp = __import__("src.providers.implementations.opme.services.dispensacoes", fromlist=["x"]).pendente_do_atendimento(id_atendimento)
        if disp:
            acoes = [("Confirmar recebimento", f"/dispensacoes/{disp['id_dispensacao']}")]
    avisar(request, mensagem, "janela", acoes=acoes)
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}/concluir")


# ---------------------------------------------------------
# v17 — concluir a bipagem, excluir bip, encerrar e reabrir
# ---------------------------------------------------------

def concluir(request: Request, id_atendimento: str):
    """Revisão antes de encerrar: o que foi bipado, com opção de excluir um bip."""
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    atendimento = atendimentos.buscar(id_atendimento)
    if not atendimento:
        return redirecionar("/sala-procedimento/atendimentos")
    from ..providers.implementations.opme.services import dispensacoes as _disp
    complemento = _disp.complemento_pendente(id_atendimento)
    sobras = fechamento.sobras(id_atendimento)
    ja_finalizado = fechamento.finalizado(atendimento)
    # v18.18: depois de finalizar, esta tela continua acessível enquanto houver
    # material novo (pedido extra no meio do procedimento) — é por aqui que a
    # sala dá ciência do que chegou depois. Antes ela era expulsa daqui e ficava
    # sem caminho nenhum.
    if atendimento["status"] != "aberto":
        return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")
    # v18.23: ciência da entrega da caixa ao paciente também segura esta tela aberta
    # — ela é exigida para encerrar e só pode ser dada aqui ou na ficha.
    entregas = entrega_paciente.do_atendimento(id_atendimento)
    falta_ciencia = [e for e in entregas if not e.get("ciencia_por")]
    if ja_finalizado and not complemento and not sobras["total"] and not falta_ciencia:
        return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")
    return render(request, "sala_procedimento/concluir.html", {
        "atendimento": atendimento,
        "descricao": atendimentos.descrever(atendimento),
        "usados": [m for m in atendimentos.materiais(id_atendimento) if m["status"] == UTILIZADO],
        "entregas": entregas,
        "sobras": sobras,
        "complemento": complemento,
        "ja_finalizado": ja_finalizado,
        "base_modulo": MODULO,
    })


def sobras_identificar(request: Request, id_atendimento: str, codigo: str = ""):
    from fastapi.responses import JSONResponse
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return JSONResponse(fechamento.identificar_sobra(id_atendimento, codigo))


def excluir_bip(request: Request, id_atendimento: str, id_unidade: str, motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = fluxo.excluir_bip(id_unidade, id_atendimento, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}/concluir")


def dar_ciencia(request: Request, id_atendimento: str, id_unidade: str):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = entrega_paciente.registrar_ciencia(id_unidade, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}/concluir")


def reabrir(request: Request, id_atendimento: str, usuario_supervisao: str = (""),
            senha_supervisao: str = (""), motivo: str = ("")):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = atendimentos.reabrir(id_atendimento, usuario["username"],
                                        usuario_supervisao, senha_supervisao, motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")


def cancelar(request: Request, id_atendimento: str, motivo: str = (""),
             detalhe: str = ("")):
    """v17 — procedimento previsto que não aconteceu."""
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = atendimentos.cancelar(id_atendimento, usuario["username"], motivo, detalhe)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")



def descancelar(request: Request, id_atendimento: str, motivo: str = ("")):
    """v18.43 — cancelamento feito por engano: o procedimento volta a ficar aberto."""
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = atendimentos.descancelar(id_atendimento, usuario["username"], motivo)
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")


# ---------------------------------------------------------
# Solicitação de OPME (o papel "Requisição de material")
# ---------------------------------------------------------

def solicitacao_tela(request: Request, id_atendimento: str, formulario: str = ""):
    from ..providers.implementations.opme.formularios_opme import FORMULARIOS
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    atendimento = atendimentos.buscar(id_atendimento)
    if not atendimento:
        return redirecionar("/sala-procedimento/atendimentos")
    sugerido = solicitacoes.formulario_sugerido(atendimento)
    sol = solicitacoes.buscar(id_atendimento)
    usados = sorted({i["formulario"] for i in (sol["itens"] if sol else [])})
    if formulario not in FORMULARIOS:
        formulario = sugerido or next((u for u in usados if u in FORMULARIOS), "") or next(iter(FORMULARIOS))
    pode, _ = solicitacoes._pode_editar(id_atendimento)
    return render(request, "sala_procedimento/solicitacao.html", {
        "atendimento": atendimento, "descricao": atendimentos.descrever(atendimento),
        "formularios": FORMULARIOS, "formulario": formulario, "sugerido": sugerido, "usados": usados,
        "outros_formularios": {k: {"titulo": f["titulo"],
                                   "itens": [f"{c} {d}" for c, d in f["linhas"]]}
                               for k, f in FORMULARIOS.items() if k != formulario},
        "linhas": solicitacoes.formulario_da_tela(id_atendimento, formulario),
        "observacao": (sol or {}).get("observacao") or "",
        "sol": solicitacoes.situacao(id_atendimento), "modo": "sala", "pode_editar": pode,
        "base_modulo": MODULO,
    })


async def solicitacao_salvar(request: Request, id_atendimento: str):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    dados = dict(await request.form())
    chave = str(dados.get("formulario") or "")
    qtds = {k[4:]: v for k, v in dados.items() if k.startswith("qtd_")}
    especs = {k[6:]: v for k, v in dados.items() if k.startswith("espec_")}
    ok, mensagem = solicitacoes.salvar_formulario(id_atendimento, chave, qtds, especs, usuario["username"],
                                                  observacao=dados.get("observacao"))
    avisar(request, mensagem, "sucesso" if ok else "erro")
    seguir = str(dados.get("seguir") or "")
    if ok and seguir == "concluir":
        return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}#solicitacao")
    if ok and seguir.startswith("formulario:"):
        chave = seguir.split(":", 1)[1]
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}/solicitacao?formulario={chave}")


def solicitacao_buscar(request: Request, q: str = "", formulario: str = ""):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return JSONResponse({"itens": solicitacoes.buscar_materiais(q, formulario)})


async def solicitacao_incluir(request: Request, id_atendimento: str):
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, MODULO)
    c = await request.json()
    ok, mensagem = solicitacoes.incluir_da_busca(id_atendimento, str(c.get("codigo") or ""),
                                                 str(c.get("descricao") or ""), c.get("quantidade"),
                                                 str(c.get("especificacao") or ""), usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": mensagem})


def solicitacao_painel_sala(request: Request, id_atendimento: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    pode, _ = solicitacoes._pode_editar(id_atendimento)
    return render(request, "sala_procedimento/_solicitado.html", {
        "sol": solicitacoes.situacao(id_atendimento), "modo": "sala", "pode_editar": pode,
        "atendimento": atendimentos.buscar(id_atendimento) or {}})


def solicitacao_avulso(request: Request, id_atendimento: str, codigo_aghu: str = (""),
                       descricao: str = (""), quantidade: str = ("")):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = solicitacoes.adicionar_avulso(id_atendimento, codigo_aghu, quantidade, descricao,
                                                 usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}/solicitacao")


def solicitacao_remover(request: Request, id_atendimento: str, id_item: int):
    from ..helpers.web_helper import avisar
    from ..providers.implementations.opme.services import solicitacoes
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    ok, mensagem = solicitacoes.remover_item(id_atendimento, id_item, usuario["username"])
    avisar(request, mensagem, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}/solicitacao")


# ---------------------------------------------------------
# v17 (out/2026) — material NÃO cadastrado (exceção das exceções)
# ---------------------------------------------------------

def nao_cadastrado_tela(request: Request, id_atendimento: str):
    from ..helpers.web_helper import render
    from ..providers.implementations.opme.services import nao_cadastrados
    from ..helpers.web_helper import exigir_modulo, redirecionar
    exigir_modulo(request, MODULO)
    atendimento = atendimentos.buscar(id_atendimento)
    if not atendimento:
        return redirecionar("/sala-procedimento/atendimentos")
    return render(request, "sala_procedimento/nao_cadastrado.html", {
        "atendimento": atendimento, "descricao": atendimentos.descrever(atendimento),
        "motivos": nao_cadastrados.MOTIVOS, "dados": {},
        "registrados": [r for r in nao_cadastrados.listar() if r["id_atendimento"] == id_atendimento],
    })


async def nao_cadastrado_registrar(request: Request, id_atendimento: str):
    from ..helpers.web_helper import avisar, render
    from ..providers.implementations.opme.services import nao_cadastrados
    from ..helpers.web_helper import exigir_modulo, redirecionar
    usuario = exigir_modulo(request, MODULO)
    dados = {k: str(v) for k, v in (await request.form()).items()}
    ok, mensagem = nao_cadastrados.registrar(id_atendimento, dados, usuario)
    if ok:
        avisar(request, mensagem, "sucesso")
        return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}")
    atendimento = atendimentos.buscar(id_atendimento)
    dados.pop("senha_supervisao", None)
    return render(request, "sala_procedimento/nao_cadastrado.html", {
        "atendimento": atendimento, "descricao": atendimentos.descrever(atendimento),
        "motivos": nao_cadastrados.MOTIVOS, "dados": dados, "erro": mensagem,
        "registrados": [r for r in nao_cadastrados.listar() if r["id_atendimento"] == id_atendimento],
    })


def nao_cadastrado_buscar(request: Request, q: str = ""):
    """nov/2026: sugestões de material enquanto a sala digita o nome."""
    from fastapi.responses import JSONResponse
    from ..providers.implementations.opme.services import nao_cadastrados
    from ..helpers.web_helper import exigir_modulo
    exigir_modulo(request, MODULO)
    return JSONResponse({"itens": nao_cadastrados.buscar_material(q)})


def nao_cadastrado_foto(request: Request, nome: str):
    """nov/2026: foto da etiqueta do material não cadastrado (sala, farmácia ou almoxarifado)."""
    from fastapi.responses import FileResponse, Response
    from ..helpers.web_helper import exigir_login
    from ..providers.implementations.opme.security import pode_acessar
    from ..providers.implementations.opme.services import nao_cadastrados
    usuario = exigir_login(request)
    if not any(pode_acessar(usuario["papel"], m) for m in ("sala-procedimento", "almoxarifado", "farmacia")):
        return Response("Sem acesso.", status_code=403)
    caminho = nao_cadastrados.caminho_foto(nome)
    if not caminho:
        return Response("Foto não encontrada.", status_code=404)
    return FileResponse(caminho, media_type="image/png" if nome.endswith(".png") else "image/jpeg")


def solicitacao_cancelar(request: Request, id_atendimento: str, motivo: str = ""):
    """v18.7.3: a sala cancela a solicitação de OPME."""
    from ..helpers.web_helper import avisar, exigir_modulo, redirecionar
    from ..providers.implementations.opme.services import solicitacoes
    usuario = exigir_modulo(request, MODULO)
    ok, msg = solicitacoes.cancelar(id_atendimento, usuario["username"], motivo)
    avisar(request, msg, "sucesso" if ok else "erro")
    return redirecionar(f"/sala-procedimento/atendimento/{id_atendimento}#solicitacao")
