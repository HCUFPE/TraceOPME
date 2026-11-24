"""Controller — Bipagem (TraceOPME).

Regras de tela do módulo, portadas de app/routers/bipagem.py da versão 17.
Cada função recebe a Requisicao (usuário já autenticado no AD/local e
autorizado no RBAC) e devolve render/redirecionar/JSON. Os endpoints
HTTP ficam em src/routers/bipagem.py.
Original:
    Tela única de bipagem + API que atende todas as etapas do fluxo.
"""

from ..helpers.web_helper import Requisicao as Request, ArquivoEnviado as UploadFile
from fastapi.responses import JSONResponse

from ..providers.implementations.opme.config import FARMACIAS, MOTIVOS_CANCELAMENTO
from ..providers.implementations.opme.domain import (BAIXADO, DIVERGENCIA, EM_ESTOQUE_RECEBIMENTO, OPERACOES,
                                                     SAIDA_OUTROS)
from ..providers.implementations.opme.services import (atendimentos, devolucoes, dispensacoes, fluxo,
                                                       saidas_outros, solicitacoes, usuarios)



def tela(request: Request, operacao: str, atendimento: str = "", busca: str = ""):
    from ..helpers.web_helper import render
    from ..helpers.web_helper import exigir_modulo, farmacia_atual, redirecionar

    op = OPERACOES.get(operacao)
    if op is None:
        return redirecionar("/")
    usuario = exigir_modulo(request, op.modulo)

    # v17 (out/2026): a devolução não é mais bipada — ao finalizar os utilizados,
    # a lista de não utilizados vai sozinha para a farmácia.
    if operacao == "devolver_nao_utilizado":
        from ..helpers.web_helper import avisar
        avisar(request, "A devolução não é mais bipada: em “Finalizar registro de uso e devoluções”, os não "
                        "utilizados ficam pendentes de devolução — leve-os à farmácia para conferência.", "info")
        return redirecionar(f"/sala-procedimento/atendimento/{atendimento}" if atendimento
                            else "/sala-procedimento")
    dados_atendimento = atendimentos.buscar(atendimento) if atendimento else None
    if op.exige_atendimento and not dados_atendimento:
        return redirecionar(f"/{op.modulo}/atendimentos?operacao={operacao}")
    # v17: atendimento encerrado não recebe bip — mostra a ficha, onde está
    # a reabertura com a senha da supervisão.
    if op.define_atendimento and dados_atendimento and dados_atendimento["status"] != "aberto":
        from ..helpers.web_helper import avisar
        avisar(request, "Este atendimento está encerrado. Para bipar de novo, a supervisão precisa reabrir.", "erro")
        return redirecionar(f"/{op.modulo}/atendimento/{atendimento}")

    # v18.9/v18.10: registrar uso só com a sala aberta. A tela abre normalmente, com o
    # campo travado e o botão "Abrir sala agora" (sem ir para a ficha e voltar).
    sala_fechada = bool(operacao == "registrar_uso" and dados_atendimento and not fluxo.sala_aberta(atendimento))

    # Operações da farmácia só enxergam o estoque da farmácia em que o usuário
    # está trabalhando; o envio do almoxarifado escolhe o destino na própria tela.
    farmacia = farmacia_atual(request) if op.escopo_farmacia else ""
    # v18.12: dispensar para paciente de OUTRA unidade — sem farmácia escolhida, a tela já
    # abre na farmácia da unidade do paciente; com outra escolhida, avisa em destaque.
    farmacia_do_paciente = ""
    if operacao == "dispensar_sala" and dados_atendimento:
        from ..helpers.web_helper import definir_farmacia
        from ..providers.implementations.opme.config import farmacia_da_unidade
        farmacia_do_paciente = farmacia_da_unidade(dados_atendimento.get("unidade"))
        if farmacia_do_paciente and farmacia_do_paciente != farmacia:
            if not request.session.get("farmacia"):
                farmacia = definir_farmacia(request, farmacia_do_paciente)
                farmacia_do_paciente = ""
        else:
            farmacia_do_paciente = ""

    return render(request, "bipagem.html", {
        "op": op,
        "sala_fechada": sala_fechada,
        "motivos_selecao_manual": fluxo.MOTIVOS_SELECAO_MANUAL
                                  if operacao in fluxo.OPERACOES_SELECAO_MANUAL else (),
        "operacao": operacao,
        "atendimento": dados_atendimento,
        "descricao_atendimento": atendimentos.descrever(dados_atendimento),
        "pendentes": fluxo.pendentes_da_operacao(operacao, atendimento, farmacia),
        # Caixas fechadas aguardando esta etapa. A lista de pendentes conta
        # unidades e está certa em contar; mas quem confere trabalha na
        # unidade "caixa", e 43 linhas de uma caixa que ele não vai abrir
        # são 43 linhas de ruído.
        "caixas_pendentes": fluxo.caixas_pendentes_da_operacao(
            operacao, atendimento, farmacia),
        "elegiveis": fluxo.contar_elegiveis(operacao, farmacia),
        "busca": busca,
        "resultados": fluxo.buscar_elegiveis(operacao, busca, farmacia=farmacia) if busca else [],
        "resumo": atendimentos.resumo(atendimento) if dados_atendimento else None,
        "exige_motivo": (op.para in (DIVERGENCIA, BAIXADO, SAIDA_OUTROS)
                         or operacao == "estornar_envio_farmacia"),
        # v18.14: saída para outros procedimentos — o "motivo" é o destino
        # (setor/procedimento), com sugestões e campo livre.
        "destinos_outros": (saidas_outros.DESTINOS if operacao in saidas_outros.OPERACOES else []),
        # No registro de uso o motivo só é exigido se o material estiver vencido,
        # e isso só se sabe ao bipar. O campo fica visível desde o início para o
        # operador não travar no meio do procedimento sem onde escrever.
        "motivo_opcional": operacao == "registrar_uso",
        "usuario_atual": usuario,
        # Lista de quem pode confirmar o recebimento nas entregas conferidas na
        # hora — vazia nas demais operações, e a tela nem desenha o bloco.
        "confirmadores": usuarios.confirmadores(
            op.confirmacao_papel, usuario.get("username", "")),
        "farmacia": farmacia,
        "farmacias": FARMACIAS,
        "farmacia_do_paciente": farmacia_do_paciente,
        # v17: o que a sala já bipou e a farmácia ainda não confirmou.
        "devolucao_itens": (devolucoes.pendentes_do_atendimento(atendimento)
                            if operacao == "devolver_nao_utilizado" and dados_atendimento else []),
        # v17: o que a farmácia já bipou e a sala ainda não confirmou com a senha.
        "complemento_pendente": (dispensacoes.complemento_pendente(atendimento)
                                 if operacao == "registrar_uso" and dados_atendimento else []),
        "trava_sala": (dispensacoes.trava_do_registro(atendimento)
                       if operacao == "registrar_uso" and dados_atendimento else []),
        "uso_registrado": (fluxo.resumo_uso(atendimento)
                           if operacao == "registrar_uso" and dados_atendimento else None),
        "motivos_outro_codigo": solicitacoes.MOTIVOS_OUTRO_CODIGO,
        "motivos_falta": solicitacoes.MOTIVOS_FALTA,
        "solicitacao": (solicitacoes.situacao(atendimento)
                        if operacao == "dispensar_sala" and dados_atendimento else None),
        "motivos_cancelamento": MOTIVOS_CANCELAMENTO,
        "motivos_excluir_uso": ("Bipado em duplicidade", "Bipado no paciente errado",
                                "Material não foi utilizado", "Bipado o material errado"),
        "dispensado_no_paciente": (dispensacoes.do_atendimento(atendimento)
                                   if operacao == "registrar_uso" and dados_atendimento else []),
        "dispensacao_itens": (dispensacoes
                              .pendentes_do_atendimento(atendimento)
                              if operacao == "dispensar_sala" and dados_atendimento else []),
    })


async def api_abrir_sala(request: Request):
    """v18.10: "Abrir sala agora" direto da tela de registrar uso."""
    from ..helpers.web_helper import exigir_modulo
    usuario = exigir_modulo(request, "sala-procedimento")
    corpo = await request.json()
    ok, msg = atendimentos.abrir_sala(str(corpo.get("atendimento") or ""), usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": msg})


async def api_abrir_entrega(request: Request):
    """Confere a senha de quem recebe UMA vez, para abrir a entrega na tela.

    Não move nada e não substitui nada: cada leitura continua autenticando a
    senha por conta própria, então todo evento gravado é individualmente
    confirmado. Isto existe só para a tela poder dizer "entrega aberta por
    Fulano" antes da primeira leitura — antes, a senha errada só aparecia como
    tarja vermelha no primeiro material bipado, o que parece defeito do sistema
    e ensina a equipe a ignorar mensagem vermelha.
    """
    from ..helpers.web_helper import exigir_login

    usuario = exigir_login(request)
    corpo = await request.json()
    op = OPERACOES.get(corpo.get("operacao", ""))
    if op is None or not op.confirmacao_papel:
        return JSONResponse({"ok": False, "mensagem": "Operação inválida."}, status_code=400)

    ok, mensagem, responsavel = usuarios.confirmar_responsavel(
        usuario["username"], corpo.get("usuario_responsavel", ""),
        corpo.get("senha_responsavel", ""),
        papel_exigido=op.confirmacao_papel, quem=op.confirmacao_quem,
    )
    if not ok:
        return JSONResponse({"ok": False, "mensagem": mensagem})
    return JSONResponse({"ok": True, "nome": responsavel["nome"],
                         "username": responsavel["username"]})


async def api_bipar(request: Request):
    from ..helpers.web_helper import exigir_login, farmacia_atual

    usuario = exigir_login(request)
    corpo = await request.json()
    operacao = corpo.get("operacao", "")
    op = OPERACOES.get(operacao)
    if op is None:
        return JSONResponse({"ok": False, "mensagem": "Operação inválida."}, status_code=400)

    from ..providers.implementations.opme.security import pode_acessar
    if not pode_acessar(usuario["papel"], op.modulo):
        return JSONResponse(
            {"ok": False, "mensagem": "Seu perfil não tem permissão para esta operação."},
            status_code=403,
        )

    # No envio, a farmácia vem da tela (é a escolha do almoxarifado). Nas demais,
    # é sempre a farmácia da sessão — não dá para a tela pedir outra.
    farmacia = corpo.get("farmacia", "") if op.define_farmacia else farmacia_atual(request)

    # v17 (out/2026): seleção manual pelo AGHU (não deu para bipar) — exceção,
    # com motivo obrigatório e registro próprio na auditoria.
    manual = str(corpo.get("selecao_manual") or "").strip()
    if corpo.get("selecao_manual") is not None and corpo.get("selecao_manual") != "":
        if operacao not in fluxo.OPERACOES_SELECAO_MANUAL:
            return JSONResponse({"ok": False, "mensagem": "Seleção manual não é permitida nesta operação."})
        if manual not in fluxo.MOTIVOS_SELECAO_MANUAL:
            return JSONResponse({"ok": False, "mensagem": "Informe por que não foi possível bipar."})

    resultado = fluxo.bipar(
        operacao=operacao,
        codigo=corpo.get("codigo", ""),
        usuario=usuario["username"],
        id_atendimento=corpo.get("atendimento", ""),
        motivo=corpo.get("motivo", ""),
        observacao=corpo.get("observacao", ""),
        farmacia=farmacia,
        # Preenchido só na segunda chamada, depois que a tela mostrou as
        # opções de uma leitura ambígua (mesmo código, mais de uma unidade) e
        # o operador escolheu uma.
        id_unidade=corpo.get("id_unidade", ""),
        # Só usados por operações com `confirmacao_papel` (enviar kit e
        # dispensar direto para a sala, confirmados pela sala; devolver não
        # utilizados, confirmado pela farmácia): usuário e senha de quem está
        # recebendo o material, digitados na hora.
        usuario_responsavel=corpo.get("usuario_responsavel", ""),
        senha_responsavel=corpo.get("senha_responsavel", ""),
        # Segunda chamada de uma caixa: a pessoa já conferiu o conteúdo na tela,
        # e `excluir` traz as unidades que ficaram de fora.
        revisado=bool(corpo.get("revisado")),
        excluir=[str(i) for i in (corpo.get("excluir") or [])],
        # v17: quantidade digitada na devolução de uma caixa de consignado.
        quantidade=str(corpo.get("quantidade") or ""),
        # v17: caixa ativa no registro de uso (bipada antes do item) e nome de
        # quem está devolvendo, na devolução à farmácia.
        caixa=str(corpo.get("caixa") or ""),
        # Quem devolve é sempre o usuário logado — não é digitado (auditoria).
        devolvido_por=(usuario.get("nome") or usuario["username"]) if operacao == "devolver_nao_utilizado" else "",
        # nov/2026: segunda chamada depois do aviso de lote com validade mais
        # próxima — a pessoa deu ciência e segue com o lote que bipou.
        ciencia_validade=bool(corpo.get("ciencia_validade")),
    )
    if manual and resultado.get("ok") and resultado.get("item"):
        from ..providers.implementations.opme import db
        it = resultado["item"]
        with db.transacao() as conn:
            db.registrar_evento(
                conn, tipo="selecao_manual", id_unidade=it.get("id_unidade"),
                id_atendimento=corpo.get("atendimento", "") or None, usuario=usuario["username"],
                motivo=manual,
                observacao=(f"{op.titulo}: selecionado pelo AGHU {it.get('aghu')} "
                            f"(lote {it.get('lote')}, val. {it.get('validade')}), sem bipar."))
        resultado["selecao_manual"] = manual
    resultado["pendentes"] = len(fluxo.pendentes_da_operacao(
        operacao, corpo.get("atendimento", ""), farmacia if op.escopo_farmacia else ""))
    if op.exige_atendimento:
        resultado["resumo"] = atendimentos.resumo(corpo.get("atendimento", ""))
    if operacao == "dispensar_sala" and corpo.get("atendimento") and resultado.get("ok"):
        # Solicitação da sala: o bip deu o "check"? Se o material não foi pedido
        # (ou veio além do pedido), aceita e SINALIZA — o pedido segue faltando.
        resultado["solicitacao_atualizada"] = True
        if resultado.get("item"):
            aviso = solicitacoes.unidade_nao_solicitada(corpo.get("atendimento", ""),
                                                        resultado["item"].get("id_unidade", ""))
            if aviso:
                resultado.setdefault("alertas", []).append(aviso)
                resultado["nao_solicitado"] = aviso
    if (operacao == "registrar_uso" and resultado.get("ok") and resultado.get("item")
            and str(corpo.get("avaria") or "").strip()):
        # v18: o bip já veio marcado com o problema do material (caiu, danificado…).
        from ..providers.implementations.opme.services import avarias
        ok_av, msg_av = avarias.sinalizar(resultado["item"].get("id_unidade", ""), corpo.get("atendimento", ""),
                                          str(corpo.get("avaria") or ""), str(corpo.get("avaria_detalhe") or ""),
                                          usuario["username"])
        resultado.setdefault("alertas", []).append(msg_av)
    if operacao == "registrar_uso" and corpo.get("atendimento"):
        resultado["uso"] = fluxo.resumo_uso(corpo.get("atendimento", ""))
    if operacao == "devolver_fornecedor":
        # v18: cada item devolvido entra na devolução aberta (com número) do fornecedor dele.
        from ..providers.implementations.opme.services import devolucoes_fornecedor
        if resultado.get("ok") and resultado.get("item"):
            dev = devolucoes_fornecedor.anexar(resultado["item"].get("id_unidade", ""), usuario["username"],
                                               corpo.get("motivo", ""))
            if dev:
                resultado["devolucao_fornecedor"] = dev["id_devolucao"]
        resultado["devolucoes_abertas"] = devolucoes_fornecedor.abertas(usuario["username"])
    return JSONResponse(resultado)


async def api_avaria(request: Request):
    """v18: sinaliza, depois do bip, que o material registrado caiu/veio danificado."""
    from ..helpers.web_helper import exigir_login
    from ..providers.implementations.opme.security import pode_acessar
    from ..providers.implementations.opme.services import avarias
    usuario = exigir_login(request)
    if not pode_acessar(usuario["papel"], OPERACOES["registrar_uso"].modulo):
        return JSONResponse({"ok": False, "mensagem": "Seu perfil não tem permissão para esta operação."},
                            status_code=403)
    corpo = await request.json()
    id_atendimento = str(corpo.get("atendimento") or "")
    ok, msg = avarias.sinalizar(str(corpo.get("id_unidade") or ""), id_atendimento, str(corpo.get("motivo") or ""),
                                str(corpo.get("detalhe") or ""), usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": msg, "uso": fluxo.resumo_uso(id_atendimento)})


async def api_excluir_uso(request: Request):
    """Registro de uso: exclui, na própria tela de bipagem, um bip feito por engano.

    Mesma regra da tela de conclusão (fluxo.excluir_bip): motivo obrigatório,
    nada é apagado do histórico, e o item volta para onde estava antes do uso
    (na sala, se tinha sido dispensado; senão, ao estoque). Depois de finalizar
    os materiais utilizados não se exclui mais por aqui.
    """
    from ..providers.implementations.opme.security import pode_acessar
    from ..helpers.web_helper import exigir_login
    usuario = exigir_login(request)
    if not pode_acessar(usuario["papel"], OPERACOES["registrar_uso"].modulo):
        return JSONResponse({"ok": False, "mensagem": "Seu perfil não tem permissão para esta operação."},
                            status_code=403)
    corpo = await request.json()
    id_atendimento = str(corpo.get("atendimento") or "")
    estado = fluxo.resumo_uso(id_atendimento)
    if not estado["pode_excluir"]:
        return JSONResponse({"ok": False, "uso": estado, "mensagem":
                             "Os materiais utilizados já foram finalizados (ou o atendimento está "
                             "encerrado). A exclusão agora só com a supervisão."})
    ok, mensagem = fluxo.excluir_bip(str(corpo.get("id_unidade") or ""), id_atendimento,
                                     usuario["username"], str(corpo.get("motivo") or ""))
    return JSONResponse({"ok": ok, "mensagem": mensagem, "uso": fluxo.resumo_uso(id_atendimento),
                         "resumo": atendimentos.resumo(id_atendimento)})


def api_selecao_manual(request: Request, operacao: str = "", aghu: str = "", atendimento: str = "",
                       caixa: str = ""):
    """v17 (out/2026): lista por lote e validade para quem não conseguiu bipar."""
    from ..providers.implementations.opme.security import pode_acessar
    from ..helpers.web_helper import exigir_login, farmacia_atual
    usuario = exigir_login(request)
    op = OPERACOES.get(operacao)
    if op is None or not pode_acessar(usuario["papel"], op.modulo):
        return JSONResponse({"ok": False, "mensagem": "Operação inválida."}, status_code=403)
    grupos = fluxo.selecao_manual(operacao, aghu, atendimento,
                                  farmacia_atual(request) if op.escopo_farmacia else "", caixa)
    return JSONResponse({"ok": True, "grupos": grupos})


async def api_ciencia_entrega(request: Request):
    """v17 — ciência de que a caixa do material vai ser entregue ao paciente."""
    from ..providers.implementations.opme.services import entrega_paciente
    from ..helpers.web_helper import exigir_login

    usuario = exigir_login(request)
    corpo = await request.json()
    ok, mensagem = entrega_paciente.registrar_ciencia(
        corpo.get("id_unidade", ""), usuario["username"])
    return JSONResponse({"ok": ok, "mensagem": mensagem})


async def api_desfazer(request: Request):
    from ..helpers.web_helper import exigir_login

    usuario = exigir_login(request)
    corpo = await request.json()
    ok, mensagem = fluxo.desfazer_ultimo(
        corpo.get("id_unidade", ""), usuario["username"], corpo.get("motivo", "")
    )
    if ok:
        from ..providers.implementations.opme.services import devolucoes_fornecedor
        devolucoes_fornecedor.desfeito(corpo.get("id_unidade", ""))  # v18
    return JSONResponse({"ok": ok, "mensagem": mensagem})


def tratar_pendencias(
    request: Request,
    operacao: str,
    ids: list[str] = ([]),
    motivo: str = (""),
    destino: str = (EM_ESTOQUE_RECEBIMENTO),
    atendimento: str = (""),
):
    from ..helpers.web_helper import avisar
    from ..helpers.web_helper import exigir_modulo, redirecionar

    op = OPERACOES.get(operacao)
    if op is None:
        return redirecionar("/")
    usuario = exigir_modulo(request, op.modulo)

    ok, mensagem = fluxo.finalizar_pendencias(
        operacao=operacao, ids=ids, usuario=usuario["username"],
        motivo=motivo, destino=destino,
    )
    avisar(request, mensagem, "sucesso" if ok else "erro")
    sufixo = f"?atendimento={atendimento}" if atendimento else ""
    return redirecionar(f"/bipagem/{operacao}{sufixo}")
