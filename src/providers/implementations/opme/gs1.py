"""v17 — leitura de etiquetas GS1 (UDI) das embalagens de OPME.

O código de barras da embalagem não é só o GTIN. Na etiqueta UDI (GS1-128 ou
DataMatrix) vêm vários campos em sequência, cada um com um prefixo entre
parênteses — o "identificador de aplicação" (AI):

    (01)08714729789802 (17)280624 (10)39671573
     └ GTIN do produto  └ validade └ lote

O leitor manda tudo junto: 0108714729789802172806241039671573. A NF-e traz só
o GTIN (campo cEAN), às vezes sem os zeros à esquerda (763000726591 é o mesmo
produto que 00763000726591). Este módulo:

* separa o GTIN do resto, para a leitura achar o material cadastrado pelo cEAN
  da NF — sem ninguém precisar bipar no cadastro;
* compara GTINs com qualquer quantidade de zeros à esquerda (8, 12, 13 ou 14
  dígitos);
* usa o lote, a validade e a série da etiqueta para escolher a unidade certa
  sozinho, em vez de perguntar.
"""

import re
from datetime import date, timedelta

GS = "\x1d"  # separador de campo que alguns leitores enviam entre AIs variáveis

# AI → tamanho fixo
FIXOS = {"00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6,
         "17": 6, "20": 2, "4326": 6, "7003": 10}
# AI → tamanho máximo (terminam no separador ou no fim)
VARIAVEIS = {"10": 20, "21": 20, "22": 20, "30": 8, "37": 8, "235": 28, "240": 30,
             "241": 30, "242": 6, "250": 30, "251": 30, "253": 30, "254": 20,
             "7020": 20, "7021": 20, "7240": 20, "8003": 30, "8004": 30,
             "90": 30, "91": 90, "92": 90, "93": 90, "94": 90, "95": 90, "96": 90,
             "97": 90, "98": 90, "99": 90}
NUMERICOS = {"30", "37"}  # variáveis só com dígitos
PREFIXOS_SIMBOLOGIA = ("]C1", "]d2", "]Q3", "]e0", "]J1")


def gtin(valor) -> str:
    """Forma única de comparar códigos: GTIN numérico vira 14 dígitos.

    Registrado no SQLite como função `gtin()`: as consultas comparam
    `gtin(u.codigo_barras) = gtin(?)`. Códigos que não são GTIN (QR interno,
    códigos com letras) voltam só sem espaços.
    """
    if valor is None:
        return ""
    s = re.sub(r"\s+", "", str(valor))
    if s.isdigit() and 8 <= len(s) <= 14:
        return s.zfill(14)
    # v18.43.1: cadastro que guardou a ETIQUETA INTEIRA no campo do código.
    # Aconteceu com as próteses valvulares e as gastrostomias: o campo tem
    # "(01)7898716350358(17)300126(10)260126(21)561193...", e bipar a etiqueta
    # dava "MATERIAL NÃO CADASTRADO", porque a comparação era com o texto todo.
    # Como esta função é a forma de comparar código em todas as telas, ler o
    # GTIN de dentro da etiqueta conserta bipagem, busca, envio e devolução de
    # uma vez — sem mexer no cadastro.
    if len(s) > 14 and (s.startswith("(01)") or s.startswith("01")):
        lido = interpretar(s)
        if lido and lido.get("gtin"):
            return str(lido["gtin"]).zfill(14)
    # v18.43.4: código que não é número compara sem diferenciar maiúscula de
    # minúscula. Caso real (HC-UFPE, 23/11/2026): o CATETER MIKAELSON tinha 6
    # unidades cadastradas como "...75825071214x" e 1, já utilizada, como
    # "...75825071214X". Bipando a etiqueta (com X maiúsculo), só a utilizada
    # casava, e a tela dizia "JÁ REGISTRADO" com 6 disponíveis na farmácia.
    return s.upper()


def _data(yymmdd: str) -> str:
    if not re.fullmatch(r"\d{6}", yymmdd or ""):
        return ""
    ano, mes, dia = 2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    try:
        if dia == 0:  # "00" = último dia do mês
            proximo = date(ano + (mes == 12), mes % 12 + 1, 1)
            return (proximo - timedelta(days=1)).isoformat()
        return date(ano, mes, dia).isoformat()
    except ValueError:
        return ""


def _campos_com_parenteses(s: str) -> list[tuple[str, str, bool]]:
    return [(ai, valor.strip(), False) for ai, valor in re.findall(r"\((\d{2,4})\)([^(]*)", s)]


def _comeca_campo_valido(resto: str) -> bool:
    """`resto` começa por um campo GS1 plausível?

    Um campo de tamanho fixo só vale se vier completo e só com dígitos. Sem isso,
    em 30 01 21 S0000002545 (quantidade 01 + série S0000002545) a quantidade era
    cortada em "0" e o "01..." seguinte virava um GTIN falso — e a série se perdia.
    """
    for k in (2, 3, 4):
        ai = resto[:k]
        if ai in FIXOS:
            valor = resto[k:k + FIXOS[ai]]
            if len(valor) == FIXOS[ai] and valor.isdigit():
                return True
        elif ai in VARIAVEIS and len(resto) > k:
            return True
    return False


def _sequencia_completa(resto: str) -> bool:
    """`resto` é uma sequência de campos GS1 inteira, sem sobra e com datas válidas?"""
    if not _comeca_campo_valido(resto):
        return False
    i = 0
    while i < len(resto):
        ai = next((resto[i:i + n] for n in (2, 3, 4)
                   if resto[i:i + n] in FIXOS or resto[i:i + n] in VARIAVEIS), None)
        if ai is None:
            return False
        i += len(ai)
        if ai in FIXOS:
            valor = resto[i:i + FIXOS[ai]]
            if len(valor) != FIXOS[ai] or not valor.isdigit():
                return False
            if ai in ("11", "12", "13", "15", "16", "17") and not _data(valor):
                return False
            i += FIXOS[ai]
        else:
            fim = resto.find(GS, i)
            i = len(resto) if fim == -1 else fim + 1
    return True


# Só estes campos podem vir colados DEPOIS do lote/série numa etiqueta sem
# separador. A lista é curta de propósito: um AI de tamanho variável (240, 250,
# 90...) aceitaria qualquer sobra e cortaria o lote no meio.
AIS_DEPOIS_DO_LOTE = ("17", "11", "15", "13", "21", "30", "01", "02")
MINIMO_DO_LOTE = 4


def _leitura_partida(lote: str) -> dict:
    """v18.17: segunda leitura do lote que foi "até o fim" da etiqueta.

    O lote (AI 10) tem tamanho variável e termina no separador FNC1. Muitos
    leitores não mandam esse separador, então o lote engole o campo seguinte:
    `10 SP1124082036` + `17 270904` chega como `SP112408203617270904`, que não
    existe em cadastro nenhum — e a busca caía no GTIN, trazendo todos os lotes
    do produto.

    Aqui não se escolhe entre as duas leituras: devolve-se a alternativa
    (`lote_curto` + a validade que vinha colada) e quem procura tenta primeiro o
    lote inteiro e depois o curto. Assim um lote que de fato termina em números
    de data (9686013291005) continua sendo achado inteiro.
    """
    candidatos = []
    for corte in range(len(lote) - 1, MINIMO_DO_LOTE - 1, -1):
        resto = lote[corte:]
        if resto.startswith(AIS_DEPOIS_DO_LOTE) and _sequencia_completa(resto):
            campos = {ai: valor for ai, valor, _ in _campos_em_sequencia(resto)}
            candidatos.append({"lote_curto": lote[:corte],
                               "validade_do_lote": _data(campos.get("17", "")),
                               "_campos": len(campos), "_resto": len(resto)})
    if not candidatos:
        return {}
    # v18.25: havendo mais de um corte possível, fica com o que revela uma
    # validade. `SP102502270817280302` tanto podia ser lote + quantidade "302"
    # quanto lote SP1025022708 + validade 02/03/2028 — e é a validade que
    # confere com o cadastro.
    #
    # v18.43.3: entre os cortes restantes, fica com o que explica MAIS campos da
    # etiqueta. Sem isso, a etiqueta da prótese valvular lida sem parênteses
    # (`...10 260126 21 561193 11 260126`) cortava em "11" e dava lote
    # "26012621561193"; cortando em "21" sai o lote certo, 260126, e ainda se
    # lê o número de série. O lote inteiro continua sendo tentado primeiro, então
    # lote que de fato termina em números (9686013291005) não se perde.
    melhor = max(candidatos,
                 key=lambda c: (bool(c["validade_do_lote"]), c["_campos"], c["_resto"]))
    return {"lote_curto": melhor["lote_curto"], "validade_do_lote": melhor["validade_do_lote"]}


def _campos_em_sequencia(s: str) -> list[tuple[str, str, bool]]:
    """(AI, valor, foi_ate_o_fim_sem_separador)."""
    campos, i = [], 0
    while i < len(s):
        if s[i] == GS:
            i += 1
            continue
        ai = next((s[i:i + n] for n in (2, 3, 4)
                   if s[i:i + n] in FIXOS or s[i:i + n] in VARIAVEIS), None)
        if ai is None:
            break
        i += len(ai)
        if ai in FIXOS:
            valor = s[i:i + FIXOS[ai]]
            i += FIXOS[ai]
            campos.append((ai, valor, False))
        else:
            fim = s.find(GS, i)
            ate_o_fim = fim == -1
            fim = len(s) if ate_o_fim else fim
            if ate_o_fim and ai in NUMERICOS:
                # Quantidade (30) etc. sem separador: é só dígitos e termina onde
                # começa o próximo campo — ex.: 30 05 10 C08240A1.
                for n in range(1, min(VARIAVEIS[ai], len(s) - i) + 1):
                    trecho, resto = s[i:i + n], s[i + n:]
                    if trecho.isdigit() and _comeca_campo_valido(resto):
                        fim, ate_o_fim = i + n, False
                        break
            valor = s[i:fim] if ate_o_fim else s[i:min(fim, i + VARIAVEIS[ai])]
            # v18.24: sem separador, o valor passa do tamanho máximo do AI porque
            # engoliu os campos seguintes. Cortar em 20 aqui perdia justamente o
            # fim da etiqueta e a segunda leitura do lote não fechava — foi o que
            # aconteceu com `10 SP11250314005` + `17 280316` (21 caracteres).
            # Quem lê o lote resolve o corte em `_leitura_partida`.
            i = fim
            campos.append((ai, valor, ate_o_fim))
    return campos


def interpretar(bruto) -> dict | None:
    """Lê uma etiqueta GS1. Devolve None quando o código não é GS1 com GTIN."""
    if bruto is None:
        return None
    s = str(bruto).strip()
    for prefixo in PREFIXOS_SIMBOLOGIA:
        # v18.17.1: sem olhar maiúscula/minúscula — com o Caps Lock ligado o
        # leitor manda "]c1" em vez de "]C1" e a etiqueta inteira deixava de ser
        # reconhecida como GS1.
        if s[:len(prefixo)].upper() == prefixo.upper():
            s = s[len(prefixo):]
    s = s.replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")
    if s.startswith("("):
        campos = _campos_com_parenteses(s)
    elif re.match(r"^0[12]\d{14}", s) and len(s) >= 16:
        # v18: ">= 16" — a etiqueta que traz SÓ o GTIN, lida sem parênteses, é
        # "01" + 14 dígitos (16 ao todo). Antes não era reconhecida e o material
        # cadastrado pela etiqueta completa não era achado por ela.
        campos = _campos_em_sequencia(s)
    elif re.match(r"^(10|11|17|21)", s) and not (s.isdigit() and len(s) <= 14):
        # Etiqueta secundária: só validade/lote/série, sem o GTIN — o GTIN está
        # num código de barras separado na mesma embalagem.
        campos = _campos_em_sequencia(s)
    else:
        return None
    dados = {ai: (valor, ate_o_fim) for ai, valor, ate_o_fim in campos}
    codigo = (dados.get("01") or dados.get("02") or ("", False))[0]
    if codigo and re.fullmatch(r"\d{13}", codigo):
        # v18.39: fabricante que imprime "(01)" com 13 dígitos (o EAN-13 sem o
        # indicador de embalagem). Pelo padrão o AI 01 tem 14; completar com o
        # zero da frente é o mesmo GTIN. Sem isto a etiqueta inteira não era
        # reconhecida e acabava gravada como se fosse o código do material.
        codigo = "0" + codigo
        dados["01"] = (codigo, False)
    if codigo and not re.fullmatch(r"\d{14}", codigo):
        return None
    if not codigo and not (dados.get("10") or dados.get("21")):
        return None
    lote, lote_sem_fim = dados.get("10", ("", False))
    serie, serie_sem_fim = dados.get("21", ("", False))
    info = {
        "gtin": codigo,
        "validade": _data(dados.get("17", ("", False))[0]),
        "lote": lote, "lote_ate_o_fim": lote_sem_fim,
        "serie": serie, "serie_ate_o_fim": serie_sem_fim,
        # v18.17: segunda leitura possível do lote (ver `_leitura_partida`).
        "lote_curto": "", "validade_do_lote": "",
    }
    if lote and lote_sem_fim:
        info.update(_leitura_partida(lote))
    return info


def codigo_de_busca(bruto) -> str:
    """O que procurar no cadastro: o GTIN, quando a leitura é uma etiqueta GS1."""
    info = interpretar(bruto)
    return info["gtin"] if info and info["gtin"] else re.sub(r"\s+", "", str(bruto or ""))


def lote_normalizado(valor) -> str:
    """Lote para comparar: só letras e números, maiúsculo, sem zeros à esquerda."""
    return _norm(valor)


def _norm(valor) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(valor or "").upper()).lstrip("0")


def _confere(cadastrado, lido: str, ate_o_fim: bool, flexivel: bool = True) -> bool:
    c, l = _norm(cadastrado), _norm(lido)
    if not c or not l:
        return False
    # v18.25: cadastro com a etiqueta inteira ou "LOTE: ..." dentro do campo lote.
    limpo = _norm(lote_limpo(cadastrado))
    if limpo and limpo != c and (limpo == l or (ate_o_fim and l.startswith(limpo))):
        return True
    # Sem separador, o lote "engole" os campos seguintes (ex.: 234004643 + (20)01
    # vira 2340046432001) — então basta o lido começar pelo cadastrado.
    if c == l or (ate_o_fim and l.startswith(c)):
        return True
    # nov/2026: algumas notas gravam no lote o lote + o campo seguinte da etiqueta,
    # sem o código do campo: etiqueta (10)21680129 (91)048, lida sem separador como
    # lote "2168012991048", e o cadastro tem "21680129048". Confere tirando, de
    # dentro do lido, um código de campo GS1 (91, 21, 30...).
    if ate_o_fim and flexivel:
        for k in range(1, len(l) - 1):
            for n in (2, 3, 4):
                ai = l[k:k + n]
                if (ai in VARIAVEIS or ai in FIXOS) and l[:k] + l[k + n:] == c:
                    return True
    return False


def _serie_confere_lote(lote_cadastrado, serie: str) -> bool:
    c = _norm(lote_cadastrado)
    if not c:
        return False
    sem_letras = re.sub(r"^[A-Z]+", "", re.sub(r"[^0-9A-Z]", "", str(serie or "").upper()))
    return c in (_norm(serie), sem_letras.lstrip("0"))


def filtrar(candidatas: list[dict], info: dict | None) -> tuple[list[dict], str]:
    """Restringe às unidades do lote/série/validade da etiqueta.

    Devolve (candidatas, aviso). Se a etiqueta traz um lote que não bate com
    nenhum cadastro, mantém as candidatas e devolve um aviso para a tela.
    """
    if not info or not candidatas:
        return candidatas, ""
    aviso = ""
    if info.get("serie"):
        mesmas = [c for c in candidatas
                  if _confere(c.get("numero_serie"), info["serie"], info["serie_ate_o_fim"])]
        if not mesmas and not info.get("lote"):
            # Etiqueta só com série (sem lote): há notas fiscais que trazem esse
            # número no campo lote, às vezes sem a letra do começo
            # (série S0000002545 → lote 0000002545).
            mesmas = [c for c in candidatas if _serie_confere_lote(c.get("nLote"), info["serie"])]
        if mesmas:
            candidatas = mesmas
    if info.get("lote"):
        # Primeiro o lote igual; depois "começa com" (campos grudados); por último
        # o lote com um campo GS1 embutido (ver `_confere`).
        lido = _norm(info["lote"])
        mesmas = [c for c in candidatas if _norm(c.get("nLote")) and _norm(c.get("nLote")) == lido]
        if not mesmas:
            mesmas = [c for c in candidatas
                      if _confere(c.get("nLote"), info["lote"], info["lote_ate_o_fim"], flexivel=False)]
        if not mesmas:
            mesmas = [c for c in candidatas if _confere(c.get("nLote"), info["lote"], info["lote_ate_o_fim"])]
        if not mesmas and info.get("lote_curto"):
            # v18.17: o lote da etiqueta pode ter engolido a validade colada.
            curto = _norm(info["lote_curto"])
            mesmas = [c for c in candidatas if _norm(c.get("nLote")) == curto]
            if not mesmas:
                mesmas = [c for c in candidatas
                          if _norm(c.get("nLote")) and curto.startswith(_norm(c.get("nLote")))]
        if mesmas:
            candidatas = mesmas
        else:
            cadastrados = sorted({str(c.get("nLote") or "—") for c in candidatas})
            aviso = (f"Atenção: o lote da etiqueta ({info['lote']}) não confere com o lote "
                     f"cadastrado ({', '.join(cadastrados)}). Confira a embalagem.")
    if info.get("validade") and len(candidatas) > 1:
        mesmas = [c for c in candidatas if str(c.get("dVal") or "")[:10] == info["validade"]]
        if mesmas:
            candidatas = mesmas
    return candidatas, aviso


# Só tira o rótulo quando ele vem separado do lote (": ", " ", " - "). Sem isso,
# "LOT2025A" e "LOTE99" — que são lotes de verdade — seriam mutilados.
PREFIXOS_DE_LOTE = re.compile(r"^\s*(?:LOTE|LOT|BATCH|L)(?:\s*[:.]\s*|\s*-\s+|\s+)", re.I)


def lote_limpo(valor) -> str:
    """v18.25: o que de fato é o lote, quando o campo vem "sujo" do cadastro.

    Duas sujeiras comuns no cadastro manual: bipar a etiqueta inteira dentro do
    campo lote, e digitar o rótulo junto ("LOTE: SP11250314005"). Nos dois
    casos a unidade depois não era achada pela etiqueta.
    """
    bruto = str(valor or "").strip()
    if not bruto:
        return ""
    lido = interpretar(bruto)
    if lido and (lido.get("lote") or lido.get("lote_curto")):
        return lido.get("lote_curto") or lido["lote"]
    limpo = PREFIXOS_DE_LOTE.sub("", bruto).strip()
    return limpo or bruto


def sql_por_lote(etiqueta: dict | None, alias: str = "u") -> tuple[str, list]:
    """Condição SQL para achar pelo LOTE da etiqueta secundária (sem GTIN).

    Algumas embalagens têm dois códigos: um só com o GTIN e outro só com
    validade/lote/quantidade. Quem bipa o segundo precisa achar o material
    pelo lote (e pela validade, quando vier). Devolve ("", []) se não se aplica.
    """
    if not etiqueta or etiqueta.get("gtin") or not etiqueta.get("lote"):
        return "", []
    lote = _norm(etiqueta["lote"])
    if not lote:
        return "", []
    if etiqueta.get("lote_ate_o_fim"):
        cond = f"(lote_norm({alias}.nLote) <> '' AND ? LIKE lote_norm({alias}.nLote) || '%')"
    else:
        cond = f"lote_norm({alias}.nLote) = ?"
    params = [lote]
    if etiqueta.get("validade"):
        cond += f" AND (COALESCE({alias}.dVal, '') = '' OR substr({alias}.dVal, 1, 10) = ?)"
        params.append(etiqueta["validade"])
    return cond, params
