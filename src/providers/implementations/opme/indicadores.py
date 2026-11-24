"""Catálogo de indicadores.

Cada indicador é declarado uma única vez aqui: nome, o que mede, como é
calculado, unidade, se subir é bom ou ruim e a meta padrão sugerida.

As metas ficam no banco (tabela `metas`) e são editáveis pelo administrador —
os valores abaixo são apenas o ponto de partida quando ninguém definiu nada.
Eles refletem prática comum em farmácia hospitalar e devem ser ajustados à
realidade do serviço depois de um ou dois meses de operação.
"""

from dataclasses import dataclass

# Grupos ------------------------------------------------------------------

GRUPOS = {
    "fluxo": ("Fluxo e gargalos", "Onde o processo trava e quanto tempo cada etapa leva."),
    "desperdicio": ("Desperdício e validade", "Quanto do que sai do estoque volta sem ser usado, e o que está prestes a vencer."),
    "financeiro": ("Financeiro e consumo", "Quanto foi consumido, por quem e em quê."),
    "qualidade": ("Qualidade e conformidade", "Correções de cadastro, seleção manual e material sem cadastro."),
}

# Direções ----------------------------------------------------------------

MAIOR_MELHOR = "maior"
MENOR_MELHOR = "menor"
NEUTRO = "neutro"


@dataclass(frozen=True)
class Indicador:
    codigo: str
    nome: str
    grupo: str
    unidade: str            # "h", "%", "R$", "un", "dias"
    direcao: str
    meta: float | None      # verde a partir daqui
    atencao: float | None   # amarelo até aqui; além disso, vermelho
    pergunta: str           # a pergunta de gestão que ele responde
    formula: str            # como é calculado, em português
    por_que: str            # por que acompanhar


CATALOGO: dict[str, Indicador] = {}


def _reg(ind: Indicador) -> Indicador:
    CATALOGO[ind.codigo] = ind
    return ind


# =========================================================
# FLUXO E GARGALOS
# =========================================================

_reg(Indicador(
    "tempo_conferencia_farmacia", "Tempo até a Farmácia conferir", "fluxo", "h", MENOR_MELHOR, 4, 12,
    "Quanto tempo o material fica em trânsito entre o almoxarifado e a conferência da farmácia?",
    "Média das horas entre o evento “Enviar para a Farmácia” e o “Conferir recebimento na Farmácia” da mesma unidade.",
    "Material em trânsito não aparece em nenhum estoque. Quanto maior esse tempo, maior a chance de a farmácia pedir de novo algo que já está a caminho."))

_reg(Indicador(
    "tempo_separacao_envio", "Tempo entre separar e enviar o kit", "fluxo", "h", MENOR_MELHOR, 12, 24,
    "O kit separado fica quanto tempo parado antes de subir para a sala?",
    "Média das horas entre “Separar material para o paciente” e “Enviar kit para a sala”.",
    "Kit separado é estoque reservado que ninguém mais pode usar. Separar cedo demais imobiliza material."))

_reg(Indicador(
    "tempo_conferencia_sala", "Tempo até a sala conferir", "fluxo", "h", MENOR_MELHOR, 2, 6,
    "O kit chega e demora quanto para ser conferido na sala?",
    "Média das horas entre “Enviar kit para a sala” e “Conferir recebimento na sala”.",
    "É o ponto mais crítico: sem conferência o material não pode ser usado, e a equipe só descobre isso no momento da cirurgia."))

_reg(Indicador(
    "tempo_ate_uso", "Tempo entre conferir na sala e usar", "fluxo", "h", NEUTRO, None, None,
    "Quanto tempo o material fica na sala antes de ser implantado?",
    "Média das horas entre “Conferir recebimento na sala” e “Registrar uso no paciente”.",
    "Ajuda a entender se o kit sobe cedo demais. Não tem meta: depende da programação cirúrgica."))

_reg(Indicador(
    "tempo_retorno", "Tempo para o retorno voltar ao estoque", "fluxo", "h", MENOR_MELHOR, 24, 48,
    "O que sobrou da cirurgia demora quanto para voltar a ficar disponível?",
    "Média das horas entre “Devolver não utilizados” e “Conferir retorno do bloco”.",
    "Enquanto o retorno não é conferido, o material não conta como estoque — e pode ser comprado de novo sem necessidade."))

_reg(Indicador(
    "ciclo_total", "Ciclo total: entrada até uso", "fluxo", "dias", NEUTRO, None, None,
    "Do recebimento até o implante, quantos dias se passam?",
    "Média dos dias entre o cadastro da unidade e o registro de uso.",
    "Indicador de giro. Ciclos longos sinalizam compra antecipada demais ou consumo abaixo do previsto."))

_reg(Indicador(
    "itens_parados", "Itens parados em trânsito", "fluxo", "un", MENOR_MELHOR, 0, 5,
    "Quantos itens estão em trânsito há mais tempo do que deveriam, agora?",
    "Contagem de unidades em qualquer estado de trânsito com última movimentação há mais de 48 horas.",
    "É o sintoma clássico da conferência esquecida. Cada item aqui é uma divergência de estoque esperando para acontecer."))

_reg(Indicador(
    "conferencia_no_prazo", "Conferências feitas em até 24 h", "fluxo", "%", MAIOR_MELHOR, 90, 75,
    "Que proporção das conferências acontece no mesmo dia ou no dia seguinte?",
    "Conferências concluídas em até 24 h ÷ total de conferências do período × 100.",
    "Mede a disciplina de conferência das três pontas de uma vez só."))

_reg(Indicador(
    "backlog_atual", "Pendências abertas agora", "fluxo", "un", MENOR_MELHOR, 10, 30,
    "Quantos itens estão esperando alguma ação neste momento?",
    "Soma das unidades em trânsito (para farmácia, para sala, em retorno) e em divergência.",
    "É a fila de trabalho do dia. Serve para dimensionar equipe e turno."))

# =========================================================
# DESPERDÍCIO E VALIDADE
# =========================================================

_reg(Indicador(
    "taxa_aproveitamento", "Aproveitamento do kit", "desperdicio", "%", MAIOR_MELHOR, 70, 50,
    "Do que sobe para a sala, quanto é realmente implantado?",
    "Itens utilizados ÷ (utilizados + devolvidos ao estoque) × 100, no período.",
    "É o indicador central de desperdício de esforço. Aproveitamento baixo significa separar material demais “por garantia”, "
    "o que gera manuseio, risco de dano e imobilização de estoque."))

_reg(Indicador(
    "taxa_devolucao", "Taxa de devolução", "desperdicio", "%", MENOR_MELHOR, 30, 50,
    "Que proporção do que foi à sala voltou sem uso?",
    "Itens devolvidos pelo bloco ÷ total enviado à sala × 100.",
    "Visto por especialidade, aponta quais equipes pedem kit maior do que precisam."))

_reg(Indicador(
    "itens_vencidos", "Itens vencidos em estoque", "desperdicio", "un", MENOR_MELHOR, 0, 5,
    "Quantas unidades já venceram e continuam no estoque?",
    "Contagem de unidades ativas com validade anterior a hoje.",
    "Item vencido em estoque é perda certa e risco assistencial se for usado por engano."))

_reg(Indicador(
    "valor_vencido", "Valor vencido em estoque", "desperdicio", "R$", MENOR_MELHOR, 0, 5000,
    "Quanto dinheiro está parado em material vencido?",
    "Soma do valor unitário das unidades ativas com validade vencida.",
    "Traduz a perda em linguagem de gestão. É o número que justifica revisar a política de compra."))

_reg(Indicador(
    "valor_a_vencer_90", "Valor a vencer em 90 dias", "desperdicio", "R$", MENOR_MELHOR, 5000, 20000,
    "Quanto valor vence nos próximos três meses?",
    "Soma do valor unitário das unidades ativas com validade dentro de 90 dias.",
    "É a janela em que ainda dá para agir: priorizar o consumo, negociar troca com o fornecedor ou remanejar."))

_reg(Indicador(
    "taxa_perda", "Taxa de perda e avaria", "desperdicio", "%", MENOR_MELHOR, 0.5, 2,
    "Que proporção do material é baixada por perda, avaria ou extravio?",
    "Unidades baixadas no período ÷ total de unidades movimentadas × 100.",
    "Perdas repetidas em um mesmo produto costumam indicar problema de embalagem, transporte ou armazenamento."))

_reg(Indicador(
    "separacao_ociosa", "Kits separados sem envio", "desperdicio", "un", MENOR_MELHOR, 0, 10,
    "Quantos itens estão reservados para um paciente há mais de 48 h sem subir?",
    "Contagem de unidades no estado “Separado para o paciente” com mais de 48 h desde a separação.",
    "Podem ser cirurgias adiadas ou canceladas cujo material ninguém devolveu ao estoque."))

_reg(Indicador(
    "estoque_parado", "Estoque sem movimento", "desperdicio", "un", MENOR_MELHOR, 20, 60,
    "Quantas unidades estão há mais de 180 dias sem nenhuma movimentação?",
    "Contagem de unidades ativas cuja última movimentação foi há mais de 180 dias.",
    "Candidatos a devolução ao fornecedor ou remanejamento antes de virarem perda."))

# =========================================================
# FINANCEIRO E CONSUMO
# =========================================================

_reg(Indicador(
    "valor_consumido", "Valor consumido no período", "financeiro", "R$", NEUTRO, None, None,
    "Quanto de OPME foi implantado, em reais?",
    "Soma do valor unitário das unidades com uso registrado no período.",
    "Base para prestação de contas e para comparar com o orçamento previsto."))

_reg(Indicador(
    "custo_medio_cirurgia", "Custo médio de OPME por cirurgia", "financeiro", "R$", NEUTRO, None, None,
    "Quanto custa, em média, o material de uma cirurgia?",
    "Valor consumido ÷ número de atendimentos com pelo menos um item utilizado.",
    "Comparado por especialidade, revela onde o custo por procedimento está fora do padrão."))

_reg(Indicador(
    "itens_por_cirurgia", "Itens por cirurgia", "financeiro", "un", NEUTRO, None, None,
    "Quantos OPMEs, em média, cada cirurgia consome?",
    "Total de itens utilizados ÷ número de atendimentos com consumo.",
    "Ajuda a dimensionar o kit padrão de cada especialidade."))

_reg(Indicador(
    "valor_consignado", "Valor consignado em poder do hospital", "financeiro", "R$", NEUTRO, None, None,
    "Quanto de material de terceiros está sob nossa guarda?",
    "Soma do valor das unidades ativas classificadas como consignado.",
    "É responsabilidade patrimonial do hospital e precisa bater com o controle do fornecedor."))

_reg(Indicador(
    "valor_estoque_total", "Valor total em estoque", "financeiro", "R$", NEUTRO, None, None,
    "Quanto vale todo o OPME parado hoje?",
    "Soma do valor das unidades em qualquer estado ativo.",
    "Capital imobilizado. Acompanhado no tempo, mostra se o estoque está crescendo mais que o consumo."))

_reg(Indicador(
    "giro_estoque", "Cobertura do estoque", "financeiro", "dias", NEUTRO, None, None,
    "Com o consumo atual, o estoque dura quantos dias?",
    "Unidades ativas em estoque ÷ consumo médio diário do período.",
    "Cobertura muito alta imobiliza dinheiro; muito baixa arrisca faltar material na hora da cirurgia."))

# =========================================================
# QUALIDADE E CONFORMIDADE
# =========================================================

_reg(Indicador(
    "taxa_divergencia", "Taxa de divergência na conferência", "qualidade", "%", MENOR_MELHOR, 2, 5,
    "Que proporção das conferências termina em divergência?",
    "Itens marcados como divergência ou tratados como pendência ÷ total conferido × 100.",
    "Divergência recorrente com o mesmo fornecedor ou na mesma etapa aponta falha de processo, não de pessoa."))

_reg(Indicador(
    "completude_cadastro", "Completude do cadastro", "qualidade", "%", MAIOR_MELHOR, 98, 90,
    "Que proporção das unidades tem lote, validade, código AGHU e fabricante preenchidos?",
    "Unidades ativas com os quatro campos preenchidos ÷ total de unidades ativas × 100.",
    "Cadastro incompleto quebra o rastreio na hora do recall — que é justamente quando ninguém tem tempo de investigar."))

_reg(Indicador(
    "rastreabilidade_uso", "Rastreabilidade do implante", "qualidade", "%", MAIOR_MELHOR, 100, 98,
    "Que proporção dos implantes tem lote e validade registrados junto ao prontuário?",
    "Itens utilizados com lote e validade preenchidos ÷ total de itens utilizados × 100.",
    "É a exigência regulatória central da rastreabilidade de OPME. Abaixo de 100% há implante que não se consegue rastrear."))

_reg(Indicador(
    "correcoes_cadastro", "Correções de cadastro", "qualidade", "un", MENOR_MELHOR, 5, 20,
    "Quantas correções manuais foram necessárias no período?",
    "Contagem de eventos do tipo “correção” no período.",
    "Volume alto indica que o dado está entrando errado na origem — normalmente digitação em vez de leitura do código."))

_reg(Indicador(
    "usos_fora_do_fluxo", "Usos fora do fluxo", "qualidade", "un", MENOR_MELHOR, 0, 0,
    "Algum implante foi registrado sem passar por todas as conferências?",
    "Unidades utilizadas sem evento de conferência na sala no histórico.",
    "Precisa ser sempre zero. Qualquer valor acima disso é falha de controle que compromete a auditoria."))


# =========================================================
# APOIO
# =========================================================

def do_grupo(grupo: str) -> list[Indicador]:
    return [i for i in CATALOGO.values() if i.grupo == grupo]


def avaliar(indicador: Indicador, valor: float | None, meta: float | None,
            atencao: float | None) -> str:
    """Devolve 'verde', 'amarelo', 'vermelho' ou 'neutro'."""
    if valor is None or indicador.direcao == NEUTRO or meta is None:
        return "neutro"
    if indicador.direcao == MAIOR_MELHOR:
        if valor >= meta:
            return "verde"
        if atencao is not None and valor >= atencao:
            return "amarelo"
        return "vermelho"
    if valor <= meta:
        return "verde"
    if atencao is not None and valor <= atencao:
        return "amarelo"
    return "vermelho"


def formatar(indicador: Indicador, valor: float | None) -> str:
    if valor is None:
        return "—"
    if indicador.unidade == "R$":
        return f"R$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    if indicador.unidade == "%":
        return f"{valor:.1f}%".replace(".", ",")
    if indicador.unidade in ("h", "dias"):
        return f"{valor:.1f}".replace(".", ",") + (" h" if indicador.unidade == "h" else " dias")
    return f"{valor:,.0f}".replace(",", ".")


# =========================================================
# v17 — FLUXO SEM FARMÁCIA
# =========================================================
# Sem envio à farmácia, kit, conferência na sala nem devolução, estes
# indicadores deixam de ter o que medir. Saem do catálogo (e portanto das telas,
# metas e exportação). O ciclo "entrada até uso" continua e passa a ser o
# principal tempo do fluxo.
REMOVIDOS_V17 = (
    "tempo_conferencia_farmacia", "tempo_separacao_envio", "tempo_conferencia_sala",
    "tempo_ate_uso", "tempo_retorno", "itens_parados", "conferencia_no_prazo",
    "taxa_aproveitamento", "taxa_devolucao", "separacao_ociosa", "taxa_divergencia",
    "usos_fora_do_fluxo",
    # out/2026 — retirados a pedido da gestão.
    "completude_cadastro", "rastreabilidade_uso",
)
for _codigo in REMOVIDOS_V17:
    CATALOGO.pop(_codigo, None)


# v17 — cancelamento/troca de procedimentos previstos.
_reg(Indicador(
    "taxa_cancelamento", "Cancelamento de procedimentos", "fluxo", "%", MENOR_MELHOR, 5, 10,
    "Dos procedimentos previstos com OPME, quantos não aconteceram?",
    "Atendimentos cancelados ÷ atendimentos previstos no período (pela data do procedimento; "
    "previstos = com OPME solicitado, cadastrados à mão ou com material registrado).",
    "Cancelamento e troca de cirurgia desorganizam a sala e o estoque. Pelo motivo dá para "
    "separar o que é clínico do que é falha de processo (material, leito, equipe, agenda)."))


# v17 (out/2026) — uso na sala sem dispensação da farmácia.
_reg(Indicador(
    "taxa_uso_sem_dispensacao", "Uso sem dispensação da farmácia", "fluxo", "%", MENOR_MELHOR, 5, 15,
    "Quanto do OPME usado na sala não passou pela dispensação da farmácia?",
    "Usos registrados sem dispensação prévia ÷ usos registrados no período (pela data do uso; "
    "usos desfeitos ou estornados não entram).",
    "Cada caso é uma saída da farmácia que só ficou registrada no uso. Taxa alta mostra que o "
    "processo de dispensação não está sendo seguido (urgência, material fora do kit, falta de "
    "pessoal) — e cada caso exige ciência da farmácia."))
_reg(Indicador(
    "ciencia_uso_sem_dispensacao", "Ciência da farmácia em até 24 h", "fluxo", "%", MAIOR_MELHOR, 90, 70,
    "A farmácia está dando ciência a tempo dos usos sem dispensação?",
    "Usos sem dispensação com ciência da farmácia em até 24 h ÷ usos sem dispensação no período.",
    "A ciência é a farmácia assumir que aquele material saiu sem passar por ela — é o que permite "
    "repor o estoque, conferir o kit e corrigir a causa."))


# v17 (out/2026) — novos indicadores pedidos pela gestão.
_reg(Indicador(
    "procedimentos_criados", "Procedimentos abertos fora da agenda", "fluxo", "un", NEUTRO, None, None,
    "Quantos procedimentos tiveram de ser abertos à mão, porque não vieram na agenda do AGHU?",
    "Atendimentos com origem “aberto à mão” (Procedimentos → Abrir procedimento), pela data do procedimento.",
    "Muito procedimento aberto à mão indica agenda incompleta ou atrasada — e é onde mais "
    "acontece paciente errado ou duplicado."))
_reg(Indicador(
    "procedimentos_cancelados", "Procedimentos cancelados", "fluxo", "un", MENOR_MELHOR, None, None,
    "Quantos procedimentos previstos com OPME não aconteceram?",
    "Atendimentos cancelados no período (pela data do procedimento). A taxa e os motivos estão em "
    "“Cancelamento de procedimentos”.",
    "O número absoluto mostra o volume de retrabalho: material separado, dispensado e devolvido à toa."))
_reg(Indicador(
    "taxa_utilizacao_dispensado", "Utilização do material dispensado", "desperdicio", "%", MAIOR_MELHOR, 80, 60,
    "Do que a farmácia dispensou para a sala, quanto foi de fato usado no paciente?",
    "Itens dispensados que foram usados no mesmo paciente ÷ itens dispensados no período (pela data "
    "da dispensação; só procedimentos em que a sala já finalizou os utilizados; itens tirados da "
    "dispensação não entram).",
    "Utilização baixa é kit superdimensionado: mais material circulando, mais devolução para conferir "
    "e mais risco de perda, troca de lote e vencimento."))
_reg(Indicador(
    "pendentes_ciencia_farmacia", "Itens aguardando a ciência da farmácia", "fluxo", "un", MENOR_MELHOR, 0, 5,
    "Quanto material está agora esperando a farmácia dar ciência?",
    "Situação de agora (não depende do período): usos sem dispensação ainda sem ciência + itens das "
    "listas de não utilizados ainda sem ciência (caixa conta pelos itens dentro).",
    "Enquanto a farmácia não dá ciência, o estoque não fecha e o procedimento não encerra."))
_reg(Indicador(
    "taxa_selecao_manual", "Seleção manual pelo AGHU (sem bipar)", "qualidade", "%", MENOR_MELHOR, 2, 5,
    "Em quantas leituras não foi possível bipar e o material foi escolhido pelo código AGHU?",
    "Seleções manuais pelo AGHU ÷ (dispensações para a sala + usos registrados) no período.",
    "É uma exceção: cada caso perde a conferência automática do código de barras. Taxa alta aponta "
    "etiqueta ruim, leitor com defeito ou hábito de não bipar."))
_reg(Indicador(
    "materiais_nao_cadastrados", "Material usado sem cadastro", "qualidade", "un", MENOR_MELHOR, 0, 0,
    "Quantas vezes a sala usou material que o almoxarifado não tinha cadastrado?",
    "Unidades registradas na sala como “material não cadastrado” no período (pela data do registro).",
    "É a exceção das exceções: o material entrou no paciente sem passar pela entrada do almoxarifado "
    "(sem NF, sem empenho, sem conferência). A meta é zero — cada caso precisa ser analisado."))
