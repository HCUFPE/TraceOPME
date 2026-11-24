"""Regras de domínio: estados de uma unidade de OPME e transições permitidas.

Esta é a peça central da versão 14. Na versão anterior o "onde está o item"
ficava espalhado entre `unidades.status_estoque`, `transferencias_opme`,
`farmacia_dispensas`, `farmacia_devolucoes` e `rastreio_uso` (em outro banco),
o que obrigava consultas de 5 vias e permitia estados contraditórios.

Aqui cada unidade tem UM status. Toda mudança passa por `aplicar_transicao`,
que valida a transição e grava um evento imutável na tabela `eventos`.
"""

from dataclasses import dataclass

# =========================================================
# ESTADOS
# =========================================================

EM_ESTOQUE_RECEBIMENTO = "em_estoque_recebimento"
TRANSITO_FARMACIA = "transito_farmacia"
# nov/2026: devolução da farmácia para o almoxarifado (aguardando a ciência do almoxarifado).
TRANSITO_ALMOX = "transito_almoxarifado"
EM_ESTOQUE_FARMACIA = "em_estoque_farmacia"
SEPARADO = "separado"
TRANSITO_SALA = "transito_sala"
EM_SALA = "em_sala"
UTILIZADO = "utilizado"
TRANSITO_RETORNO = "transito_retorno"
DIVERGENCIA = "divergencia"
DEVOLVIDO_FORNECEDOR = "devolvido_fornecedor"
# v18.14: dispensação para OUTROS PROCEDIMENTOS — o material sai do estoque (da
# farmácia ou do almoxarifado) para um procedimento fora do fluxo de sala/paciente
# (ambulatório, outro setor, outro serviço). Saída definitiva: o uso nesses lugares
# não é acompanhado item a item por aqui, só fica o registro de quem levou e para quê.
SAIDA_OUTROS = "saida_outros"
BAIXADO = "baixado"
# v18.4.3: a sala informou que não recebeu — fica fora do estoque disponível até a
# farmácia localizar fisicamente (volta ao estoque) ou registrar o extravio.
NAO_RECEBIDO = "nao_recebido_conferir"


@dataclass(frozen=True)
class Estado:
    codigo: str
    rotulo: str
    local: str
    descricao: str
    cor: str
    final: bool = False


ESTADOS: dict[str, Estado] = {
    EM_ESTOQUE_RECEBIMENTO: Estado(
        EM_ESTOQUE_RECEBIMENTO, "Em estoque — Almoxarifado", "Almoxarifado",
        "Item conferido na entrada, disponível no almoxarifado.", "azul"),
    TRANSITO_FARMACIA: Estado(
        TRANSITO_FARMACIA, "Em trânsito para a Farmácia", "Trânsito",
        "Enviado pelo Recebimento, aguardando conferência da Farmácia.", "amarelo"),
    TRANSITO_ALMOX: Estado(
        TRANSITO_ALMOX, "Em devolução para o Almoxarifado", "Trânsito",
        "Devolvido pela farmácia, aguardando a ciência do almoxarifado.", "amarelo"),
    EM_ESTOQUE_FARMACIA: Estado(
        EM_ESTOQUE_FARMACIA, "Em estoque — Farmácia", "Farmácia",
        "Disponível no estoque da farmácia (Bloco Cirúrgico ou Hemodinâmica).", "azul"),
    SEPARADO: Estado(
        SEPARADO, "Separado para o paciente", "Farmácia",
        "Reservado para um atendimento, ainda na farmácia.", "roxo"),
    TRANSITO_SALA: Estado(
        TRANSITO_SALA, "Dispensado — aguardando a sala", "Trânsito",
        "Dispensado pela farmácia para o paciente; falta a sala dar ciência do recebimento.", "amarelo"),
    EM_SALA: Estado(
        EM_SALA, "Na sala (dispensado)", "Sala",
        "Recebido pela sala (ciência do usuário logado), liberado para uso no paciente.", "verde"),
    UTILIZADO: Estado(
        UTILIZADO, "Utilizado no paciente", "Sala",
        "Uso registrado e vinculado ao prontuário.", "verde", final=True),
    TRANSITO_RETORNO: Estado(
        TRANSITO_RETORNO, "Retornando para a Farmácia", "Trânsito",
        "Não utilizado, devolvido pelo bloco e aguardando conferência.", "amarelo"),
    NAO_RECEBIDO: Estado(
        NAO_RECEBIDO, "Não recebido — aguardando conferência da farmácia", "Pendência",
        "A sala informou que não recebeu. Fora do estoque disponível até a farmácia localizar o material.",
        "vermelho"),
    DIVERGENCIA: Estado(
        DIVERGENCIA, "Em divergência", "Pendência",
        "Conferência apontou problema. Precisa de tratativa.", "vermelho"),
    DEVOLVIDO_FORNECEDOR: Estado(
        DEVOLVIDO_FORNECEDOR, "Devolvido ao fornecedor", "Saída",
        "Item devolvido, fora do estoque.", "cinza", final=True),
    SAIDA_OUTROS: Estado(
        SAIDA_OUTROS, "Dispensado para outro procedimento", "Saída",
        "Saiu do estoque para um procedimento fora do fluxo de sala/paciente. "
        "Fica o registro de quem retirou, para onde foi e a justificativa.", "cinza", final=True),
    BAIXADO: Estado(
        BAIXADO, "Baixado", "Saída",
        "Item baixado por perda, avaria ou correção.", "cinza", final=True),
}

ESTOQUE_ATIVO = (
    EM_ESTOQUE_RECEBIMENTO, TRANSITO_FARMACIA, TRANSITO_ALMOX, EM_ESTOQUE_FARMACIA,
    SEPARADO, TRANSITO_SALA, EM_SALA, TRANSITO_RETORNO, DIVERGENCIA, NAO_RECEBIDO,
)
# Estoque "parado", disponível: o do almoxarifado e o de cada farmácia (out/2026:
# o almoxarifado envia para a farmácia do Bloco ou da Hemodinâmica, e a farmácia
# só dispensa para a sala o que está no estoque dela).
ESTOQUE_LIVRE = (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA)

# Ao voltar sem uso (devolução, cancelamento, item tirado da dispensação): para o
# estoque da farmácia a que o item pertence; item sem farmácia volta ao almoxarifado.
SQL_ESTOQUE_DE_VOLTA = ("CASE WHEN COALESCE(farmacia,'') <> '' THEN 'em_estoque_farmacia' "
                        "ELSE 'em_estoque_recebimento' END")


def estoque_de_volta(farmacia) -> str:
    return EM_ESTOQUE_FARMACIA if (farmacia or "").strip() else EM_ESTOQUE_RECEBIMENTO

# =========================================================
# OPERAÇÕES (cada tela de bipagem é uma operação)
# =========================================================


@dataclass(frozen=True)
class Operacao:
    codigo: str
    titulo: str
    modulo: str
    de: tuple[str, ...]
    para: str
    verbo: str
    ajuda: str
    exige_atendimento: bool = False
    limpa_atendimento: bool = False
    define_atendimento: bool = False
    # Existem duas farmácias satélites com estoques separados (Bloco Cirúrgico e
    # Hemodinâmica). `define_farmacia` marca a operação em que o almoxarifado
    # escolhe o destino; `escopo_farmacia` marca as operações que só enxergam o
    # material de uma farmácia por vez — sem isso, uma farmácia bipava material
    # que pertence à outra.
    define_farmacia: bool = False
    escopo_farmacia: bool = False
    # Etapas que empurram o material em direção ao paciente. Material vencido
    # não pode avançar por elas — é aqui que o vencimento tem que ser barrado,
    # enquanto ainda dá tempo de trocar. Ver `fluxo._conferir_validade`.
    barra_vencido: bool = False
    # A lista "ainda pendente" só faz sentido quando existe um conjunto esperado:
    # alguém enviou uma remessa e o que não for bipado é pendência de verdade.
    # Em operações que puxam do estoque inteiro (enviar à farmácia, devolver ao
    # fornecedor, baixar), não há conjunto esperado — a lista seria o estoque
    # todo, inútil e enganosa. Nesses casos usamos busca em vez de lista.
    mostra_pendentes: bool = True
    # Etapas em que faz sentido bipar a CAIXA inteira em vez de item por item.
    # O almoxarifado monta uma caixa de ortopedia com 40+ itens; do envio até o
    # retorno ninguém abre essa caixa — a unidade de trabalho real é ela, não o
    # item. `registrar_uso` fica de fora de propósito: é ali que a caixa se abre,
    # e é o único momento em que o item individual importa, porque é ele que vai
    # para o prontuário.
    aceita_caixa: bool = False
    # Entrega conferida na hora: quem entrega bipa na frente de quem recebe, e
    # quem recebe confirma com a própria senha — em vez de uma segunda bipagem
    # de conferência feita depois, sem ninguém junto. Vale nos dois sentidos: a
    # farmácia dispensa e a sala confirma o recebimento; a sala devolve e a
    # farmácia confirma o retorno. Ver `fluxo.bipar`: ao confirmar, a mesma
    # leitura já encadeia a conferência (`confirmacao_encadeia`), creditada a
    # quem digitou a senha, não a quem operou o leitor.
    confirmacao_papel: str = ""     # papel exigido de quem confirma
    confirmacao_encadeia: str = ""  # operação aplicada na sequência
    confirmacao_quem: str = ""      # como chamar essa pessoa na tela
    confirmacao_aviso: str = ""     # explicação mostrada acima dos campos
    # v17: a operação fica registrada no atendimento (evento), sem prender a
    # unidade a ele — usada na devolução do que não foi utilizado, em que o
    # material continua sendo estoque do almoxarifado.
    registra_atendimento: bool = False


# Texto que a tela de bipagem mostra acima dos campos de confirmação. Fica aqui,
# junto da operação, porque é a operação que sabe quem confirma o quê.
AVISO_CONFIRMACAO_SALA = (
    "Bipe na frente do responsável da sala: ele(a) digita o próprio usuário e "
    "senha aqui antes da primeira leitura, confirmando que está recebendo o "
    "material. O item já vai direto para “Na sala” (conferido), sem bipagem de "
    "conferência separada depois."
)
AVISO_CONFIRMACAO_RETORNO = (
    "Bipe na frente do farmacêutico que está recebendo de volta: ele(a) digita o "
    "próprio usuário e senha aqui antes da primeira leitura, confirmando o "
    "retorno. O material já volta direto ao estoque da farmácia, sem bipagem de "
    "conferência separada depois."
)

OPERACOES: dict[str, Operacao] = {
    # Versão 17 — fluxo sem farmácia: o almoxarifado cadastra (NF ou manual) e
    # guarda o material; não há mais envio à farmácia, kit, dispensação para a
    # sala nem devolução de sobra. A única movimentação em direção ao paciente é
    # a bipagem do uso, feita na sala de procedimento, direto do estoque do
    # almoxarifado. Os estados antigos (farmácia, trânsito, sala) continuam
    # definidos acima só para o histórico e as consultas não quebrarem.
    # v17 (out/2026): dispensação da farmácia para a sala, por paciente. A
    # farmácia bipa; o operador da sala confirma só com a senha (em trânsito →
    # na sala). Ver `services/dispensacoes.py`.
    "dispensar_sala": Operacao(
        "dispensar_sala", "Dispensar para a sala", "farmacia",
        (EM_ESTOQUE_FARMACIA,), TRANSITO_SALA, "dispensado para a sala",
        "Bipe o OPME separado para este paciente (ou o código da caixa de consignado). "
        "No fim, o operador da sala confirma o recebimento com a própria senha — "
        "não precisa bipar de novo.",
        exige_atendimento=True, define_atendimento=True, barra_vencido=True,
        mostra_pendentes=False, escopo_farmacia=True),
    "registrar_uso": Operacao(
        "registrar_uso", "Registrar uso no paciente", "sala-procedimento",
        (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA, TRANSITO_SALA, EM_SALA), UTILIZADO, "registrado como utilizado",
        "Bipe o material no momento do uso. Ele fica vinculado ao prontuário deste "
        "atendimento — de preferência o que a farmácia dispensou para este paciente.",
        exige_atendimento=True, define_atendimento=True, mostra_pendentes=False),
    "devolver_nao_utilizado": Operacao(
        "devolver_nao_utilizado", "Devolver não utilizados", "sala-procedimento",
        (EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_FARMACIA, TRANSITO_SALA, EM_SALA), EM_ESTOQUE_RECEBIMENTO, "devolvido à farmácia",
        "Bipe o que voltou sem uso — aqui na sala ou na porta da farmácia. Depois, "
        "a farmácia confirma o recebimento com a própria senha: nesta tela, se "
        "estiver junto, ou mais tarde em Farmácia → Devoluções a confirmar.",
        exige_atendimento=True, registra_atendimento=True, mostra_pendentes=False),
    "devolver_fornecedor": Operacao(
        "devolver_fornecedor", "Devolver ao fornecedor", "almoxarifado",
        (EM_ESTOQUE_RECEBIMENTO, DIVERGENCIA), DEVOLVIDO_FORNECEDOR, "devolvido ao fornecedor",
        "Bipe os itens que voltam para o fornecedor.", mostra_pendentes=False),
    "baixar": Operacao(
        "baixar", "Baixar item", "almoxarifado",
        ESTOQUE_ATIVO, BAIXADO, "baixado",
        "Baixa por perda, avaria ou correção de cadastro. Exige motivo.",
        mostra_pendentes=False),
    # v18.14 — dispensação para outros procedimentos (farmácia e almoxarifado).
    # Sem atendimento e sem paciente: o material sai do estoque e o acompanhamento
    # do uso não é feito por aqui. O motivo (para onde/para quê) é obrigatório.
    "saida_outros": Operacao(
        "saida_outros", "Dispensar para outros procedimentos", "farmacia",
        (EM_ESTOQUE_FARMACIA,), SAIDA_OUTROS, "dispensado para outro procedimento",
        "Bipe o que está saindo do estoque da farmácia para um procedimento fora do fluxo de "
        "sala/paciente. Informe o destino (setor/procedimento) e quem está levando: o item sai "
        "do estoque e o uso não é acompanhado item a item por aqui.",
        barra_vencido=True, mostra_pendentes=False, escopo_farmacia=True),
    "saida_outros_almox": Operacao(
        "saida_outros_almox", "Dispensar para outros procedimentos", "almoxarifado",
        (EM_ESTOQUE_RECEBIMENTO,), SAIDA_OUTROS, "dispensado para outro procedimento",
        "Bipe o que está saindo do estoque do almoxarifado para um procedimento fora do fluxo de "
        "sala/paciente. Informe o destino (setor/procedimento) e quem está levando: o item sai "
        "do estoque e o uso não é acompanhado item a item por aqui.",
        barra_vencido=True, mostra_pendentes=False),
    "marcar_divergencia": Operacao(
        "marcar_divergencia", "Registrar divergência", "almoxarifado",
        ESTOQUE_ATIVO, DIVERGENCIA, "marcado como divergente",
        "Registra uma pendência sobre o item. Exige motivo.", mostra_pendentes=False),
}


# Operações recusadas quando o lote está bloqueado por recall: todas as que
# empurram o material adiante. As demais — conferir o que chegou, devolver,
# baixar, estornar — continuam liberadas, porque são justamente o caminho para
# tirar o lote de circulação.
#
# `registrar_uso` fica de fora de propósito: ele descreve algo que já aconteceu
# no paciente. Recusar não desimplanta nada, só apagaria o rastro — e num
# recall o rastro é a única coisa que importa. Lá o uso passa com justificativa
# obrigatória, como no material vencido.
BLOQUEADAS_POR_RECALL: tuple[str, ...] = ("dispensar_sala", "saida_outros", "saida_outros_almox")


def operacoes_do_modulo(modulo: str) -> list[Operacao]:
    return [o for o in OPERACOES.values() if o.modulo == modulo]


def rotulo(status: str) -> str:
    estado = ESTADOS.get(status)
    return estado.rotulo if estado else (status or "—")


def local_de(status: str) -> str:
    estado = ESTADOS.get(status)
    return estado.local if estado else "—"


def cor_de(status: str) -> str:
    estado = ESTADOS.get(status)
    return estado.cor if estado else "cinza"


def explicar_recusa(operacao: Operacao, status_atual: str) -> str:
    """Mensagem clara para o operador quando o item não pode receber a operação."""
    atual = rotulo(status_atual)
    esperados = " ou ".join(rotulo(s) for s in operacao.de)

    if status_atual == UTILIZADO and operacao.codigo == "devolver_nao_utilizado":
        return ("Este item está registrado como UTILIZADO no paciente, então não pode "
                "ser devolvido. Se ele voltou sem uso, o bip de uso foi um engano: "
                "exclua-o em “Concluir bipagem” (ou estorne o uso) e bipe a devolução de novo.")
    if status_atual == UTILIZADO:
        return ("Este item já foi registrado como utilizado em um paciente "
                "e não pode ser movimentado novamente.")
    if operacao.codigo == "dispensar_sala" and status_atual == EM_ESTOQUE_RECEBIMENTO:
        return ("Este material ainda está no estoque do ALMOXARIFADO. A farmácia só dispensa o que "
                "está no estoque dela: peça ao almoxarifado o envio para a farmácia (e dê ciência).")
    if operacao.codigo == "dispensar_sala" and status_atual == TRANSITO_FARMACIA:
        return ("Este material foi enviado pelo almoxarifado e ainda não teve a ciência da farmácia. "
                "Confira o envio em Farmácia → Receber do almoxarifado antes de dispensar.")
    if status_atual == SAIDA_OUTROS:
        return ("Este item já foi dispensado para outro procedimento e saiu do estoque. "
                "Se foi engano, registre a correção no almoxarifado.")
    if status_atual in (DEVOLVIDO_FORNECEDOR, BAIXADO):
        return f"Este item saiu do estoque ({atual}) e não pode ser movimentado."
    if status_atual == operacao.para:
        return f"Este item já está como “{atual}”. Nada a fazer."
    return f"Situação atual: “{atual}”. Para esta operação o item precisa estar como “{esperados}”."
