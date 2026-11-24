"""v17 — gerador de PDF simples (relatórios em tabela), sem biblioteca externa.

O sistema roda num computador do hospital, às vezes sem internet para instalar
pacote novo. Um relatório em tabela não precisa de mais do que isto: páginas
A4 deitadas, Helvetica, título, linhas de informação e uma tabela que quebra de
página repetindo o cabeçalho. Acentos saem pela codificação WinAnsi (cp1252).
"""

from datetime import datetime

LARGURA, ALTURA = 842, 595  # A4 paisagem, em pontos
MARGEM = 36

# Larguras médias da Helvetica (em milésimos do tamanho da fonte) — o bastante
# para cortar o texto que não cabe na coluna.
_LARG = {**{c: 556 for c in "0123456789"}, " ": 278, ".": 278, ",": 278, "-": 333, "/": 278,
         "(": 333, ")": 333, ":": 278, "i": 222, "l": 222, "j": 222, "I": 278, "f": 278,
         "t": 278, "r": 333, "m": 833, "w": 722, "M": 833, "W": 944}


def _largura(texto: str, tamanho: float, negrito: bool = False) -> float:
    total = 0
    for c in texto:
        total += _LARG.get(c, 667 if c.isupper() else 556)
    return total * tamanho / 1000 * (1.05 if negrito else 1)


def _cortar(texto: str, largura: float, tamanho: float, negrito: bool = False) -> str:
    texto = str(texto or "")
    if _largura(texto, tamanho, negrito) <= largura:
        return texto
    while texto and _largura(texto + "…", tamanho, negrito) > largura:
        texto = texto[:-1]
    return texto + "…"


def _quebrar(texto: str, largura: float, tamanho: float) -> list[str]:
    """Quebra o texto em linhas que cabem na largura (palavra por palavra)."""
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = (atual + " " + palavra).strip()
        if _largura(tentativa, tamanho) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    linhas.append(atual)
    return [_cortar(l, largura, tamanho) for l in linhas] or [""]


def _esc(texto: str) -> bytes:
    bruto = str(texto).encode("cp1252", errors="replace")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Pagina:
    def __init__(self):
        self.ops: list[bytes] = []

    def texto(self, x, y, s, tamanho=9, negrito=False, cor=(0, 0, 0)):
        fonte = b"/F2" if negrito else b"/F1"
        self.ops.append(b"%.3f %.3f %.3f rg BT " % cor + fonte + b" %.1f Tf %.1f %.1f Td (" % (tamanho, x, y)
                        + _esc(s) + b") Tj ET")

    def retangulo(self, x, y, w, h, cor):
        self.ops.append(b"%.3f %.3f %.3f rg %.1f %.1f %.1f %.1f re f" % (*cor, x, y, w, h))

    def linha(self, x1, y1, x2, y2, cor=(0.8, 0.82, 0.85)):
        self.ops.append(b"%.3f %.3f %.3f RG 0.5 w %.1f %.1f m %.1f %.1f l S" % (*cor, x1, y1, x2, y2))


def tabela(*, titulo: str, subtitulo: str = "", informacoes: list[tuple[str, str]] | None = None,
           colunas: list[tuple[str, float]], linhas: list[list[str]], rodape: str = "",
           totais: list[str] | None = None, quebrar_linhas: bool = False,
           assinaturas: list[str] | None = None, texto_final: str = "") -> bytes:
    """Monta o PDF. `colunas` = [(título, largura_relativa)]; `linhas` = textos.

    nov/2026: `assinaturas` = um bloco por parte (ex.: "Hospital", "Fornecedor"),
    cada um com linha para assinatura, nome, documento e data; `texto_final` é a
    declaração impressa logo acima das assinaturas.
    """
    util = LARGURA - 2 * MARGEM
    soma = sum(p for _, p in colunas) or 1
    larguras = [util * p / soma for _, p in colunas]
    paginas: list[_Pagina] = []
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    azul = (0.047, 0.227, 0.404)

    def nova_pagina(primeira: bool) -> tuple[_Pagina, float]:
        p = _Pagina()
        paginas.append(p)
        y = ALTURA - MARGEM
        if primeira:
            p.texto(MARGEM, y - 14, titulo, 15, True, azul)
            y -= 22
            if subtitulo:
                p.texto(MARGEM, y - 10, subtitulo, 9.5, False, (0.3, 0.33, 0.38))
                y -= 16
            for rotulo, valor in (informacoes or []):
                p.texto(MARGEM, y - 10, rotulo + ":", 8.5, True)
                p.texto(MARGEM + _largura(rotulo + ": ", 8.5, True) + 2, y - 10, valor, 8.5)
                y -= 13
            y -= 8
        else:
            p.texto(MARGEM, y - 10, titulo + " (continuação)", 10, True, azul)
            y -= 20
        # cabeçalho da tabela
        p.retangulo(MARGEM, y - 16, util, 16, (0.93, 0.945, 0.96))
        x = MARGEM
        for (rotulo, _), w in zip(colunas, larguras):
            p.texto(x + 3, y - 11.5, _cortar(rotulo.upper(), w - 6, 7.5, True), 7.5, True, (0.3, 0.33, 0.38))
            x += w
        return p, y - 16

    pagina, y = nova_pagina(True)
    if not linhas:
        pagina.texto(MARGEM + 3, y - 14, "Nenhum registro no período.", 9, False, (0.4, 0.4, 0.4))
    for linha in linhas:
        if quebrar_linhas:
            # Texto longo (ex.: descrição do HC) quebra em várias linhas na célula.
            celulas = [_quebrar(str(valor or ""), w - 14, 8) for valor, w in zip(linha, larguras)]
            altura = 11 * max(len(c) for c in celulas) + 4
        else:
            celulas = [[_cortar(valor, w - 6, 8)] for valor, w in zip(linha, larguras)]
            altura = 15
        if y - altura < MARGEM + 20:
            pagina, y = nova_pagina(False)
        x = MARGEM
        for partes, w in zip(celulas, larguras):
            for n, parte in enumerate(partes):
                pagina.texto(x + 3, y - 11 - 11 * n, parte, 8)
            x += w
        y -= altura
        pagina.linha(MARGEM, y, MARGEM + util, y)
    if totais:
        y -= 6
        for t in totais:
            if y - 13 < MARGEM + 20:
                pagina, y = nova_pagina(False)
            pagina.texto(MARGEM, y - 11, t, 9, True)
            y -= 14
    if assinaturas:
        declaracao = _quebrar(texto_final, util, 9) if texto_final else []
        altura_bloco = 14 * len(declaracao) + 110
        if y - altura_bloco < MARGEM + 20:
            pagina, y = nova_pagina(False)
        y -= 14
        for parte in declaracao:
            pagina.texto(MARGEM, y - 11, parte, 9)
            y -= 14
        y -= 34
        n = len(assinaturas)
        espaco = 30
        largura_bloco = (util - espaco * (n - 1)) / n
        for i, quem in enumerate(assinaturas):
            x = MARGEM + i * (largura_bloco + espaco)
            pagina.linha(x, y, x + largura_bloco, y, (0.2, 0.2, 0.2))
            pagina.texto(x, y - 12, quem, 9, True, azul)
            pagina.texto(x, y - 26, "Nome legível: " + "_" * 40, 8.5)
            pagina.texto(x, y - 40, "Matrícula / documento: " + "_" * 28, 8.5)
            pagina.texto(x, y - 54, "Data: ____/____/________", 8.5)
        y -= 60

    total = len(paginas)
    for n, p in enumerate(paginas, 1):
        p.texto(MARGEM, MARGEM - 14, f"{rodape}  ·  gerado em {gerado}".strip(" ·"), 7.5, False, (0.45, 0.45, 0.45))
        p.texto(LARGURA - MARGEM - 60, MARGEM - 14, f"página {n} de {total}", 7.5, False, (0.45, 0.45, 0.45))

    # --- montagem dos objetos do PDF
    objetos: list[bytes] = []
    def add(conteudo: bytes) -> int:
        objetos.append(conteudo)
        return len(objetos)

    add(b"")  # 1: catálogo (preenchido no fim)
    add(b"")  # 2: árvore de páginas
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    filhos = []
    for p in paginas:
        fluxo = b"\n".join(p.ops)
        c = add(b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"\nendstream")
        filhos.append(add(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                          % (LARGURA, ALTURA, f1, f2, c)))
    objetos[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objetos[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in filhos) + b"] /Count %d >>" % len(filhos)

    saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posicoes = []
    for i, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for pos in posicoes:
        saida += b"%010d 00000 n \n" % pos
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return bytes(saida)
