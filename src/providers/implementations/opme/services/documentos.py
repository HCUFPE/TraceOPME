"""Geração de TXT e PDF simples, sem dependência externa.

O caso de uso é o descritivo cirúrgico: o médico abre a ficha do paciente,
copia a lista de materiais implantados e cola no prontuário; ou imprime a
mesma lista para anexar. São poucas linhas de texto, então não vale trazer uma
biblioteca de PDF inteira para isso — o PDF aqui é montado à mão, com a fonte
Helvetica que todo leitor de PDF já traz.
"""

from ..utils import texto

import textwrap

LARGURA_PAGINA = 595  # A4 em pontos (72 dpi)
ALTURA_PAGINA = 842
MARGEM = 56
ALTURA_LINHA = 13
TAMANHO_FONTE = 9
LINHAS_POR_PAGINA = int((ALTURA_PAGINA - 2 * MARGEM) / ALTURA_LINHA)

# Courier é monoespaçada: cada caractere ocupa 0,6 do tamanho da fonte. Com isso
# dá para saber exatamente quantos cabem na linha — o PDF não quebra texto
# sozinho, e o que passa da margem simplesmente some da folha impressa.
LARGURA_CARACTERE = TAMANHO_FONTE * 0.6
COLUNAS = int((LARGURA_PAGINA - 2 * MARGEM) / LARGURA_CARACTERE)


def quebrar_linha(linha: str, colunas: int = COLUNAS) -> list[str]:
    """Quebra a linha no limite da página, mantendo o recuo da original.

    A continuação entra alinhada com o começo do texto, e não na margem, para
    a lista continuar legível quando o nome do produto ou do fornecedor é longo.
    """
    # Sem `texto()` aqui de propósito: ele faz strip nas duas pontas e apagaria
    # justamente o recuo que esta função precisa preservar.
    linha = ("" if linha is None else str(linha)).rstrip()
    if not linha.strip():
        return [""]
    if len(linha) <= colunas:
        return [linha]

    # `textwrap` descarta o espaço do começo, o que apagaria o recuo e faria a
    # descrição do produto parecer um item de primeiro nível. Por isso o recuo
    # é retirado antes e devolvido como indent explícito.
    recuo = " " * (len(linha) - len(linha.lstrip()))
    continuacao = recuo + "    "
    if len(continuacao) > colunas - 20:
        continuacao = recuo
    return textwrap.wrap(
        linha.strip(), width=colunas,
        initial_indent=recuo,
        subsequent_indent=continuacao,
        break_long_words=True,      # código de barras longo não pode estourar a margem
        break_on_hyphens=False,     # não quebra "U-2305-E" no meio
    ) or [recuo]


def _escapar(linha: str) -> str:
    """Escapa os caracteres com significado especial dentro de uma string PDF."""
    return (texto(linha)
            .replace("\\", r"\\")
            .replace("(", r"\(")
            .replace(")", r"\)"))


# Sinais tipográficos que o sistema usa nas mensagens mas não existem em
# Latin-1 — sem a troca, sairiam como "?" no PDF impresso.
EQUIVALENTES = str.maketrans({
    "—": "-", "–": "-", "‑": "-",
    "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'",
    "…": "...", "•": "-", " ": " ",
})


def _para_latin1(linha: str) -> str:
    """As fontes padrão do PDF usam Latin-1; o que não couber vira '?'.

    Acentos do português cabem em Latin-1 e são preservados. Perder um símbolo
    exótico é aceitável; quebrar o arquivo inteiro não é.
    """
    return texto(linha).translate(EQUIVALENTES).encode("latin-1", errors="replace").decode("latin-1")


def _pagina(linhas: list[str]) -> bytes:
    partes = [b"BT", f"/F1 {TAMANHO_FONTE} Tf {ALTURA_LINHA} TL".encode("latin-1"),
              f"{MARGEM} {ALTURA_PAGINA - MARGEM} Td".encode("latin-1")]
    for linha in linhas:
        partes.append(f"({_escapar(_para_latin1(linha))}) Tj T*".encode("latin-1"))
    partes.append(b"ET")
    return b"\n".join(partes)


def pdf_de_texto(linhas: list[str]) -> bytes:
    """PDF de uma ou mais páginas com texto monoespaçado, pronto para imprimir."""
    ajustadas: list[str] = []
    for linha in (linhas or [""]):
        ajustadas.extend(quebrar_linha(linha))

    paginas = [ajustadas[i:i + LINHAS_POR_PAGINA]
               for i in range(0, len(ajustadas), LINHAS_POR_PAGINA)] or [[""]]

    objetos: list[bytes] = []

    def adicionar(corpo: bytes) -> int:
        objetos.append(corpo)
        return len(objetos)  # números de objeto começam em 1

    # A ordem importa só para os identificadores; as referências são resolvidas
    # depois, quando já sabemos o número de cada objeto.
    id_catalogo = adicionar(b"")
    id_paginas = adicionar(b"")
    id_fonte = adicionar(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

    ids_paginas: list[int] = []
    for conteudo_pagina in paginas:
        fluxo = _pagina(conteudo_pagina)
        id_fluxo = adicionar(
            b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream")
        id_pagina = adicionar(b"")
        objetos[id_pagina - 1] = (
            b"<< /Type /Page /Parent " + str(id_paginas).encode() + b" 0 R"
            b" /MediaBox [0 0 " + str(LARGURA_PAGINA).encode() + b" " + str(ALTURA_PAGINA).encode() + b"]"
            b" /Resources << /Font << /F1 " + str(id_fonte).encode() + b" 0 R >> >>"
            b" /Contents " + str(id_fluxo).encode() + b" 0 R >>")
        ids_paginas.append(id_pagina)

    kids = b" ".join(str(i).encode() + b" 0 R" for i in ids_paginas)
    objetos[id_paginas - 1] = (
        b"<< /Type /Pages /Count " + str(len(ids_paginas)).encode() + b" /Kids [" + kids + b"] >>")
    objetos[id_catalogo - 1] = (
        b"<< /Type /Catalog /Pages " + str(id_paginas).encode() + b" 0 R >>")

    saida = bytearray(b"%PDF-1.4\n")
    posicoes: list[int] = []
    for numero, corpo in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += str(numero).encode() + b" 0 obj\n" + corpo + b"\nendobj\n"

    inicio_xref = len(saida)
    saida += b"xref\n0 " + str(len(objetos) + 1).encode() + b"\n"
    saida += b"0000000000 65535 f \n"
    for posicao in posicoes:
        saida += f"{posicao:010d} 00000 n \n".encode()
    saida += (b"trailer\n<< /Size " + str(len(objetos) + 1).encode()
              + b" /Root " + str(id_catalogo).encode() + b" 0 R >>\n"
              b"startxref\n" + str(inicio_xref).encode() + b"\n%%EOF\n")
    return bytes(saida)
