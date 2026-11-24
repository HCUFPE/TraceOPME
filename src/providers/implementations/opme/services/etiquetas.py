"""Etiquetas com QR Code para material sem código de barras de fábrica.

Boa parte do OPME chega sem código de barras legível — embalagem estéril com
etiqueta manuscrita, item avulso, consignado que veio sem identificação. Sem um
código, esse material não entra no fluxo de bipagem e o rastreio se perde
justamente nos itens mais problemáticos.

A saída é o almoxarifado gerar o próprio código no momento do cadastro: um
código interno estável, impresso como QR Code e colado na embalagem. A partir
daí ele é bipado como qualquer outro item — nada mais no sistema precisa saber
que aquele código nasceu aqui dentro.

O conteúdo do QR é o próprio código interno, em texto puro. É o formato que
qualquer leitor entende sem configuração: para o scanner, ler o QR é
indistinguível de ler um código de barras comum.
"""

import io
import re

from ..utils import gerar_id, normalizar_codigo, texto

PREFIXO_INTERNO = "OPME"

# Formato do código gerado: CÓDIGO AGHU entre o produto e o lote, como
# "PA1780(07-0426C)". É o mesmo formato que o hospital já usava nas etiquetas
# feitas à mão, então quem lê a etiqueta reconhece o item sem precisar do
# sistema. Também é legível para digitação, se o leitor falhar.
PADRAO_CODIGO = re.compile(r"^[^()\s]+\([^()]+\)$")


def gerar_codigo_interno(codigo_aghu: str = "", lote: str = "") -> str:
    """Código interno para material que chegou sem código de barras.

    Com AGHU e lote, usa o formato `AGHU(LOTE)`. Sem eles, cai num código
    aleatório — melhor um código feio do que nenhum, porque sem código o item
    não entra no fluxo de bipagem.

    Duas unidades do mesmo AGHU e mesmo lote recebem o mesmo código, e isso é
    correto: é assim que o sistema já trata caixas iguais vindas de NF-e. Cada
    unidade continua tendo o seu próprio `id_unidade` para o rastreio individual.
    """
    aghu = normalizar_codigo(codigo_aghu).upper()
    lote_limpo = normalizar_codigo(lote).upper()
    if aghu and lote_limpo:
        return f"{aghu}({lote_limpo})"
    return gerar_id(PREFIXO_INTERNO).replace("-", "")


def e_codigo_interno(codigo: str) -> bool:
    """Reconhece os dois formatos gerados aqui dentro."""
    valor = texto(codigo).upper()
    return bool(PADRAO_CODIGO.match(valor)) or valor.startswith(PREFIXO_INTERNO)


class QRIndisponivel(Exception):
    """A biblioteca de QR Code não está instalada neste ambiente."""


def qr_disponivel() -> bool:
    """Permite a tela avisar antes, em vez de mostrar imagens quebradas."""
    try:
        import qrcode  # noqa: F401
        return True
    except ImportError:
        return False


def gerar_png(conteudo: str, legenda: str = "", borda: int = 3) -> bytes:
    """PNG do QR Code com o conteúdo informado e uma legenda legível embaixo.

    A legenda importa: se o QR estiver danificado ou o leitor falhar, ainda dá
    para digitar o código à mão na tela de bipagem.
    """
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError as erro:  # ambiente sem a dependência opcional
        raise QRIndisponivel(
            "A biblioteca de QR Code não está instalada. Feche a aplicação e rode "
            "novamente o iniciar.bat — ele instala o que falta."
        ) from erro

    qr = qrcode.QRCode(
        version=None,
        # Etiqueta em ambiente hospitalar: sujeira, dobra e álcool são comuns.
        error_correction=ERROR_CORRECT_M,
        box_size=8,
        border=borda,
    )
    qr.add_data(texto(conteudo))
    qr.make(fit=True)
    imagem = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if legenda:
        imagem = _com_legenda(imagem, legenda)

    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def _com_legenda(imagem, texto_legenda: str):
    from PIL import Image, ImageDraw, ImageFont

    largura, altura = imagem.size
    faixa = 34
    nova = Image.new("RGB", (largura, altura + faixa), "white")
    nova.paste(imagem, (0, 0))

    desenho = ImageDraw.Draw(nova)
    try:
        fonte = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        fonte = ImageFont.load_default()

    caixa = desenho.textbbox((0, 0), texto_legenda, font=fonte)
    pos_x = max((largura - (caixa[2] - caixa[0])) // 2, 0)
    desenho.text((pos_x, altura + 6), texto_legenda, fill="black", font=fonte)
    return nova
