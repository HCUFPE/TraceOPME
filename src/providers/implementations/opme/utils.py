"""Funções auxiliares de normalização e formatação."""

import re
import unicodedata
import uuid
from datetime import date, datetime


def gerar_id(prefixo: str) -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:12].upper()}"


def texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def inteiro(valor, padrao: int = 0) -> int:
    try:
        return int(float(str(valor).replace(",", ".").strip()))
    except (TypeError, ValueError):
        return padrao


def decimal(valor, padrao: float = 0.0) -> float:
    """Número digitado no formato brasileiro ou vindo do XML da NF-e.

    "4.200,00" e "R$ 4.200,00" → 4200.0 (ponto = milhar quando há vírgula);
    "220,50" → 220.5; "4200.0000" (XML) → 4200.0. Antes, "4.200,00" virava
    4.2 → recusado como valor zero/errado.
    """
    try:
        s = str(valor).replace("R$", "").replace(" ", "").replace("\u00a0", "").strip()
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1:
            s = s.replace(".", "")
        return float(s)
    except (TypeError, ValueError):
        return padrao


def sem_acento(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto(valor))
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def padronizar_unidade(valor) -> str:
    """Unidade/setor (BLOCO CIRURGICO, HEMODINAMICA - PDT): só maiúsculas sem acento."""
    return sem_acento(texto(valor)).upper()


# Nomes padronizados das especialidades. A agenda do AGHU e quem abre o
# procedimento à mão escrevem a mesma especialidade de vários jeitos
# ("CIR GERAL", "CARDIO", "GINECO"); aqui todas viram um nome só, para que
# filtros, indicadores e caixas não se dividam. Chave e valor já em maiúsculas
# sem acento. Para incluir uma abreviação nova, basta acrescentar uma linha.
ESPECIALIDADE_SINONIMOS = {
    "CIR GERAL": "CIRURGIA GERAL",
    "CIRURGIA GERAL": "CIRURGIA GERAL",
    "CG": "CIRURGIA GERAL",
    "CARDIO": "CARDIOLOGIA",
    "CARD": "CARDIOLOGIA",
    "CARD INTERV": "CARDIOLOGIA INTERVENCIONISTA",
    "CARDIO INTERV": "CARDIOLOGIA INTERVENCIONISTA",
    "CARDIOLOGIA INTERV": "CARDIOLOGIA INTERVENCIONISTA",
    "CIR CAR": "CIRURGIA CARDIACA",
    "CIR CARD": "CIRURGIA CARDIACA",
    "CIR CARDIACA": "CIRURGIA CARDIACA",
    "CCP": "CIRURGIA DE CABECA E PESCOCO",
    "CIR CAB PESC": "CIRURGIA DE CABECA E PESCOCO",
    "CABECA E PESCOCO": "CIRURGIA DE CABECA E PESCOCO",
    "CIPE": "CIRURGIA PEDIATRICA",
    "CIR PED": "CIRURGIA PEDIATRICA",
    "CIR PEDIATRICA": "CIRURGIA PEDIATRICA",
    "PLASTICA": "CIRURGIA PLASTICA",
    "CIR PLASTICA": "CIRURGIA PLASTICA",
    "TORACICA": "CIRURGIA TORACICA",
    "CIR TORACICA": "CIRURGIA TORACICA",
    "BARIATRICA": "CIRURGIA BARIATRICA",
    "CIR BARIATRICA": "CIRURGIA BARIATRICA",
    "VASCULAR": "CIRURGIA VASCULAR",
    "CIR VASCULAR": "CIRURGIA VASCULAR",
    "CIR VASC": "CIRURGIA VASCULAR",
    "BUCO": "BUCOMAXILOFACIAL",
    "BUCOMAXILO": "BUCOMAXILOFACIAL",
    "CTBMF": "BUCOMAXILOFACIAL",
    "DERMATO": "DERMATOLOGIA",
    "GINECO": "GINECOLOGIA",
    "GINECO OBSTETRICIA": "GINECOLOGIA E OBSTETRICIA",
    "GO": "GINECOLOGIA E OBSTETRICIA",
    "OBSTETRI": "OBSTETRICIA",
    "OBSTET": "OBSTETRICIA",
    "NEURO": "NEUROLOGIA",
    "NEUROCIRURGIA": "NEUROLOGIA",
    "NEUROCIR": "NEUROLOGIA",
    "OFTALMO": "OFTALMOLOGIA",
    "OFTALMOL": "OFTALMOLOGIA",
    "ONCO": "CIRURGIA ONCOLOGICA",
    "ONCOLOGIA": "CIRURGIA ONCOLOGICA",
    "CIR ONCO": "CIRURGIA ONCOLOGICA",
    "ONCOMASTO": "CIRURGIA ONCOLOGICA",
    "MASTO": "MASTOLOGIA",
    "ORTO": "ORTOPEDIA E TRAUMATOLOGIA",
    "ORTOP": "ORTOPEDIA E TRAUMATOLOGIA",
    "ORTOPEDIA E TRAUMATOLOGIA": "ORTOPEDIA E TRAUMATOLOGIA",
    "ORTOPEDIA": "ORTOPEDIA E TRAUMATOLOGIA",
    "TRAUMATO": "ORTOPEDIA E TRAUMATOLOGIA",
    "ORTOPEDIA TRAUMATOLOGIA": "ORTOPEDIA E TRAUMATOLOGIA",
    "OTORRINO": "OTORRINOLARINGOLOGIA",
    "GASTROPED": "GASTROPEDIATRIA",
    "GASTRO PED": "GASTROPEDIATRIA",
    "GASTROPEDIATRIA": "GASTROPEDIATRIA",
    "ENDOSCOPIA GINECOLOGICA": "ENDOSCOPIA GINECOLOGICA",
    "ENDO GINECO": "ENDOSCOPIA GINECOLOGICA",
    "HISTEROSCOPIA": "ENDOSCOPIA GINECOLOGICA",
    "ELETROFISIOLOGIA": "ELETROFISIOLOGIA",
    "ELETROFISIO": "ELETROFISIOLOGIA",
    "EEF": "ELETROFISIOLOGIA",
    "OTORRINOLARIN": "OTORRINOLARINGOLOGIA",
    "ORL": "OTORRINOLARINGOLOGIA",
    "URO": "UROLOGIA",
    "RADIOINT": "RADIOLOGIA INTERVENCIONISTA",
    "RADIO INT": "RADIOLOGIA INTERVENCIONISTA",
    "RADIO INTERV": "RADIOLOGIA INTERVENCIONISTA",
    "ENDOSCOPIA": "ENDOSCOPIA",
    "ENDO": "ENDOSCOPIA",
    "GASTRO": "GASTROENTEROLOGIA",
    "HEMODINAMICA": "HEMODINAMICA",
    "HEMO": "HEMODINAMICA",
}


def padronizar_especialidade(valor) -> str:
    """Nome padronizado da especialidade ("cir. geral" -> "CIRURGIA GERAL").

    Maiúsculas sem acento, pontuação vira espaço, espaços repetidos somem; depois
    a abreviação é trocada pelo nome completo (ESPECIALIDADE_SINONIMOS). O que não
    está na lista e começa por "CIR " vira "CIRURGIA ...". O resto fica como veio.
    """
    base = sem_acento(texto(valor)).upper()
    base = " ".join(re.sub(r"[.\-_/]+", " ", base).split())
    if not base:
        return ""
    if base in ESPECIALIDADE_SINONIMOS:
        return ESPECIALIDADE_SINONIMOS[base]
    for prefixo in ("CIR ", "CIRUR ", "CIRURG "):
        if base.startswith(prefixo):
            resto = base[len(prefixo):]
            return ESPECIALIDADE_SINONIMOS.get("CIR " + resto, "CIRURGIA " + resto)
    return base


def normalizar_sala(valor) -> str:
    valor = texto(valor)
    return valor.zfill(2) if valor.isdigit() else valor


def normalizar_codigo(valor) -> str:
    """Leitores costumam enviar espaços, tabs e quebras de linha junto do código.

    v17: etiqueta GS1/UDI completa ((01)GTIN(17)validade(10)lote...) vira só o
    GTIN — é por ele que o material está cadastrado (cEAN da NF).
    """
    from .gs1 import codigo_de_busca
    return codigo_de_busca(valor if valor is None else str(valor))


def data_iso(valor) -> str:
    """Converte data em vários formatos para YYYY-MM-DD. Retorna '' se não der."""
    valor = texto(valor)
    if not valor:
        return ""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    valor = valor.split("T")[0].split(" ")[0]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(valor, formato).date().isoformat()
        except ValueError:
            continue
    return ""


def data_br(valor) -> str:
    iso = data_iso(valor)
    if not iso:
        return texto(valor)
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def data_hora_br(valor) -> str:
    valor = texto(valor)
    if not valor:
        return ""
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, formato).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue
    return valor


def hoje_iso() -> str:
    return date.today().isoformat()


def dias_para(valor) -> int | None:
    iso = data_iso(valor)
    if not iso:
        return None
    return (datetime.strptime(iso, "%Y-%m-%d").date() - date.today()).days


# Turnos da agenda cirúrgica, pela hora de início do procedimento.
# O intervalo é [inicio, fim): 12:00 já é tarde, 18:00 já é noite.
TURNOS = {
    "manha": ("Manhã", "00:00", "12:00"),
    "tarde": ("Tarde", "12:00", "18:00"),
    "noite": ("Noite", "18:00", "23:59"),
}


def rotulo_turno(turno: str) -> str:
    dados = TURNOS.get(texto(turno).lower())
    return dados[0] if dados else "Todos os turnos"


def faixa_turno(turno: str) -> tuple[str, str] | None:
    """Hora inicial e final do turno, ou None quando o turno não é reconhecido."""
    dados = TURNOS.get(texto(turno).lower())
    return (dados[1], dados[2]) if dados else None


def moeda(valor) -> str:
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"
