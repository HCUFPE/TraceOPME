"""Configurações do domínio TraceOPME (unidades, farmácias, especialidades...).

Os valores que vêm do ambiente (caminho do banco, trava de login, etc.) são
lidos de ``src/config.py`` — o módulo centralizado de configurações exigido
pelo Framework SETISD. Aqui ficam apenas as regras do domínio.
"""

from ....config import settings

DATA_DIR = settings.OPME_DB_PATH.parent
# OPME_LOG_DIR permite isolar o log em testes e apontá-lo para outro disco em produção.
LOG_DIR = settings.OPME_LOG_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Banco único: elimina o ATTACH entre dois arquivos da versão anterior.
DB_PATH = settings.OPME_DB_PATH

APP_TITLE = "TraceOPME"
APP_SUBTITLE = "Rastreabilidade de OPME — do almoxarifado ao paciente"
ORGANIZACAO = settings.OPME_ORG

# Trava de login: após TENTATIVAS_MAXIMAS erros seguidos, a conta fica
# bloqueada por MINUTOS_BLOQUEIO. Segura ataque de força bruta sem transformar
# um erro de digitação em chamado para o administrador.
TENTATIVAS_MAXIMAS = settings.OPME_TENTATIVAS
MINUTOS_BLOQUEIO = settings.OPME_MINUTOS_BLOQUEIO

# Primeiro acesso: criado apenas se não existir nenhum usuário.
ADMIN_PADRAO = settings.OPME_ADMIN
SENHA_ADMIN_PADRAO = settings.OPME_ADMIN_SENHA

# Unidades funcionais e suas salas.
# A mesma numeração de sala se repete entre unidades — existe "sala 01" no bloco
# cirúrgico, na hemodinâmica, na endoscopia e no centro obstétrico. Por isso a
# sala sozinha não identifica o local: o par unidade + sala é que identifica.
# As chaves são exatamente como vêm do AGHU, para a importação casar sem ajuste.
UNIDADES = {
    "BLOCO CIRURGICO": {
        "rotulo": "Bloco Cirúrgico",
        "salas": [f"{i:02d}" for i in range(1, 11)] + ["12", "17"],
        "usa_opme": True,
        "cor": "azul",
    },
    "HEMODINAMICA - PDT": {
        "rotulo": "Hemodinâmica",
        "salas": ["01"],
        "usa_opme": True,
        "cor": "roxo",
    },
    "CENTRO OBSTETRICO": {
        "rotulo": "Centro Obstétrico",
        "salas": ["01", "02"],
        "usa_opme": False,
        "cor": "cinza",
    },
    "ENDOSCOPIA": {
        "rotulo": "Endoscopia",
        "salas": ["01", "02", "03"],
        "usa_opme": False,
        "cor": "cinza",
    },
    "BLOCO DERMATO": {
        "rotulo": "Bloco Dermatológico",
        "salas": ["01", "02"],
        "usa_opme": False,
        "cor": "cinza",
    },
    "CARDIOLOGIA PDT": {
        "rotulo": "Cardiologia PDT",
        "salas": ["01"],
        "usa_opme": False,
        "cor": "cinza",
    },
}

UNIDADE_PADRAO = "BLOCO CIRURGICO"

# Cada unidade que usa OPME tem a sua própria farmácia satélite, com estoque
# separado: o que está na farmácia do Bloco Cirúrgico não serve a uma cirurgia
# da Hemodinâmica e vice-versa. O almoxarifado escolhe o destino no envio, e a
# farmácia trabalha sempre dentro de uma delas.
FARMACIAS = {
    "BLOCO CIRURGICO": "Farmácia do Bloco Cirúrgico",
    "HEMODINAMICA - PDT": "Farmácia da Hemodinâmica",
}

FARMACIA_PADRAO = "BLOCO CIRURGICO"


def rotulo_farmacia(farmacia: str) -> str:
    return FARMACIAS.get((farmacia or "").strip().upper(), "Farmácia")


def farmacia_da_unidade(unidade: str) -> str:
    """v18.12: farmácia que atende a unidade do procedimento ("" quando não há uma própria)."""
    u = (unidade or "").strip().upper()
    if "HEMODIN" in u:
        return "HEMODINAMICA - PDT"
    if "BLOCO CIR" in u:
        return "BLOCO CIRURGICO"
    return ""


def farmacia_valida(farmacia: str) -> str:
    """Devolve a farmácia informada, ou a padrão quando vier vazia/inválida."""
    chave = (farmacia or "").strip().upper()
    return chave if chave in FARMACIAS else FARMACIA_PADRAO

# Só Bloco Cirúrgico e Hemodinâmica usam OPME. A agenda importada do AGHU traz
# as seis unidades, mas esta aplicação é de rastreabilidade de OPME — não faz
# sentido mostrar cirurgias de unidades que nunca vão movimentar material aqui.
UNIDADES_ATIVAS = {chave: dados for chave, dados in UNIDADES.items() if dados["usa_opme"]}


def rotulo_unidade(unidade: str) -> str:
    dados = UNIDADES.get((unidade or "").strip().upper())
    return dados["rotulo"] if dados else (unidade or "—")


def cor_unidade(unidade: str) -> str:
    dados = UNIDADES.get((unidade or "").strip().upper())
    return dados["cor"] if dados else "cinza"


def salas_da_unidade(unidade: str) -> list[str]:
    dados = UNIDADES.get((unidade or "").strip().upper())
    return dados["salas"] if dados else [f"{i:02d}" for i in range(1, 21)]


def todas_as_salas(apenas_ativas: bool = True) -> list[str]:
    """Números de sala existentes em qualquer unidade, sem repetir."""
    base = UNIDADES_ATIVAS if apenas_ativas else UNIDADES
    numeros = {sala for dados in base.values() for sala in dados["salas"]}
    return sorted(numeros)


def locais(apenas_ativas: bool = True) -> list[tuple[str, str, str]]:
    """Lista (unidade, sala, rótulo) dos locais, para preencher menus."""
    base = UNIDADES_ATIVAS if apenas_ativas else UNIDADES
    return [
        (chave, sala, f"{dados['rotulo']} — Sala {sala}")
        for chave, dados in base.items()
        for sala in dados["salas"]
    ]

# Especialidades do hospital (out/2026), na ordem da tela do hospital.
# (valor gravado — maiúsculas sem acento —, nome mostrado na tela)
ESPECIALIDADES_HOSPITAL = [
    ("ORTOPEDIA E TRAUMATOLOGIA", "Ortopedia e Traumatologia"),
    ("CIRURGIA GERAL", "Cirurgia Geral"),
    ("OTORRINOLARINGOLOGIA", "Otorrino"),
    ("CIRURGIA PLASTICA", "Cirurgia Plástica"),
    ("CIRURGIA TORACICA", "Cirurgia Torácica"),
    ("CIRURGIA ONCOLOGICA", "Cirurgia Oncológica"),
    ("NEUROLOGIA", "Neurologia"),
    ("ENDOSCOPIA", "Endoscopia"),
    ("GASTROPEDIATRIA", "Gastropediatria"),
    ("CIRURGIA VASCULAR", "Cirurgia Vascular"),
    ("CIRURGIA CARDIACA", "Cirurgia Cardíaca"),
    ("CARDIOLOGIA INTERVENCIONISTA", "Cardiologia Intervencionista"),
    ("RADIOLOGIA INTERVENCIONISTA", "Radiologia Intervencionista"),
    ("OFTALMOLOGIA", "Oftalmologia"),
    ("GINECOLOGIA", "Ginecologia"),
    ("UROLOGIA", "Urologia"),
    ("ENDOSCOPIA GINECOLOGICA", "Endoscopia Ginecológica"),
    ("ELETROFISIOLOGIA", "Eletrofisiologia"),
]
ESPECIALIDADES_PADRAO = [valor for valor, _ in ESPECIALIDADES_HOSPITAL]
ROTULO_ESPECIALIDADE = dict(ESPECIALIDADES_HOSPITAL)

# Dias de antecedência para alertar validade próxima no painel.
DIAS_ALERTA_VALIDADE = settings.OPME_DIAS_VALIDADE

# Percentual do saldo de um empenho consignado usado a partir do qual um alerta
# antecipado é disparado (antes de esgotar de vez). 0.8 = avisa aos 80% usado.
LIMIAR_ALERTA_EMPENHO = settings.OPME_LIMIAR_EMPENHO


# Grade das caixas (a composição esperada: "esta caixa deve ter 6 parafusos
# AGHU-101"). DESLIGADA enquanto a composição das caixas não for fixa: sem
# grade, a caixa é só o que foi bipado para dentro dela.
#
# Desligar vale para a lógica, não só para a tela: com a grade desligada não há
# "faltando", nem lista de reposição, nem alerta de reposição ao almoxarifado —
# mesmo que exista grade gravada no banco. Nada é apagado: as tabelas e o
# histórico continuam lá, e para religar basta definir OPME_GRADE_CAIXAS=1.
GRADE_DAS_CAIXAS = settings.OPME_GRADE_CAIXAS


# v17 — motivos de cancelamento de procedimento (o que não aconteceu na agenda).
# A lista alimenta o indicador de cancelamento/troca de cirurgias; "Outro" exige
# descrição. Para mudar, edite aqui e reinicie a aplicação.
MOTIVOS_CANCELAMENTO = [
    "Paciente sem condição clínica",
    "Paciente não compareceu / não internou",
    "Exames ou pré-operatório incompletos",
    "Falta de leito / UTI",
    "Falta de material / OPME",
    "Falta de equipe (cirurgião, anestesista, enfermagem)",
    "Sala ou equipamento indisponível",
    "Tempo cirúrgico excedido / horário esgotado",
    "Troca ou remanejamento na agenda",
    "Paciente desistiu / não autorizou",
    "Outro",
]
