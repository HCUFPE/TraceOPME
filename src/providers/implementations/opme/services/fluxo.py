"""Motor de bipagem: uma única rotina para todas as etapas do fluxo.

Versão 17: o fluxo é almoxarifado → uso no paciente (bipado na sala). Não há
mais farmácia, kit, dispensação nem retorno. Toda tela de leitura de código de
barras chama `bipar`. Isso garante que a regra é idêntica em todos
os pontos e que qualquer movimento gera evento de auditoria.
"""

import re
from .. import busca, db, gs1, log
from ..domain import (
    BAIXADO, BLOQUEADAS_POR_RECALL, DIVERGENCIA, EM_ESTOQUE_FARMACIA,
    EM_ESTOQUE_RECEBIMENTO, EM_SALA, ESTADOS, OPERACOES, SAIDA_OUTROS, SEPARADO,
    TRANSITO_RETORNO, TRANSITO_SALA, UTILIZADO, Operacao, explicar_recusa, rotulo,
)
from ..config import farmacia_valida, rotulo_farmacia
from ..erros import ErroDeNegocio
from ..utils import data_br, dias_para, normalizar_codigo, texto
from . import alertas, caixas, caixas_consignado, empenhos, entrega_paciente, recall, usuarios

# Quando a conferência de uma etapa devolve material porque "não chegou"/"não
# foi identificado", o lado que enviou precisa de um sinal — sem isso, a
# devolução só reaparece como pendência comum do lado de quem enviou, sem
# distinção de uma chegada nova de verdade. Ver `finalizar_pendencias`.
ALERTA_RETORNO = {
    ("conferir_farmacia", EM_ESTOQUE_RECEBIMENTO): (
        "almoxarifado", "Material devolvido pela Farmácia sem identificação",
        "não foram identificados na conferência da Farmácia e voltaram ao estoque do Almoxarifado",
    ),
    ("conferir_sala", EM_ESTOQUE_FARMACIA): (
        "farmacia", "Material devolvido pelo Bloco sem identificação",
        "não foram identificados na conferência da sala e voltaram ao estoque da Farmácia",
    ),
}

CAMPOS_ITEM = """
    u.id_unidade, u.codigo_barras, u.codigo_aghu, u.xProd, u.marca_fabricante,
    u.fornecedor, u.nLote, u.numero_serie, u.dFab, u.dVal, u.vUnCom,
    u.tipo_entrada, u.status, u.id_atendimento, u.chave_nf, u.numero_nf,
    u.criado_em, u.origem, u.farmacia, u.id_caixa, u.descritivo_hospital
"""


class ErroDeFluxo(ErroDeNegocio):
    """Erro de regra de negócio com mensagem pronta para o operador."""


class EscolhaNecessaria(ErroDeNegocio):
    """Mais de uma unidade elegível responde ao código bipado.

    O mesmo código de barras pode valer para lotes diferentes do mesmo
    material — ou, pior, para materiais completamente diferentes que por
    coincidência compartilham o código. Nos dois casos, quem bipa precisa ver
    as opções e escolher qual é; o sistema não decide sozinho por FEFO nem por
    nenhum outro critério.
    """

    def __init__(self, candidatas: list[dict]):
        self.candidatas = candidatas
        super().__init__("Mais de um item responde a este código.")


# =========================================================
# BUSCA DE UNIDADES
# =========================================================

def _candidatas(codigo: str) -> list[dict]:
    """Unidades que respondem ao que foi bipado (id, código de barras ou nº de série)."""
    return db.consultar(
        f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE UPPER(u.id_unidade) = UPPER(?)
               OR gtin(u.codigo_barras) = gtin(?)
               OR (u.numero_serie IS NOT NULL AND u.numero_serie <> ''
                   AND REPLACE(u.numero_serie, ' ', '') = ?)
            ORDER BY
                CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                u.dVal, u.criado_em""",
        (codigo, codigo, codigo),
    )


def buscar_unidade(id_unidade: str) -> dict | None:
    return db.consultar_um(
        f"""SELECT {CAMPOS_ITEM}, u.descritivo_hospital, u.codigo_consignado, u.cEAN,
                   a.prontuario, a.sala, a.especialidade, a.data_procedimento
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.id_unidade = ?""",
        (id_unidade,),
    )


def historico(id_unidade: str) -> list[dict]:
    return db.consultar(
        """SELECT tipo, status_anterior, status_novo, usuario, data_evento,
                  motivo, observacao, id_atendimento
           FROM eventos WHERE id_unidade = ? ORDER BY id_evento""",
        (id_unidade,),
    )


# =========================================================
# BIPAGEM
# =========================================================

def _selecionar(operacao: Operacao, candidatas: list[dict], id_atendimento: str,
                farmacia: str = "", id_unidade_escolhida: str = "",
                caixa_ativa: str = "") -> dict:
    """Escolhe a unidade correta ou explica exatamente por que não dá.

    Quando `id_unidade_escolhida` vem preenchido, é porque quem bipou já viu
    uma lista de opções (por causa de uma leitura anterior ambígua) e escolheu
    uma — a partir daqui só essa unidade é considerada, mas ela ainda passa
    por todas as mesmas checagens de segurança de baixo (farmácia, atendimento,
    caixa, recall, validade).
    """
    if not candidatas:
        raise ErroDeFluxo(
            "Código não encontrado. Confirme se o item foi cadastrado no Almoxarifado."
        )

    elegiveis = [c for c in candidatas if c["status"] in operacao.de]

    if id_unidade_escolhida:
        elegiveis = [c for c in elegiveis if c["id_unidade"] == id_unidade_escolhida]
        if not elegiveis:
            raise ErroDeFluxo(
                "A unidade escolhida não está mais disponível para esta operação "
                "— bipe o código de novo."
            )

    # Os estoques das duas farmácias são separados: uma não pode movimentar o
    # material que pertence à outra, mesmo que o código bipado exista.
    if operacao.escopo_farmacia and farmacia and elegiveis:
        da_farmacia = [c for c in elegiveis if texto(c.get("farmacia")) == farmacia]
        if not da_farmacia:
            outra = texto(elegiveis[0].get("farmacia"))
            raise ErroDeFluxo(
                f"Este material pertence ao estoque da "
                f"{rotulo_farmacia(outra) if outra else 'outra farmácia'} e não pode ser "
                f"movimentado a partir da {rotulo_farmacia(farmacia)}."
            )
        elegiveis = da_farmacia

    if not elegiveis:
        # Mensagem específica sobre o estado real do item.
        situacoes = sorted({c["status"] for c in candidatas})
        if operacao.codigo == "dispensar_sala":
            from ..domain import TRANSITO_FARMACIA
            for st in (EM_ESTOQUE_RECEBIMENTO, TRANSITO_FARMACIA):
                if st in situacoes:
                    n = sum(1 for c in candidatas if c["status"] == st)
                    # v18.23: diga QUAL lote está nessa situação. A farmácia costuma ter
                    # outro lote do mesmo produto em estoque e a recusa parecia errada.
                    lotes = sorted({texto(c.get("nLote")) for c in candidatas if c["status"] == st} - {""})
                    qual = f" Lote {', '.join(lotes[:2])}." if lotes else ""
                    raise ErroDeFluxo(explicar_recusa(operacao, st)
                                      + f"{qual} ({n} unidade(s) nessa situação.)")
        if len(situacoes) == 1:
            # v18.24: nomeie o lote também aqui ("já utilizado", "em outra sala"…).
            # Sem o lote, a recusa parece contradizer o estoque, que costuma ter
            # outro lote do mesmo produto disponível.
            lotes = sorted({texto(c.get("nLote")) for c in candidatas} - {""})
            qual = f" Lote {', '.join(lotes[:2])}." if lotes else ""
            raise ErroDeFluxo(explicar_recusa(operacao, situacoes[0])
                              + f"{qual} ({len(candidatas)} unidade(s) nessa situação.)")
        resumo = ", ".join(f"{sum(1 for c in candidatas if c['status'] == s)}× {rotulo(s)}"
                           for s in situacoes)
        raise ErroDeFluxo(
            f"Nenhuma unidade deste código está na situação exigida pela operação. "
            f"Situação atual do estoque: {resumo}."
        )

    # Operações dentro de um atendimento só podem tocar itens daquele atendimento.
    if (operacao.exige_atendimento and not operacao.define_atendimento
            and not operacao.registra_atendimento):
        do_atendimento = [c for c in elegiveis if texto(c["id_atendimento"]) == id_atendimento]
        if not do_atendimento:
            outro = elegiveis[0]
            if texto(outro["id_atendimento"]):
                raise ErroDeFluxo(
                    f"Este material está vinculado a outro atendimento "
                    f"(prontuário {outro.get('prontuario') or '—'}, sala {outro.get('sala') or '—'})."
                )
            raise ErroDeFluxo("Este material não foi separado para o atendimento selecionado.")
        elegiveis = do_atendimento

    # v18.36: no registro de uso, o material que JÁ ESTÁ na sala daquele
    # paciente vem primeiro. Sem isso o bipe podia pegar outra unidade do mesmo
    # lote parada em outro estoque — gravando "uso sem dispensação" e deixando a
    # unidade dispensada presa na sala, virando pendência de devolução.
    if operacao.codigo == "registrar_uso" and texto(id_atendimento):
        na_sala = [c for c in elegiveis
                   if texto(c.get("id_atendimento")) == texto(id_atendimento)
                   and c["status"] in (EM_SALA, TRANSITO_SALA)]
        if na_sala:
            elegiveis = na_sala

    # Item dentro de caixa não se move sozinho. A única exceção é o registro de
    # uso: é ali que a caixa se abre, e é o único momento em que o item
    # individual importa, porque é ele que vai para o prontuário. Nas demais
    # etapas, mover um item de dentro seria abrir a caixa sem ninguém saber.
    if operacao.codigo != "registrar_uso":
        soltos = [c for c in elegiveis if not texto(c.get("id_caixa"))]
        if not soltos:
            dentro = elegiveis[0]
            raise ErroDeFluxo(
                f"Este item está na caixa {dentro['id_caixa']}. Bipe a caixa para "
                f"movimentar tudo de uma vez, ou retire o item dela em "
                f"Almoxarifado → Caixas — a retirada exige motivo e fica registrada."
            )
        elegiveis = soltos
    else:
        # v17 — uso de item de caixa: primeiro a CAIXA, depois o item. Caixas
        # diferentes podem ter o mesmo material (mesmo código, até o mesmo lote);
        # só quem está com a caixa aberta na mão sabe de qual delas o item saiu.
        caixa_ativa = texto(caixa_ativa).strip().upper()
        caixas_do_item = sorted({texto(c.get("id_caixa")) for c in elegiveis if texto(c.get("id_caixa"))})
        if caixa_ativa:
            na_caixa = [c for c in elegiveis if texto(c.get("id_caixa")).strip().upper() == caixa_ativa]
            if not na_caixa:
                if caixas_do_item:
                    raise ErroDeFluxo(
                        f"Este item NÃO está na caixa {caixa_ativa}. Ele consta na(s) "
                        f"caixa(s) {', '.join(caixas_do_item)}. Confira de qual caixa ele "
                        f"saiu e bipe essa caixa antes do item.")
                raise ErroDeFluxo(
                    f"Este item NÃO está na caixa {caixa_ativa} — ele é do estoque solto "
                    f"(fora de caixa). Clique em “Sair da caixa” e bipe o item de novo.")
            elegiveis = na_caixa
        else:
            # v18.11.6: a SALA não precisa bipar a caixa — bipa só o item. Se ele está
            # numa caixa que pode ser usada neste atendimento, o uso sai dela sozinho.
            # Só pergunta a caixa se o mesmo material estiver em DUAS caixas usáveis.
            soltos = [c for c in elegiveis if not texto(c.get("id_caixa"))]
            if soltos:
                elegiveis = soltos
            else:
                from . import caixas_sala
                do_paciente = [c for c in elegiveis if texto(c.get("id_atendimento")) == id_atendimento]
                base = do_paciente or elegiveis
                usaveis, motivos = [], []
                for cx in sorted({texto(c.get("id_caixa")) for c in base}):
                    pode, motivo, _ = caixas_sala.permite_uso(cx, id_atendimento)
                    bloq = caixas_consignado.bloqueada_para(cx, id_atendimento)
                    if pode is False or bloq:
                        motivos.append(motivo or f"A caixa {cx} está bloqueada para conferência.")
                    else:
                        usaveis.append(cx)
                if not usaveis:
                    raise ErroDeFluxo(motivos[0] if motivos else
                                      f"Este item está na caixa {', '.join(caixas_do_item)}, que não pode ser usada aqui.")
                if len(usaveis) > 1:
                    raise ErroDeFluxo(
                        f"Este material está em mais de uma caixa ({', '.join(usaveis)}). Bipe a CAIXA de "
                        f"onde ele saiu e, em seguida, o item.")
                elegiveis = [c for c in base if texto(c.get("id_caixa")) == usaveis[0]]

    # Lote em recall não avança. A checagem fica aqui, no motor, e não em cada
    # tela: assim nenhuma operação futura pode esquecer de verificar. As
    # operações que tiram o material de circulação continuam liberadas — é
    # exatamente o que se quer fazer com um lote bloqueado.
    if operacao.codigo in BLOQUEADAS_POR_RECALL:
        item = elegiveis[0]
        bloqueio = recall.bloqueio_do_item(item.get("nLote"), item.get("codigo_aghu"))
        if bloqueio:
            raise ErroDeFluxo(
                f"Lote {item.get('nLote')} BLOQUEADO: {bloqueio['motivo']}. "
                f"Não movimente este material. Separe fisicamente e avise o "
                f"almoxarifado, que registra a devolução ao fornecedor ou a baixa."
            )

    # Vencido não avança em direção ao paciente. Preferir uma unidade válida do
    # mesmo código, se houver, em vez de recusar de cara.
    if operacao.barra_vencido:
        validos = [c for c in elegiveis if (dias_para(c.get("dVal")) or 0) >= 0
                   or not texto(c.get("dVal"))]
        if not validos:
            item = elegiveis[0]
            raise ErroDeFluxo(
                f"Material com validade vencida em {data_br(item.get('dVal'))}. "
                f"Não pode ser separado nem enviado para a sala. Separe o item "
                f"fisicamente e registre a baixa em Almoxarifado → Baixar item."
            )
        elegiveis = validos

    # Mais de uma unidade sobrevive a todas as checagens acima. Se todas forem
    # o mesmo produto — mesmo código AGHU, mesmo lote, mesma validade — são
    # unidades fungíveis do mesmo estoque, e tanto faz qual delas segue
    # (mantém a ordem FEFO já trazida pela consulta). A descrição NÃO entra:
    # o nome varia conforme quem cadastrou ("FIO GUIA TEFLONADO" x "FIO
    # TEFLONADO"), mas AGHU + lote + validade iguais são o mesmo produto.
    # O que não pode é o sistema decidir sozinho quando o código responde a
    # AGHU ou lotes DIFERENTES — aí só quem bipou sabe qual é a certa.
    if len(elegiveis) > 1:
        grupos: dict[tuple, dict] = {}
        for c in elegiveis:
            aghu = texto(c.get("codigo_aghu")).strip().upper()
            assinatura = (
                aghu,
                # Sem AGHU no cadastro, a descrição é o que resta para separar.
                "" if aghu else texto(c.get("xProd")).strip().upper(),
                gs1.lote_normalizado(c.get("nLote")),
                texto(c.get("dVal")).strip()[:10],
                # v17: dentro de uma caixa x solto no estoque também é "diferente"
                # — escolher a unidade errada estraga a contagem da caixa.
                texto(c.get("id_caixa")).strip().upper(),
            )
            grupos.setdefault(assinatura, c)
        if len(grupos) > 1:
            raise EscolhaNecessaria(list(grupos.values()))
    return elegiveis[0]


def resposta_lote_nao_encontrado(candidatas: list[dict], etiqueta: dict | None, op) -> dict | None:
    """v18.12: resposta "escolha o lote" quando o lote da etiqueta não existe no cadastro.
    None quando não há unidade elegível para oferecer (segue o erro normal)."""
    vistos, opcoes = set(), []
    for c in candidatas:
        if c["status"] not in op.de:
            continue
        assinatura = (texto(c.get("codigo_aghu")).upper(), gs1.lote_normalizado(c.get("nLote")),
                      texto(c.get("dVal"))[:10], texto(c.get("id_caixa")).upper())
        if assinatura not in vistos:
            vistos.add(assinatura)
            opcoes.append(c)
    if not opcoes:
        return None
    lido = texto((etiqueta or {}).get("lote"))
    return {
        "ok": False, "escolha": True, "lote_nao_encontrado": lido,
        "mensagem": (f"O lote da etiqueta ({lido}) não está cadastrado. Nada foi registrado — "
                     "confira a embalagem e escolha o lote certo, ou cancele a leitura."),
        "opcoes": [formatar_item(c) for c in opcoes[:8]],
    }


def _bipar_nucleo(
    *,
    operacao: str,
    codigo: str,
    usuario: str,
    id_atendimento: str = "",
    motivo: str = "",
    observacao: str = "",
    farmacia: str = "",
    id_unidade: str = "",
    excluir: list[str] | None = None,
    caixa: str = "",
    devolvido_por: str = "",
    recebido_por: str = "",
) -> dict:
    """Processa uma leitura. Nunca levanta exceção para o operador: devolve dict.

    Uso interno — `bipar()`, logo abaixo, é a função pública: ela cuida da
    confirmação do responsável da sala (quando a operação exige) antes de
    chamar esta aqui, e encadeia a conferência automática depois.
    """
    op = OPERACOES.get(operacao)
    if op is None:
        return {"ok": False, "mensagem": "Operação desconhecida."}

    etiqueta = busca.interpretar(codigo)
    bipado = texto(codigo)          # v18.43.2: o texto como veio do leitor
    codigo = normalizar_codigo(codigo)
    id_atendimento = texto(id_atendimento)
    aviso_etiqueta = ""
    aviso_dispensacao = ""
    if op.define_farmacia or op.escopo_farmacia:
        farmacia = farmacia_valida(farmacia)

    if not codigo:
        return {"ok": False, "mensagem": "Bipe ou digite um código."}

    # O que foi lido é uma caixa? Então a operação vale para tudo que está
    # dentro dela. O prefixo reservado (CX-) é o que distingue — por isso ele
    # não pode colidir com código de barras de fábrica.
    if caixas.e_codigo_caixa(codigo) and operacao != "registrar_uso":
        return caixas.aplicar_operacao(
            operacao=operacao, id_caixa=codigo, usuario=usuario,
            id_atendimento=id_atendimento, motivo=motivo,
            observacao=observacao, farmacia=farmacia, excluir=excluir,
        )

    if op.exige_atendimento and not id_atendimento:
        return {"ok": False, "mensagem": "Selecione o atendimento antes de bipar."}

    # v17: o uso é o único momento em que o material ganha paciente. Não pode
    # cair num atendimento inexistente ou já encerrado.
    if op.define_atendimento:
        situacao = db.consultar_um(
            "SELECT status FROM atendimentos WHERE id_atendimento = ?", (id_atendimento,))
        if not situacao:
            return {"ok": False, "mensagem": "Atendimento não encontrado. Selecione o paciente de novo."}
        if texto(situacao["status"]) != "aberto":
            return {"ok": False, "mensagem": ("Este atendimento está encerrado. Abra um novo "
                                              "atendimento para registrar mais uso.")}

    # v17 (out/2026): prontuário com dispensação da farmácia aguardando a
    # confirmação da enfermagem não bipa uso. A trava é do PRONTUÁRIO, não da
    # sala: a farmácia pode dispensar antes para vários pacientes da mesma sala.
    if operacao == "registrar_uso":
        from . import dispensacoes
        travas = dispensacoes.trava_do_registro(id_atendimento)
        if travas:
            qtd = sum(t["qtd"] for t in travas)
            return {"ok": False, "dispensacao_pendente": True, "mensagem": (
                f"A farmácia dispensou {qtd} item(ns) para este prontuário e o recebimento ainda "
                f"não foi confirmado. Confirme o recebimento (com o seu usuário) antes de bipar.")}

    # v17 — no uso, bipar uma caixa não move nada: só diz de qual caixa os
    # próximos itens estão saindo ("caixa ativa" na tela).
    if caixas.e_codigo_caixa(codigo):
        return caixas_consignado.abrir_para_uso(codigo, id_atendimento)

    if op.para in (DIVERGENCIA,) or operacao in ("baixar", "estornar_envio_farmacia"):
        if not texto(motivo):
            return {"ok": False, "mensagem": "Informe o motivo antes de bipar."}
    # v18.14: saída para outro procedimento — sem destino não há registro que sirva depois.
    if op.para == SAIDA_OUTROS and len(texto(motivo)) < 3:
        return {"ok": False, "mensagem": "Informe o destino (setor / procedimento) antes de bipar."}

    try:
        with db.transacao() as conn:
            candidatas = [dict(r) for r in conn.execute(
                f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
                    FROM unidades u
                    LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                    WHERE UPPER(u.id_unidade) = UPPER(?)
                       OR gtin(u.codigo_barras) = gtin(?)
                       OR (u.numero_serie IS NOT NULL AND u.numero_serie <> ''
                           AND REPLACE(u.numero_serie, ' ', '') = ?)
                    ORDER BY
                        CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                        u.dVal, u.criado_em""",
                (codigo, codigo, codigo),
            ).fetchall()]
            if not candidatas:
                # v17: etiqueta secundária (só validade/lote, sem GTIN): acha pelo lote.
                cond, extra = gs1.sql_por_lote(etiqueta)
                if cond:
                    candidatas = [dict(r) for r in conn.execute(
                        f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala, a.data_procedimento
                            FROM unidades u
                            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                            WHERE {cond}
                            ORDER BY CASE WHEN u.dVal IS NULL OR u.dVal = '' THEN 1 ELSE 0 END,
                                     u.dVal, u.criado_em""", extra).fetchall()]

            # v17: etiqueta GS1 — lote, série e validade lidos escolhem a unidade.
            # v18.43.2: o texto bipado inteiro é o código — se alguma unidade tem
            # exatamente ele, a busca é essa e não abre a lista de lotes do produto.
            candidatas = busca.preferir_exatos(candidatas, bipado)
            candidatas, aviso_etiqueta = gs1.filtrar(candidatas, etiqueta)

            # v18.12: o lote lido na etiqueta NÃO existe no cadastro. Antes o sistema
            # registrava outra unidade do mesmo produto (outro lote) só com um aviso —
            # o prontuário ficava com o lote errado. Agora nada é registrado: a tela
            # mostra os lotes que existem e a pessoa escolhe (ou cancela a leitura).
            if aviso_etiqueta and not texto(id_unidade):
                pede = resposta_lote_nao_encontrado(candidatas, etiqueta, op)
                if pede:
                    return pede

            # v17: o que a sala bipou como devolvido e a farmácia ainda não
            # confirmou não pode ser usado em paciente nenhum.
            if operacao == "registrar_uso" and candidatas:
                ids = [c["id_unidade"] for c in candidatas]
                aguardando = {r[0] for r in conn.execute(
                    f"""SELECT i.id_unidade FROM devolucao_itens i
                        JOIN devolucoes d ON d.id_devolucao = i.id_devolucao
                        WHERE i.situacao = 'pendente' AND d.status = 'pendente'
                          AND i.id_unidade IN ({','.join('?' for _ in ids)})""", ids).fetchall()}
                if aguardando:
                    livres = [c for c in candidatas if c["id_unidade"] not in aguardando]
                    if not [c for c in livres if c["status"] in op.de]:
                        raise ErroDeFluxo(
                            "Este material foi bipado como DEVOLVIDO e está aguardando a "
                            "confirmação da farmácia. Se ele foi usado, avise a farmácia para "
                            "desmarcá-lo na lista de não utilizados e bipe o uso de novo.")
                    candidatas = livres

            # v18.13: depois de "Finalizar materiais utilizados" a sala CONTINUA bipando
            # normalmente — inclusive material novo. A sala só fecha quando a farmácia
            # conclui a conferência (aí o atendimento é encerrado e a trava acima vale).

            # v17: dispensação — na sala, o que a farmácia dispensou para ESTE
            # paciente vem primeiro (e evita perguntar o lote).
            if operacao == "registrar_uso" and candidatas:
                caixa_cmp = texto(caixa).strip().upper()
                meus = [c for c in candidatas
                        if c["status"] in (TRANSITO_SALA, EM_SALA)
                        and texto(c.get("id_atendimento")) == id_atendimento
                        and (not caixa_cmp or texto(c.get("id_caixa")).upper() == caixa_cmp)]
                if meus:
                    candidatas = meus
                else:
                    # Depois o estoque; por último o dispensado para OUTRO paciente.
                    candidatas.sort(key=lambda c: 0 if c["status"] in (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO) else 1)

            if op.registra_atendimento and candidatas:
                ja = {r[0] for r in conn.execute(
                    f"""SELECT DISTINCT id_unidade FROM eventos
                        WHERE tipo = ? AND id_atendimento = ?
                          AND id_unidade IN ({','.join('?' for _ in candidatas)})""",
                    (op.codigo, id_atendimento, *[c["id_unidade"] for c in candidatas]),
                ).fetchall()}
                restantes = [c for c in candidatas if c["id_unidade"] not in ja]
                if ja and not [c for c in restantes if c["status"] in op.de]:
                    raise ErroDeFluxo(
                        "Este material já foi devolvido neste atendimento. Não é preciso "
                        "bipar de novo.")
                candidatas = restantes or candidatas

            # Caixa do dia com pendência (faltou item no retorno): só o que faltou
            # pode ser bipado — o resto já voltou ao estoque da farmácia.
            if operacao == "registrar_uso" and texto(caixa) and candidatas:
                from . import caixas_sala
                if caixas_sala.permite_uso(caixa, id_atendimento)[1] == "pendencia":
                    candidatas = [c for c in candidatas if c["status"] == EM_SALA
                                  and texto(c.get("id_caixa")).upper() == texto(caixa).upper()] or candidatas

            unidade = _selecionar(op, candidatas, id_atendimento, farmacia, id_unidade,
                                  caixa_ativa=caixa)

            if operacao == "registrar_uso" and texto(unidade.get("id_caixa")):
                from . import caixas_sala
                pode, motivo_turno, _ = caixas_sala.permite_uso(unidade["id_caixa"], id_atendimento)
                if pode is False:
                    raise ErroDeFluxo(motivo_turno)
                bloqueio = caixas_consignado.bloqueada_para(unidade["id_caixa"], id_atendimento)
                if bloqueio:
                    raise ErroDeFluxo(
                        f"Este item está na caixa {bloqueio['id_caixa']}, que está BLOQUEADA "
                        f"para conferência ({texto(bloqueio['bloqueio_motivo'])}). Use material "
                        f"de outra caixa ou peça à farmácia para conferir e liberar.")

            # O registro de uso descreve algo que já aconteceu no paciente.
            # Recusar aqui não desfaz o implante — só apagaria o rastro, que é
            # pior. Então o vencido passa, mas exige justificativa e vira alerta.
            usou_vencido = (
                operacao == "registrar_uso"
                and texto(unidade.get("dVal"))
                and (dias_para(unidade.get("dVal")) or 0) < 0
            )
            bloqueio_uso = (
                recall.bloqueio_do_item(unidade.get("nLote"), unidade.get("codigo_aghu"))
                if operacao == "registrar_uso" else None
            )
            if usou_vencido and not texto(motivo):
                raise ErroDeFluxo(
                    f"Este material venceu em {data_br(unidade.get('dVal'))}. O uso ainda "
                    f"pode ser registrado — não registrar seria pior —, mas é obrigatório "
                    f"informar o motivo no campo acima. O caso será sinalizado à gestão."
                )
            if bloqueio_uso and not texto(motivo):
                raise ErroDeFluxo(
                    f"O lote {unidade.get('nLote')} está bloqueado: {bloqueio_uso['motivo']}. "
                    f"Se o material já foi implantado, registre — o rastro é o que permite "
                    f"localizar o paciente depois —, mas informe a justificativa no campo acima."
                )

            # v17: registro de saída da farmácia. Uso de item que NÃO passou pela
            # dispensação grava a saída automaticamente e avisa; item dispensado
            # para outro paciente também é avisado.
            observacao_uso = ""
            if operacao == "registrar_uso":
                if unidade["status"] in (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA):
                    db.registrar_evento(
                        conn, tipo="saida_sem_dispensacao", id_unidade=unidade["id_unidade"],
                        id_atendimento=id_atendimento, usuario=usuario,
                        observacao="Usado na sala sem dispensação prévia; saída da farmácia registrada no uso")
                    from . import usos_sem_dispensacao
                    usos_sem_dispensacao.registrar(conn, id_unidade=unidade["id_unidade"],
                                                   id_atendimento=id_atendimento, usuario=usuario)
                    aviso_dispensacao = ("Item não foi dispensado pela farmácia para este paciente — a "
                                         "saída foi registrada no uso e a farmácia vai dar ciência.")
                elif (texto(unidade.get("id_atendimento")) != id_atendimento
                      and not (not texto(unidade.get("id_atendimento")) and texto(unidade.get("id_caixa")))):
                    aviso_dispensacao = (f"Atenção: este item tinha sido dispensado para outro paciente "
                                         f"(prontuário {unidade.get('prontuario') or '—'}). O uso foi "
                                         f"registrado neste paciente.")
                    # v18.34: o aviso aparecia só na tela de quem bipou. Depois
                    # disso o item sumia da ficha do paciente de origem, que
                    # fechava "sem nada sobrando", e o histórico não dizia para
                    # onde o material tinha ido. Fica registrado dos dois lados.
                    origem = texto(unidade.get("id_atendimento"))
                    linha_destino = conn.execute(
                        "SELECT prontuario FROM atendimentos WHERE id_atendimento = ?",
                        (id_atendimento,)).fetchone()
                    destino = texto(linha_destino[0]) if linha_destino else ""
                    db.registrar_evento(
                        conn, tipo="uso_em_outro_paciente", id_unidade=unidade["id_unidade"],
                        id_atendimento=origem, usuario=usuario,
                        observacao=(f"Material dispensado para este paciente foi registrado como "
                                    f"utilizado no prontuário {destino or '—'}."))
                    observacao_uso = (f"Material dispensado para o prontuário "
                                      f"{unidade.get('prontuario') or '—'} e usado neste paciente.")

            novo_atendimento = unidade["id_atendimento"]
            if op.define_atendimento:
                novo_atendimento = id_atendimento
            elif op.limpa_atendimento:
                novo_atendimento = None

            # O envio define a farmácia de destino; o estorno do envio a desfaz,
            # para o item poder ser enviado de novo à farmácia certa.
            nova_farmacia = unidade.get("farmacia")
            if op.define_farmacia:
                nova_farmacia = farmacia
            elif operacao == "estornar_envio_farmacia":
                nova_farmacia = None

            conn.execute(
                """UPDATE unidades
                   SET status = ?, id_atendimento = ?, farmacia = ?,
                       atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (op.para, novo_atendimento, nova_farmacia, db.agora(), usuario,
                 unidade["id_unidade"]),
            )
            # Usar é abrir: o item registrado no paciente deixa de pertencer à
            # caixa no mesmo commit. Assim a conciliação do retorno consegue
            # separar "foi usado" de "sumiu".
            caixa_de_origem = ""
            if operacao == "registrar_uso" and texto(unidade.get("id_caixa")):
                caixa_de_origem = texto(unidade["id_caixa"])
                caixas.registrar_saida_por_uso(conn, unidade["id_unidade"], usuario)
                from . import caixas_sala
                caixas_sala.marcar_uso(conn, unidade["id_unidade"], id_atendimento)
                observacao = f"[{caixa_de_origem}] retirado da caixa. {texto(observacao)}".strip()
            if observacao_uso:                       # v18.34: de onde o material veio
                observacao = f"{observacao_uso} {texto(observacao)}".strip()

            db.registrar_evento(
                conn,
                tipo=op.codigo,
                id_unidade=unidade["id_unidade"],
                id_atendimento=(id_atendimento if op.registra_atendimento
                                else novo_atendimento or unidade["id_atendimento"]),
                status_anterior=unidade["status"],
                status_novo=op.para,
                usuario=usuario,
                motivo=motivo,
                observacao=observacao,
                devolvido_por=devolvido_por,
                recebido_por=recebido_por,
            )
    except EscolhaNecessaria as ambiguo:
        # Não é uma recusa: o código é válido, só não é suficiente sozinho
        # para saber qual unidade é. Devolve as opções para a tela perguntar.
        return {
            "ok": False,
            "escolha": True,
            "mensagem": "Mais de um item responde a este código — escolha qual é.",
            "opcoes": [formatar_item(c) for c in ambiguo.candidatas],
        }
    except ErroDeFluxo as recusa:
        # Recusa de regra de negócio: esperada, vale como aviso para achar padrões
        # (por exemplo, um operador bipando sempre na etapa errada).
        log.info(f"bipagem recusada · operacao={operacao} · codigo={codigo} · {recusa}", usuario)
        return {"ok": False, "mensagem": str(recusa)}
    except Exception as falha:  # falha técnica — nada foi gravado
        log.erro(f"falha ao bipar · operacao={operacao} · codigo={codigo}", usuario, falha)
        return {
            "ok": False,
            "mensagem": ("Não foi possível registrar por uma falha do sistema. "
                         "Nada foi gravado. Tente novamente; se persistir, avise o suporte."),
        }

    # A caixa só perde item no uso, e é aí que a reposição precisa ser pedida —
    # senão o material sai da caixa e ninguém compra o substituto. A lista de
    # falta responde isso a qualquer momento; o alerta é o empurrão para quem
    # tem que comprar e não fica olhando tela.
    if caixa_de_origem:
        caixas.alertar_reposicao(
            caixa_de_origem, usuario,
            contexto=(f"Saiu por uso: {unidade['xProd']} — AGHU "
                      f"{unidade.get('codigo_aghu') or '—'}, prontuário "
                      f"{unidade.get('prontuario') or '—'}."),
        )

    if bloqueio_uso:
        alertas.criar(
            modulo_destino="consultas",
            titulo="Material de lote BLOQUEADO registrado como utilizado",
            mensagem=(
                f"{unidade['xProd']} — AGHU {unidade.get('codigo_aghu') or '—'} · "
                f"lote {unidade.get('nLote')}.\n"
                f"Bloqueio: {bloqueio_uso['motivo']}\n"
                f"Registrado por {usuario} com a justificativa: “{texto(motivo)}”.\n"
                f"Prontuário {unidade.get('prontuario') or '—'} — este paciente precisa "
                f"entrar na lista de acompanhamento do recall."
            ),
            usuario=usuario,
            ids_unidade=[unidade["id_unidade"]],
        )
        log.aviso(f"lote bloqueado utilizado · unidade={unidade['id_unidade']} · "
                  f"lote={unidade.get('nLote')} · motivo={texto(motivo)}", usuario)

    if usou_vencido:
        alertas.criar(
            modulo_destino="consultas",
            titulo="Material vencido registrado como utilizado",
            mensagem=(
                f"{unidade['xProd']} — AGHU {unidade.get('codigo_aghu') or '—'} · "
                f"lote {unidade.get('nLote') or '—'} · validade "
                f"{data_br(unidade.get('dVal'))}.\n"
                f"Registrado por {usuario} com o motivo: “{texto(motivo)}”.\n"
                f"Prontuário {unidade.get('prontuario') or '—'}, "
                f"sala {unidade.get('sala') or '—'}."
            ),
            usuario=usuario,
            ids_unidade=[unidade["id_unidade"]],
        )
        log.aviso(f"material vencido utilizado · unidade={unidade['id_unidade']} · "
                  f"validade={unidade.get('dVal')} · motivo={texto(motivo)}", usuario)

    item = dict(unidade)
    item["status"] = op.para
    resposta = {
        "ok": True,
        "mensagem": f"{unidade['xProd']} {op.verbo}.",
        "item": formatar_item(item),
        "alertas": alertas_do_item(unidade) + ([aviso_etiqueta] if aviso_etiqueta else [])
                   + ([aviso_dispensacao] if aviso_dispensacao else []),
    }
    # v17: débito automático do empenho pelo código AGHU.
    if operacao == "registrar_uso":
        debito = empenhos.vincular_automatico(unidade["id_unidade"], usuario)
        if debito:
            resposta["empenho"] = debito["mensagem"]
            if debito["alerta"]:
                resposta["alertas"] = list(resposta["alertas"]) + [debito["mensagem"]]
    # v17: material cuja caixa vai para o paciente. A tela abre o aviso
    # vermelho e só volta a ler depois que quem bipou der ciência.
    if operacao == "registrar_uso" and entrega_paciente.exige(unidade.get("codigo_aghu")):
        from . import materiais
        resposta["entrega_paciente"] = {
            "id_unidade": unidade["id_unidade"],
            "aghu": texto(unidade.get("codigo_aghu")),
            "produto": (materiais.descritivo_hospital(unidade.get("codigo_aghu"))
                        or unidade["xProd"]),
            "lote": texto(unidade.get("nLote")) or "—",
        }
    return resposta


def _farmacia_da_etapa_encadeada(encadeada, farmacia: str, alvo: str) -> str:
    """Farmácia com que rodar a conferência encadeada.

    No retorno da sala a tela não pergunta a farmácia — o material já sabe de
    onde saiu. Mas `conferir_retorno` é escopada por farmácia, e escopo vazio
    vira a farmácia padrão lá dentro: sem isso, devolver para a farmácia da
    Hemodinâmica seria recusado por pertencer "à outra farmácia".
    """
    if not encadeada.escopo_farmacia or texto(farmacia):
        return farmacia
    if caixas.e_codigo_caixa(alvo):
        linhas = db.consultar("SELECT farmacia FROM caixas WHERE id_caixa = ?", (alvo,))
    else:
        linhas = db.consultar("SELECT farmacia FROM unidades WHERE id_unidade = ?", (alvo,))
    return texto(linhas[0]["farmacia"]) if linhas else farmacia


MSG_SALA_FECHADA = ("A sala ainda não foi aberta para este paciente. Abra a sala primeiro "
                    "(ficha do paciente → “Abrir sala”) e depois registre o uso.")


def sala_aberta(id_atendimento: str) -> bool:
    """v18.9: o uso no paciente só é registrado com a sala aberta."""
    a = db.consultar_um("SELECT sala_aberta_em FROM atendimentos WHERE id_atendimento = ?", (texto(id_atendimento),))
    return bool(a and texto(a.get("sala_aberta_em")))


def bipar(**kw) -> dict:
    """v18.9: registrar uso exige a sala aberta (antes, o primeiro uso abria a sala sozinho)."""
    if (kw.get("id_atendimento") and kw.get("operacao") in ("registrar_uso", "uso_nao_cadastrado")
            and not sala_aberta(kw["id_atendimento"])):
        return {"ok": False, "mensagem": MSG_SALA_FECHADA, "sala_fechada": True}
    return _bipar(**kw)


def _bipar(
    *,
    operacao: str,
    codigo: str,
    usuario: str,
    id_atendimento: str = "",
    motivo: str = "",
    observacao: str = "",
    farmacia: str = "",
    id_unidade: str = "",
    usuario_responsavel: str = "",
    senha_responsavel: str = "",
    revisado: bool = False,
    excluir: list[str] | None = None,
    quantidade: str = "",
    caixa: str = "",
    devolvido_por: str = "",
    ciencia_validade: bool = False,
) -> dict:
    """Processa uma leitura. Nunca levanta exceção para o operador: devolve dict.

    Nas entregas conferidas na hora (`enviar_sala` e `dispensar_sala`, da
    farmácia para a sala; `devolver_farmacia`, da sala de volta para a
    farmácia), quem entrega bipa na frente de quem recebe, e quem recebe
    confirma com a própria senha ali mesmo — não há mais uma bipagem de
    conferência feita depois, sem ninguém junto. Por isso, quando a operação
    exige confirmação, autenticamos quem recebe ANTES de tocar no estoque (a
    autenticação grava tentativa/bloqueio numa conexão própria — não pode
    acontecer no meio da transação de baixo, ou o SQLite trava). Nada é gravado
    se a senha estiver errada. Se a entrega for aceita, encadeamos na hora a
    conferência, creditada a quem confirmou — não a quem operou o leitor.
    """
    op = OPERACOES.get(operacao)

    # Caixa numa entrega conferida (envio à sala, devolução à farmácia): antes de
    # mover, a tela mostra o conteúdo agrupado para quem recebe contar de olho —
    # 40 itens viram 8 ou 10 linhas. Só na segunda chamada, já conferida, com o
    # que ficou de fora em `excluir`, a caixa se move. Ver `caixas.revisao`.
    if (op is not None and op.confirmacao_papel and op.aceita_caixa and not revisado
            and caixas.e_codigo_caixa(normalizar_codigo(codigo))):
        return caixas.revisao(
            operacao=operacao, id_caixa=normalizar_codigo(codigo),
            id_atendimento=texto(id_atendimento),
            farmacia=farmacia_valida(farmacia) if op.escopo_farmacia else farmacia,
        )

    # v17 — devolução do que não foi utilizado: a sala bipa (sem senha) e a
    # farmácia confirma depois, com a senha. Ver `devolucoes`.
    if op is not None and op.codigo == "dispensar_sala":
        from . import dispensacoes
        return dispensacoes.bipar(codigo=codigo, id_atendimento=id_atendimento, usuario=usuario,
                                  id_unidade=id_unidade, farmacia=farmacia_valida(farmacia),
                                  ciencia_validade=ciencia_validade)
    if op is not None and op.codigo == "devolver_nao_utilizado":
        from . import devolucoes
        return devolucoes.bipar(codigo=codigo, id_atendimento=id_atendimento, usuario=usuario,
                                devolvido_por=devolvido_por, id_unidade=id_unidade,
                                quantidade=quantidade)

    responsavel = None
    if op is not None and op.confirmacao_papel:
        ok_confirmacao, mensagem_confirmacao, responsavel = usuarios.confirmar_responsavel(
            usuario, usuario_responsavel, senha_responsavel,
            papel_exigido=op.confirmacao_papel, quem=op.confirmacao_quem,
        )
        if not ok_confirmacao:
            return {"ok": False, "mensagem": mensagem_confirmacao}

    resultado = _bipar_nucleo(
        operacao=operacao, codigo=codigo, usuario=usuario,
        id_atendimento=id_atendimento, motivo=motivo, observacao=observacao,
        farmacia=farmacia, id_unidade=id_unidade, excluir=excluir, caixa=caixa,
    )

    if not (resultado.get("ok") and responsavel is not None):
        return resultado

    # v17 — devolução de não utilizados: não há etapa encadeada; a senha do
    # farmacêutico vira um evento de confirmação, creditado a ele.
    if not op.confirmacao_encadeia:
        alvo = (resultado.get("item") or {}).get("id_unidade")
        with db.transacao() as conn:
            db.registrar_evento(
                conn, tipo=f"confirmar_{op.codigo}", id_unidade=alvo,
                id_atendimento=texto(id_atendimento) or None,
                usuario=responsavel["username"],
                devolvido_por=devolvido_por, recebido_por=responsavel["nome"],
                observacao=(f"Recebimento confirmado com a senha de {responsavel['nome']}; "
                            f"devolvido por {devolvido_por}; bipado por {usuario}."))
        resultado["mensagem"] = (f"{resultado['mensagem']} Devolvido por {devolvido_por}; "
                                 f"recebido por {responsavel['nome']}.")
        resultado["recebido_por"] = responsavel["nome"]
        resultado["devolvido_por"] = devolvido_por
        return resultado

    # Encadeia a conferência, creditada a quem foi autenticado acima — o mesmo
    # código que acabou de mover para "em trânsito" identifica sozinho essa
    # unidade (ou caixa) agora, então não há nova ambiguidade possível aqui.
    alvo = (resultado.get("item") or {}).get("id_unidade") or (resultado.get("caixa") or {}).get("id_caixa")
    encadeada = OPERACOES[op.confirmacao_encadeia]
    conferencia = _bipar_nucleo(
        operacao=encadeada.codigo, codigo=alvo, usuario=responsavel["username"],
        id_atendimento=id_atendimento, motivo=motivo,
        observacao=(f"Conferido no ato da entrega, com a senha de "
                    f"{responsavel['nome']} — sem bipagem separada depois. "
                    f"{texto(observacao)}").strip(),
        farmacia=_farmacia_da_etapa_encadeada(encadeada, farmacia, alvo),
    )
    if not conferencia.get("ok"):
        # Não deveria acontecer — a conferência repete as mesmas checagens que
        # o envio acabou de passar, sobre o mesmo item, na sequência. Mas se
        # acontecer, o envio já foi gravado (o material está mesmo em
        # trânsito): melhor avisar e deixar a conferência manual completar,
        # do que fingir sucesso ou tentar desfazer um evento já registrado.
        log.erro(f"conferência automática falhou após {operacao} · "
                 f"codigo={alvo} · {conferencia.get('mensagem')}", responsavel["username"])
        resultado["mensagem"] += (
            f" Atenção: a confirmação automática falhou "
            f"({conferencia.get('mensagem')}) — use “{encadeada.titulo}” para "
            f"concluir."
        )
        return resultado

    resultado["mensagem"] = (
        f"{resultado['mensagem']} Conferido na hora por {responsavel['nome']}."
    )
    if "item" in conferencia:
        resultado["item"] = conferencia["item"]
    if "caixa" in conferencia:
        resultado["caixa"] = conferencia["caixa"]
    if "itens" in conferencia:
        resultado["itens"] = conferencia["itens"]
    resultado["alertas"] = (resultado.get("alertas") or []) + (conferencia.get("alertas") or [])
    return resultado


def formatar_item(unidade: dict) -> dict:
    # v17 (out/2026): a referência é SEMPRE a descrição do AGHU (catálogo do
    # hospital); a digitada ou trazida pela NF do fornecedor fica de apoio.
    descricao_aghu = texto(unidade.get("descritivo_hospital"))
    if not descricao_aghu and texto(unidade.get("codigo_aghu")):
        from . import materiais
        descricao_aghu = materiais.descritivo_hospital(unidade.get("codigo_aghu"))
    return {
        "descricao_aghu": descricao_aghu,
        "produto_fornecedor": unidade.get("xProd", ""),
        "id_unidade": unidade.get("id_unidade", ""),
        "codigo_barras": unidade.get("codigo_barras", ""),
        "caixa": unidade.get("id_caixa") or "",
        # O código AGHU é como o hospital identifica o item no dia a dia,
        # por isso vem antes da descrição em todas as listagens.
        "aghu": unidade.get("codigo_aghu") or "—",
        "produto": descricao_aghu or unidade.get("xProd", ""),
        "lote": unidade.get("nLote") or "—",
        "validade": data_br(unidade.get("dVal")) or "—",
        "fornecedor": unidade.get("fornecedor") or "—",
        "marca": unidade.get("marca_fabricante") or "—",
        "serie": unidade.get("numero_serie") or "",
        "status": unidade.get("status", ""),
        "status_rotulo": rotulo(unidade.get("status", "")),
        "farmacia": unidade.get("farmacia") or "",
        "farmacia_rotulo": rotulo_farmacia(unidade.get("farmacia")) if unidade.get("farmacia") else "",
    }


def alertas_do_item(unidade: dict) -> list[str]:
    avisos: list[str] = []
    dias = dias_para(unidade.get("dVal"))
    if dias is not None:
        if dias < 0:
            avisos.append(f"ATENÇÃO: validade vencida em {data_br(unidade.get('dVal'))}.")
        elif dias <= 30:
            avisos.append(f"Validade próxima: vence em {dias} dia(s).")
    if not texto(unidade.get("dVal")):
        avisos.append("Item sem data de validade cadastrada.")
    return avisos


# =========================================================
# KIT DO ATENDIMENTO
# =========================================================

def itens_do_kit(id_atendimento: str) -> list[dict]:
    """Material separado e ainda não enviado à sala, ordenado pelo código AGHU."""
    linhas = db.consultar(
        f"""SELECT {CAMPOS_ITEM} FROM unidades u
            WHERE u.id_atendimento = ? AND u.status = '{SEPARADO}'
            ORDER BY COALESCE(NULLIF(u.codigo_aghu,''),'zzz'), u.xProd, u.dVal""",
        (texto(id_atendimento),),
    )
    return [formatar_item(l) for l in linhas]


def dispensar_kit(
    *, id_atendimento: str, ids_enviar: list[str], usuario: str, observacao: str = "",
    usuario_responsavel: str = "", senha_responsavel: str = "",
) -> tuple[bool, str]:
    """Envia à sala os itens marcados; os desmarcados voltam ao estoque.

    A separação costuma acontecer na véspera. No dia, o farmacêutico revisa o
    kit: o que não vai mais ser usado é retirado e volta a ficar disponível
    para outro paciente, em vez de subir para a sala e voltar depois.

    Assim como no envio por bipagem, o responsável da sala confirma o
    recebimento na hora com a própria senha — por isso os itens marcados vão
    direto a "Na sala" (conferidos), em vez de ficarem esperando uma
    conferência bipada depois, sem ninguém junto.
    """
    id_atendimento = texto(id_atendimento)
    if not id_atendimento:
        return False, "Selecione o atendimento."

    kit = db.consultar(
        f"""SELECT id_unidade, xProd, codigo_aghu, id_caixa FROM unidades
            WHERE id_atendimento = ? AND status = '{SEPARADO}'""",
        (id_atendimento,),
    )
    if not kit:
        return False, "Não há material separado neste atendimento."

    marcados = {texto(i) for i in (ids_enviar or []) if texto(i)}
    enviados = [k for k in kit if k["id_unidade"] in marcados]
    retirados = [k for k in kit if k["id_unidade"] not in marcados]

    if not enviados:
        return False, ("Nenhum item marcado para envio. Para devolver o kit inteiro "
                       "ao estoque, use “Cancelar o kit”.")

    # Mesma regra do envio bipado — inclusive quem pode confirmar: a tela do kit
    # é só outra porta para `enviar_sala`.
    op_envio = OPERACOES["enviar_sala"]
    ok_confirmacao, mensagem_confirmacao, responsavel = usuarios.confirmar_responsavel(
        usuario, usuario_responsavel, senha_responsavel,
        papel_exigido=op_envio.confirmacao_papel, quem=op_envio.confirmacao_quem,
    )
    if not ok_confirmacao:
        return False, mensagem_confirmacao

    agora = db.agora()
    obs_conferencia = (f"Conferido no ato da dispensação do kit, com a senha de "
                       f"{responsavel['nome']} — sem bipagem separada depois. "
                       f"{texto(observacao)}").strip()
    with db.transacao() as conn:
        for item in enviados:
            conn.execute(
                """UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (TRANSITO_SALA, agora, usuario, item["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="enviar_sala", id_unidade=item["id_unidade"],
                id_atendimento=id_atendimento, status_anterior=SEPARADO,
                status_novo=TRANSITO_SALA, usuario=usuario, observacao=observacao,
            )
            conn.execute(
                """UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (EM_SALA, agora, responsavel["username"], item["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="conferir_sala", id_unidade=item["id_unidade"],
                id_atendimento=id_atendimento, status_anterior=TRANSITO_SALA,
                status_novo=EM_SALA, usuario=responsavel["username"],
                observacao=obs_conferencia,
            )
        for item in retirados:
            conn.execute(
                """UPDATE unidades SET status = ?, id_atendimento = NULL,
                                       atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (EM_ESTOQUE_FARMACIA, agora, usuario, item["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="cancelar_separacao", id_unidade=item["id_unidade"],
                id_atendimento=id_atendimento, status_anterior=SEPARADO,
                status_novo=EM_ESTOQUE_FARMACIA, usuario=usuario,
                motivo="Retirado do kit na dispensação",
                observacao=observacao,
            )
        # Itens de caixa: a caixa vai junto com o que foi (e o que ficou sai
        # dela). Sem isto a caixa ficava "Separado" com o conteúdo já na sala.
        caixas.acompanhar_dispensa_do_kit(
            conn, itens_kit=kit, ids_enviados={e["id_unidade"] for e in enviados},
            id_atendimento=id_atendimento, usuario=usuario,
        )

    log.info(f"kit dispensado · atendimento={id_atendimento} · "
             f"enviados={len(enviados)} · retirados={len(retirados)}", usuario)

    mensagem = (f"{len(enviados)} material(is) enviado(s) e conferido(s) na sala por "
               f"{responsavel['nome']}.")
    if retirados:
        mensagem += f" {len(retirados)} retirado(s) do kit e devolvido(s) ao estoque."
    return True, mensagem


def cancelar_kit(id_atendimento: str, usuario: str, motivo: str) -> tuple[bool, str]:
    """Devolve todo o kit ao estoque — cirurgia suspensa ou adiada."""
    id_atendimento = texto(id_atendimento)
    if not texto(motivo):
        return False, "Informe o motivo do cancelamento."

    kit = db.consultar(
        f"SELECT id_unidade, id_caixa FROM unidades WHERE id_atendimento = ? AND status = '{SEPARADO}'",
        (id_atendimento,),
    )
    if not kit:
        return False, "Não há material separado neste atendimento."

    agora = db.agora()
    with db.transacao() as conn:
        for item in kit:
            conn.execute(
                """UPDATE unidades SET status = ?, id_atendimento = NULL,
                                       atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (EM_ESTOQUE_FARMACIA, agora, usuario, item["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="cancelar_separacao", id_unidade=item["id_unidade"],
                id_atendimento=id_atendimento, status_anterior=SEPARADO,
                status_novo=EM_ESTOQUE_FARMACIA, usuario=usuario, motivo=motivo,
            )
        caixas.acompanhar_cancelamento_do_kit(conn, itens_kit=kit, usuario=usuario)
    log.aviso(f"kit cancelado · atendimento={id_atendimento} · itens={len(kit)} · "
              f"motivo={motivo}", usuario)
    return True, f"Kit cancelado. {len(kit)} material(is) devolvido(s) ao estoque da farmácia."


def mover_kit(
    *, origem: str, destino: str, usuario: str, motivo: str,
) -> tuple[bool, str]:
    """Passa o kit inteiro de um atendimento para outro.

    Acontece quando a cirurgia é remarcada para outro paciente no mesmo dia:
    o material já separado na véspera continua servindo, muda só o destinatário.
    """
    origem, destino = texto(origem), texto(destino)
    if not origem or not destino:
        return False, "Informe o atendimento de origem e o de destino."
    if origem == destino:
        return False, "O atendimento de destino precisa ser diferente do de origem."
    if not texto(motivo):
        return False, "Informe o motivo da troca."

    alvo = db.consultar_um("SELECT * FROM atendimentos WHERE id_atendimento = ?", (destino,))
    if not alvo:
        return False, "Atendimento de destino não encontrado."
    if alvo["status"] != "aberto":
        return False, "O atendimento de destino já foi encerrado."

    kit = db.consultar(
        f"SELECT id_unidade, id_caixa FROM unidades WHERE id_atendimento = ? AND status = '{SEPARADO}'",
        (origem,),
    )
    if not kit:
        return False, "Não há material separado no atendimento de origem."

    agora = db.agora()
    with db.transacao() as conn:
        for item in kit:
            conn.execute(
                """UPDATE unidades SET id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (destino, agora, usuario, item["id_unidade"]),
            )
            db.registrar_evento(
                conn, tipo="mover_kit", id_unidade=item["id_unidade"],
                id_atendimento=destino, status_anterior=SEPARADO, status_novo=SEPARADO,
                usuario=usuario, motivo=motivo,
                observacao=f"Kit transferido do atendimento {origem}",
            )
        caixas.acompanhar_troca_de_paciente(conn, itens_kit=kit, destino=destino,
                                            usuario=usuario)
    log.aviso(f"kit movido · de={origem} para={destino} · itens={len(kit)} · "
              f"motivo={motivo}", usuario)
    return True, (f"{len(kit)} material(is) transferido(s) para o prontuário "
                  f"{alvo['prontuario']}.")


DESTINOS_ESTORNO = {
    EM_ESTOQUE_RECEBIMENTO: "Voltar para a farmácia — a farmácia dá ciência de que o material voltou",
    DIVERGENCIA: "Marcar como divergência (material perdido ou danificado)",
    BAIXADO: "Baixar (material inutilizado, não volta ao estoque)",
}


def estornar_uso(
    id_unidade: str, usuario: str, motivo: str, destino: str = EM_ESTOQUE_RECEBIMENTO,
) -> tuple[bool, str]:
    """Cancela um implante registrado por engano.

    Substitui a antiga rotina de "excluir registro" da v13, com uma diferença
    importante: aqui nada é apagado. O uso continua no histórico, marcado como
    estornado, e o item recebe um novo estado explícito. Em rastreabilidade de
    implante, apagar registro é pior do que o erro que se quer corrigir.
    """
    motivo = texto(motivo)
    id_unidade = texto(id_unidade)

    if not motivo:
        return False, "Informe o motivo do estorno. Ele fica registrado na auditoria."
    if len(motivo) < 10:
        return False, "Descreva o motivo com mais detalhe — ele será lido em auditoria."
    if destino not in DESTINOS_ESTORNO:
        return False, "Destino inválido para o estorno."

    unidade = buscar_unidade(id_unidade)
    if not unidade:
        return False, "Item não encontrado."
    if unidade["status"] != UTILIZADO:
        return False, (f"Este item não está registrado como utilizado "
                       f"(situação atual: “{rotulo(unidade['status'])}”). Nada a estornar.")

    # v18: o estorno vale também depois do procedimento encerrado (ex.: bipado em
    # duplicidade). "Voltar" não cai mais direto no estoque: o item fica "na
    # sala", ligado ao paciente, numa devolução pendente — a farmácia dá ciência.
    atendimento_original = unidade["id_atendimento"]
    volta_pela_farmacia = destino == EM_ESTOQUE_RECEBIMENTO and bool(texto(atendimento_original))
    novo_atendimento = atendimento_original if destino == EM_SALA or volta_pela_farmacia else None
    if volta_pela_farmacia:
        destino = EM_SALA
    elif destino == EM_ESTOQUE_RECEBIMENTO and texto(unidade.get("farmacia")):
        destino = EM_ESTOQUE_FARMACIA

    with db.transacao() as conn:
        conn.execute(
            """UPDATE unidades SET status = ?, id_atendimento = ?,
                                   atualizado_em = ?, atualizado_por = ?
               WHERE id_unidade = ?""",
            (destino, novo_atendimento, db.agora(), usuario, id_unidade),
        )
        from . import usos_sem_dispensacao
        usos_sem_dispensacao.cancelar(conn, id_unidade, f"Uso estornado: {motivo}")
        db.registrar_evento(
            conn, tipo="estornar_uso", id_unidade=id_unidade,
            id_atendimento=atendimento_original, status_anterior=UTILIZADO,
            status_novo=destino, usuario=usuario, motivo=motivo,
            observacao=(f"Uso estornado. Vínculo original: prontuário "
                        f"{unidade.get('prontuario') or '—'}, sala {unidade.get('sala') or '—'}."
                        + (" Volta para a farmácia: aguardando a ciência." if volta_pela_farmacia else "")),
        )
        if volta_pela_farmacia:
            from . import devolucoes
            devolucoes.abrir_retorno(conn, atendimento_original, usuario, unidades=[id_unidade],
                                     origem=f"Uso estornado: {motivo}")

    empenhos.desfazer_vinculo_da_unidade(id_unidade, usuario, f"Uso estornado: {motivo}")
    log.aviso(
        f"uso estornado · unidade={id_unidade} · destino={destino} · motivo={motivo}", usuario)
    if volta_pela_farmacia:
        return True, ("Uso estornado. O item volta para a farmácia, que precisa dar ciência "
                      "(Farmácia → Não utilizados — dar ciência). O registro anterior continua no histórico.")
    return True, (f"Uso estornado. O item passou para “{rotulo(destino)}”. "
                  "O registro anterior continua visível no histórico.")


def _atendimento_encerrado(id_atendimento) -> bool:
    if not texto(id_atendimento):
        return False
    situacao = db.consultar_um(
        "SELECT status FROM atendimentos WHERE id_atendimento = ?", (texto(id_atendimento),))
    return bool(situacao) and texto(situacao["status"]) != "aberto"


def excluir_bip(id_unidade: str, id_atendimento: str, usuario: str,
                motivo: str) -> tuple[bool, str]:
    """v17 — na conclusão da bipagem, quem bipou tira um bip lançado por engano.

    O item volta ao estoque do almoxarifado, sem paciente. Nada é apagado: o uso
    e a exclusão ficam no histórico, com o motivo. Só vale com o atendimento
    aberto — depois de encerrado, só a supervisão reabre.
    """
    motivo = texto(motivo)
    if not motivo:
        return False, "Informe o motivo da exclusão (ex.: bipado em duplicidade)."
    unidade = buscar_unidade(texto(id_unidade))
    if not unidade or unidade["status"] != UTILIZADO:
        return False, "Este item não está registrado como utilizado."
    if texto(unidade["id_atendimento"]) != texto(id_atendimento):
        return False, "Este bip não pertence a este atendimento."
    if _atendimento_encerrado(id_atendimento):
        return False, "Atendimento encerrado. Peça à supervisão para reabri-lo."

    # v17: se o item tinha sido dispensado, volta para a sala (dispensado ao
    # paciente), não para o estoque — fisicamente ele continua na sala.
    antes = db.consultar_um(
        """SELECT status_anterior FROM eventos WHERE id_unidade = ? AND tipo = 'registrar_uso'
           ORDER BY id_evento DESC LIMIT 1""", (unidade["id_unidade"],))
    estava_na_sala = bool(antes) and antes["status_anterior"] in (TRANSITO_SALA, EM_SALA)
    # Sem dispensação: volta para o estoque de onde saiu (farmácia ou almoxarifado).
    destino = EM_SALA if estava_na_sala else (
        antes["status_anterior"] if antes and antes["status_anterior"] in (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO)
        else EM_ESTOQUE_RECEBIMENTO)
    # Item da caixa do dia: volta para a caixa na sala, sem paciente.
    from . import caixas_sala
    do_turno = caixas_sala.item_do_turno(unidade["id_unidade"])
    with db.transacao() as conn:
        conn.execute(
            """UPDATE unidades SET status = ?, id_atendimento = ?,
                                   atualizado_em = ?, atualizado_por = ?
               WHERE id_unidade = ?""",
            (destino, id_atendimento if (estava_na_sala and not do_turno) else None, db.agora(), usuario,
             unidade["id_unidade"]))
        caixas_consignado.recolocar_apos_correcao(conn, unidade["id_unidade"], usuario)
        from . import usos_sem_dispensacao
        usos_sem_dispensacao.cancelar(conn, unidade["id_unidade"], f"Bip excluído: {motivo}")
        db.registrar_evento(
            conn, tipo="excluir_bip", id_unidade=unidade["id_unidade"],
            id_atendimento=id_atendimento, status_anterior=UTILIZADO,
            status_novo=destino, usuario=usuario, motivo=motivo,
            observacao=("Bip excluído na conclusão da bipagem; item continua na sala (dispensado)."
                        if estava_na_sala else
                        "Bip excluído na conclusão da bipagem; item voltou ao estoque."))
    empenhos.desfazer_vinculo_da_unidade(unidade["id_unidade"], usuario, f"Bip excluído: {motivo}")
    log.aviso(f"bip excluído · unidade={unidade['id_unidade']} · motivo={motivo}", usuario)
    return True, (f"Bip excluído: {unidade['xProd']} "
                  + ("continua na sala, dispensado para o paciente." if estava_na_sala
                     else "voltou ao estoque do almoxarifado."))


def lista_uso(id_atendimento: str) -> list[dict]:
    """Registro de uso: o que já foi registrado como utilizado neste paciente.

    Aparece logo abaixo do campo de leitura (o mais recente primeiro), para quem
    está bipando não se perder do que já bipou — com o botão de excluir o bip.
    """
    if not texto(id_atendimento):
        return []
    from ..utils import data_hora_br
    linhas = db.consultar(
        f"""SELECT u.*, e.data_evento AS bipado_em, e.usuario AS bipado_por
            FROM unidades u
            LEFT JOIN (SELECT id_unidade, MAX(id_evento) AS ultimo
                       FROM eventos WHERE tipo = 'registrar_uso' GROUP BY id_unidade) ue
                   ON ue.id_unidade = u.id_unidade
            LEFT JOIN eventos e ON e.id_evento = ue.ultimo
            WHERE u.id_atendimento = ? AND u.status = '{UTILIZADO}'
            ORDER BY COALESCE(ue.ultimo, 0) DESC, u.atualizado_em DESC""",
        (texto(id_atendimento),))
    from . import avarias
    problemas = avarias.do_atendimento(id_atendimento)
    saida = []
    for linha in linhas:
        item = formatar_item(linha)
        item["quando"] = data_hora_br(linha.get("bipado_em") or linha.get("atualizado_em")) or "—"
        item["por"] = linha.get("bipado_por") or linha.get("atualizado_por") or ""
        item["avaria"] = problemas.get(linha["id_unidade"])  # v18
        saida.append(item)
    return saida


def resumo_uso(id_atendimento: str) -> dict:
    """Bloco "Já registrado neste paciente" da tela de registro de uso."""
    at = db.consultar_um("SELECT status, uso_finalizado_em FROM atendimentos WHERE id_atendimento = ?",
                         (texto(id_atendimento),))
    # v18.13: a sala continua podendo corrigir o que bipou enquanto o atendimento estiver aberto
    pode_excluir = bool(at) and at["status"] == "aberto"
    from . import avarias
    return {"lista": lista_uso(id_atendimento), "pode_excluir": pode_excluir,
            "motivos_avaria": avarias.MOTIVOS_AVARIA,
            "pode_sinalizar": bool(at) and at["status"] == "aberto"}


def usos_estornaveis(
    *, prontuario: str = "", id_atendimento: str = "", dias: int = 30, limite: int = 100,
) -> list[dict]:
    """Implantes registrados que ainda podem ser estornados."""
    condicoes = [f"u.status = '{UTILIZADO}'"]
    params: list = []

    if texto(prontuario):
        condicoes.append("a.prontuario = ?")
        params.append(texto(prontuario))
    if texto(id_atendimento):
        condicoes.append("u.id_atendimento = ?")
        params.append(texto(id_atendimento))
    if not texto(prontuario) and not texto(id_atendimento):
        condicoes.append("julianday('now') - julianday(e.data_evento) <= ?")
        params.append(dias)
    params.append(limite)

    return db.consultar(
        f"""SELECT u.id_unidade, u.xProd, u.nLote, u.dVal, u.numero_serie, u.codigo_barras,
                   u.fornecedor, a.prontuario, a.paciente, a.sala, a.especialidade,
                   a.data_procedimento, e.data_evento, e.usuario
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            LEFT JOIN (SELECT id_unidade, MAX(id_evento) AS ultimo FROM eventos
                       WHERE tipo = 'registrar_uso' GROUP BY id_unidade) ult
                   ON ult.id_unidade = u.id_unidade
            LEFT JOIN eventos e ON e.id_evento = ult.ultimo
            WHERE {' AND '.join(condicoes)}
            ORDER BY e.data_evento DESC LIMIT ?""",
        params,
    )


def estornos_recentes(limite: int = 50) -> list[dict]:
    return db.consultar(
        """SELECT e.data_evento, e.usuario, e.motivo, e.status_novo, e.observacao,
                  u.id_unidade, u.xProd, u.nLote, a.prontuario, a.sala
           FROM eventos e
           LEFT JOIN unidades u ON u.id_unidade = e.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
           WHERE e.tipo = 'estornar_uso'
           ORDER BY e.id_evento DESC LIMIT ?""",
        (limite,),
    )


def desfazer_ultimo(id_unidade: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    """Desfaz o último movimento de uma unidade — o 'ctrl+z' do operador."""
    evento = db.consultar_um(
        """SELECT * FROM eventos WHERE id_unidade = ? AND status_anterior IS NOT NULL
           ORDER BY id_evento DESC LIMIT 1""",
        (id_unidade,),
    )
    if not evento:
        return False, "Não há movimento para desfazer neste item."

    unidade = buscar_unidade(id_unidade)
    if not unidade:
        return False, "Item não encontrado."
    if unidade["status"] != evento["status_novo"]:
        return False, "O item já sofreu outro movimento depois deste. Corrija manualmente."

    if evento["tipo"] == "registrar_uso" and _atendimento_encerrado(evento["id_atendimento"]):
        return False, ("O atendimento está encerrado. Peça à supervisão para reabri-lo "
                       "antes de excluir este bip.")

    anterior = evento["status_anterior"]
    atendimento = evento["id_atendimento"]
    if anterior in (SEPARADO, EM_SALA, TRANSITO_SALA, TRANSITO_RETORNO, UTILIZADO):
        novo_atendimento = atendimento
    else:
        # Desfazer um uso devolve o item ao estoque do almoxarifado — sem
        # paciente. Na v17 o uso sai direto do almoxarifado.
        novo_atendimento = (None if evento["tipo"] in ("separar", "registrar_uso")
                            else unidade["id_atendimento"])

    with db.transacao() as conn:
        conn.execute(
            """UPDATE unidades SET status = ?, id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
               WHERE id_unidade = ?""",
            (anterior, novo_atendimento, db.agora(), usuario, id_unidade),
        )
        if evento["tipo"] == "registrar_uso":
            caixas_consignado.recolocar_apos_correcao(conn, id_unidade, usuario)
            from . import usos_sem_dispensacao
            usos_sem_dispensacao.cancelar(conn, id_unidade, "Uso desfeito na bipagem")
        if evento["tipo"] == "dispensar_sala":
            from . import dispensacoes
            dispensacoes.marcar_removido_por_desfazer(conn, id_unidade)
        db.registrar_evento(
            conn, tipo="desfazer", id_unidade=id_unidade, id_atendimento=novo_atendimento,
            status_anterior=unidade["status"], status_novo=anterior, usuario=usuario,
            motivo=motivo or "Correção do operador",
            observacao=f"Desfeito: {evento['tipo']}",
        )
    if evento["tipo"] == "registrar_uso":
        empenhos.desfazer_vinculo_da_unidade(id_unidade, usuario, "Uso desfeito na bipagem")
    return True, f"Movimento desfeito. Item voltou para “{rotulo(anterior)}”."


# =========================================================
# LISTAS DE APOIO DAS TELAS DE BIPAGEM
# =========================================================

def _filtro_farmacia(op: Operacao, farmacia: str) -> tuple[str, list]:
    """Recorte de farmácia para as operações que só enxergam um dos estoques."""
    if not op.escopo_farmacia or not texto(farmacia):
        return "", []
    return " AND u.farmacia = ?", [farmacia_valida(farmacia)]


def pendentes_da_operacao(operacao: str, id_atendimento: str = "",
                          farmacia: str = "") -> list[dict]:
    """O que ainda falta bipar nesta etapa. É a lista que o operador confere."""
    op = OPERACOES.get(operacao)
    if op is None or not op.mostra_pendentes:
        # Sem conjunto esperado, a "lista de pendentes" seria o estoque inteiro.
        return []

    marcadores = ",".join("?" for _ in op.de)
    params: list = list(op.de)
    filtro_atendimento = ""

    if op.exige_atendimento and not op.define_atendimento:
        filtro_atendimento = " AND u.id_atendimento = ?"
        params.append(id_atendimento)

    filtro_farmacia, params_farmacia = _filtro_farmacia(op, farmacia)
    params += params_farmacia

    linhas = db.consultar(
        f"""SELECT {CAMPOS_ITEM}, a.prontuario, a.sala
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.status IN ({marcadores}){filtro_atendimento}{filtro_farmacia}
            ORDER BY u.xProd, u.dVal, u.nLote""",
        params,
    )
    return [formatar_item(l) | {"prontuario": l.get("prontuario") or "",
                                "sala": l.get("sala") or "",
                                "id_caixa": l.get("id_caixa") or ""} for l in linhas]


def caixas_pendentes_da_operacao(operacao: str, id_atendimento: str = "",
                                 farmacia: str = "") -> list[dict]:
    """Caixas fechadas aguardando esta etapa, uma linha por caixa.

    A lista de pendentes conta unidades, e está certa em contar: são elas que
    faltam. Mas para quem confere, 43 linhas de uma caixa que ele não vai abrir
    são 43 linhas de ruído. Esta lista dá a mesma informação na unidade em que o
    operador trabalha — a caixa.
    """
    op = OPERACOES.get(operacao)
    if op is None or not op.aceita_caixa:
        return []

    marcadores = ",".join("?" for _ in op.de)
    params: list = list(op.de)
    filtro = ""
    if op.exige_atendimento and not op.define_atendimento:
        filtro += " AND c.id_atendimento = ?"
        params.append(texto(id_atendimento))
    if op.escopo_farmacia and texto(farmacia):
        filtro += " AND c.farmacia = ?"
        params.append(farmacia_valida(farmacia))

    return db.consultar(
        f"""SELECT c.id_caixa, c.nome, c.status, c.especialidade,
                   (SELECT COUNT(*) FROM unidades u WHERE u.id_caixa = c.id_caixa) AS total
            FROM caixas c
            WHERE c.encerrada_em IS NULL
              AND c.status IN ({marcadores}){filtro}
            ORDER BY c.especialidade, c.id_caixa""",
        params,
    )


def contar_elegiveis(operacao: str, farmacia: str = "") -> int:
    """Quantos itens estão na situação exigida por esta operação, no total."""
    op = OPERACOES.get(operacao)
    if op is None:
        return 0
    marcadores = ",".join("?" for _ in op.de)
    filtro_farmacia, params_farmacia = _filtro_farmacia(op, farmacia)
    return db.escalar(
        f"SELECT COUNT(*) FROM unidades u WHERE u.status IN ({marcadores}){filtro_farmacia}",
        [*op.de, *params_farmacia])


def buscar_elegiveis(operacao: str, termo: str, limite: int = 40,
                     farmacia: str = "") -> list[dict]:
    """Busca por código AGHU, descrição, código de barras ou lote.

    Substitui a lista de pendentes nas operações que puxam do estoque inteiro:
    lá não existe conjunto esperado, e listar o estoque todo não ajuda ninguém.
    """
    op = OPERACOES.get(operacao)
    termo = texto(termo)
    if op is None or not termo:
        return []

    marcadores = ",".join("?" for _ in op.de)
    from .. import busca
    # nov/2026: aceita a etiqueta GS1 bipada inteira (ver `busca.condicao`).
    cond, params_busca, etiqueta = busca.condicao(
        termo, ["u.codigo_aghu", "u.xProd", "u.codigo_barras", "u.nLote", "u.numero_serie"])
    filtro_farmacia, params_farmacia = _filtro_farmacia(op, farmacia)
    linhas = db.consultar(
        f"""SELECT {CAMPOS_ITEM}, COUNT(*) OVER (
                     PARTITION BY u.codigo_aghu, u.xProd, u.nLote) AS iguais
            FROM unidades u
            WHERE u.status IN ({marcadores}){filtro_farmacia}
              AND {cond}
            ORDER BY COALESCE(NULLIF(u.codigo_aghu,''),'zzz'), u.xProd,
                     (u.dVal IS NULL OR u.dVal = ''), u.dVal
            LIMIT ?""",
        [*op.de, *params_farmacia, *params_busca, limite],
    )
    linhas = busca.preferir_exatos(busca.refinar(linhas, etiqueta, termo), termo)
    return [formatar_item(l) | {"iguais": l.get("iguais", 1)} for l in linhas]


def concluidos_da_operacao(operacao: str, id_atendimento: str = "", limite: int = 200) -> list[dict]:
    op = OPERACOES.get(operacao)
    if op is None:
        return []
    filtro = " AND e.id_atendimento = ?" if op.exige_atendimento else ""
    params: list = [operacao]
    if op.exige_atendimento:
        params.append(id_atendimento)
    params.append(limite)
    linhas = db.consultar(
        f"""SELECT {CAMPOS_ITEM}, e.data_evento, e.usuario
            FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
            WHERE e.tipo = ?{filtro}
            ORDER BY e.id_evento DESC LIMIT ?""",
        params,
    )
    return [formatar_item(l) | {"quando": l["data_evento"], "usuario": l["usuario"]} for l in linhas]


def finalizar_pendencias(
    *, operacao: str, ids: list[str], usuario: str, motivo: str, destino: str,
) -> tuple[bool, str]:
    """Fecha a etapa tratando o que sobrou (ex.: não chegou, extraviado)."""
    ids = [texto(i) for i in ids if texto(i)]
    if not ids:
        return False, "Selecione ao menos um item."
    if not texto(motivo):
        return False, "Informe o motivo."
    if destino not in ESTADOS:
        return False, "Destino inválido."

    total = 0
    tratados: list[dict] = []
    with db.transacao() as conn:
        for id_unidade in ids:
            atual = conn.execute(
                """SELECT status, id_atendimento, xProd, codigo_aghu, nLote, codigo_barras
                   FROM unidades WHERE id_unidade = ?""",
                (id_unidade,),
            ).fetchone()
            if not atual:
                continue
            # Limpa o vínculo com atendimento quando o material volta ao estoque livre
            novo_atendimento = None if destino in (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO) else atual["id_atendimento"]
            conn.execute(
                """UPDATE unidades SET status = ?, id_atendimento = ?, atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (destino, novo_atendimento, db.agora(), usuario, id_unidade),
            )
            db.registrar_evento(
                conn, tipo=f"{operacao}_pendencia", id_unidade=id_unidade,
                id_atendimento=atual["id_atendimento"], status_anterior=atual["status"],
                status_novo=destino, usuario=usuario, motivo=motivo,
            )
            total += 1
            tratados.append({"id_unidade": id_unidade, **dict(atual)})

    if total and (operacao, destino) in ALERTA_RETORNO:
        # Avisa o módulo de origem: isto é uma devolução, não uma chegada nova,
        # e merece um olhar mais atento — foi por isso que o usuário pediu.
        #
        # O nome do produto sozinho não basta: se houver mais de um lote do
        # mesmo produto em estoque, quem recebe o alerta não sabe qual unidade
        # exata voltou e não consegue tratar. Por isso cada item entra
        # identificado por código AGHU, lote e código de barras.
        modulo_destino, titulo, explicacao = ALERTA_RETORNO[(operacao, destino)]
        linhas_item = [
            f"  · {i['xProd']} — AGHU {i.get('codigo_aghu') or '—'} · "
            f"lote {i.get('nLote') or '—'} · cód. barras {i.get('codigo_barras') or '—'}"
            for i in tratados[:12]
        ]
        if len(tratados) > 12:
            linhas_item.append(f"  · … e mais {len(tratados) - 12} item(ns).")
        alertas.criar(
            modulo_destino=modulo_destino,
            titulo=titulo,
            mensagem=(
                f"{total} material(is) {explicacao}. "
                f"Motivo registrado por {usuario}: “{motivo}”.\n"
                + "\n".join(linhas_item)
            ),
            usuario=usuario,
            ids_unidade=[i["id_unidade"] for i in tratados],
        )

    return True, f"{total} item(ns) tratado(s) como “{rotulo(destino)}”."


# =========================================================
# v17 (out/2026) — seleção manual pelo código AGHU (caso excepcional)
# =========================================================

OPERACOES_SELECAO_MANUAL = ("dispensar_sala", "registrar_uso")
MOTIVOS_SELECAO_MANUAL = ("Etiqueta danificada ou ilegível", "Leitor não lê o código",
                          "Material sem etiqueta", "Outro")


def selecao_manual(operacao: str, aghu: str, id_atendimento: str = "", farmacia: str = "",
                   caixa: str = "") -> list[dict]:
    """Quando não dá para bipar: a pessoa digita o código AGHU e escolhe pelo lote e
    validade. Devolve um grupo por AGHU + lote + validade (+ caixa), com a primeira
    unidade (FEFO) — a escolha passa depois por todas as checagens do bip normal."""
    op = OPERACOES.get(operacao)
    aghu = texto(aghu).strip()
    if op is None or operacao not in OPERACOES_SELECAO_MANUAL or not aghu:
        return []
    marcadores = ",".join("?" for _ in op.de)
    filtro_farmacia, params_farmacia = _filtro_farmacia(op, farmacia)
    # nov/2026: também busca pelo nome — cada palavra digitada precisa aparecer
    # na descrição do hospital ou na do fornecedor (a partir de 3 letras).
    palavras = [p for p in re.split(r"\s+", aghu) if p]
    por_nome, params_nome = "", []
    if len(aghu) >= 3:
        por_nome = " OR (" + " AND ".join(
            "UPPER(COALESCE(u.descritivo_hospital,'') || ' ' || COALESCE(u.xProd,'')) LIKE UPPER(?)"
            for _ in palavras) + ")"
        params_nome = [f"%{p}%" for p in palavras]
    linhas = db.consultar(
        f"""SELECT {CAMPOS_ITEM} FROM unidades u
            WHERE u.status IN ({marcadores}){filtro_farmacia}
              AND (UPPER(TRIM(u.codigo_aghu)) = UPPER(?)
                   OR LTRIM(TRIM(u.codigo_aghu), '0') = LTRIM(?, '0'){por_nome})
              AND NOT EXISTS (SELECT 1 FROM devolucao_itens di JOIN devolucoes dv
                                ON dv.id_devolucao = di.id_devolucao
                              WHERE di.id_unidade = u.id_unidade AND di.situacao = 'pendente'
                                AND dv.status = 'pendente')
            ORDER BY (u.dVal IS NULL OR u.dVal = ''), u.dVal, u.criado_em""",
        [*op.de, *params_farmacia, aghu, aghu, *params_nome])
    id_atendimento = texto(id_atendimento)
    caixa = texto(caixa).strip().upper()
    if operacao == "registrar_uso":
        meus = [l for l in linhas if l["status"] in (TRANSITO_SALA, EM_SALA)
                and texto(l["id_atendimento"]) == id_atendimento]
        if meus:
            linhas = meus  # o que a farmácia dispensou para este paciente vem antes
        else:
            linhas = [l for l in linhas if l["status"] == EM_ESTOQUE_RECEBIMENTO]
        linhas = [l for l in linhas if texto(l["id_caixa"]).upper() == caixa] if caixa else \
                 [l for l in linhas if not texto(l["id_caixa"])]
    else:
        linhas = [l for l in linhas if not texto(l["id_caixa"])]
        if op.barra_vencido:
            linhas = [l for l in linhas if not texto(l["dVal"]) or (dias_para(l["dVal"]) or 0) >= 0]
    grupos: dict[tuple, dict] = {}
    for l in linhas:
        chave = (texto(l["codigo_aghu"]).upper(), gs1.lote_normalizado(l["nLote"]), texto(l["dVal"])[:10],
                 texto(l["id_caixa"]).upper())
        g = grupos.get(chave)
        if g:
            g["quantidade"] += 1
            continue
        grupos[chave] = formatar_item(l) | {
            "descricao": l.get("descritivo_hospital") or l["xProd"] or "", "quantidade": 1,
            "dispensado": l["status"] in (TRANSITO_SALA, EM_SALA)}
    return list(grupos.values())[:40]
