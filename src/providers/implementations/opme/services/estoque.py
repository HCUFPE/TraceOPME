"""Entrada de materiais: cadastro manual, importação de NF-e e correções."""

import re
import xml.etree.ElementTree as ET
from datetime import datetime

from .. import busca, db, gs1
from ..domain import BAIXADO, EM_ESTOQUE_RECEBIMENTO, ESTOQUE_ATIVO
from ..utils import data_hora_br, data_iso, decimal, gerar_id, inteiro, normalizar_codigo, texto
from . import etiquetas, materiais

TIPOS_ENTRADA = {
    "aquisicao_propria": "Aquisição própria",
    "consignado": "Consignado",
    "doacao": "Doação",
    "emprestimo": "Empréstimo",
}


def normalizar_tipo_entrada(valor) -> str:
    chave = texto(valor).lower().replace(" ", "_").replace("ç", "c").replace("ã", "a").replace("é", "e")
    return chave if chave in TIPOS_ENTRADA else "aquisicao_propria"


# =========================================================
# HISTÓRICO DE PRODUTOS (sugestão de marca/fabricante — nunca preenche sozinho)
# =========================================================
#
# A NF-e não traz marca/fabricante, e o "fornecedor" dela costuma ser um
# distribuidor ou operador logístico da licitação, não o fabricante real. O
# mesmo código de compra pode ser atendido por marcas diferentes a cada
# pregão/lote — por isso este histórico NUNCA escolhe um valor sozinho. Ele só
# alimenta uma lista de sugestões (autocomplete) com as marcas já vistas para
# aquele código; quem recebe sempre confere e escolhe/digita a marca real
# desta entrega. O campo continua obrigatório em todas as telas.
#
# O código de barras sozinho NÃO identifica o produto: materiais diferentes
# podem compartilhar o mesmo código (código genérico do distribuidor, GTIN
# reaproveitado, etc.). Por isso toda consulta aqui também exige que a
# descrição (`xProd`) bata — senão a sugestão de um item vazaria para outro
# completamente diferente que por acaso chegou com o mesmo código.

def _mesmo_produto(xProd: str):
    """Compara descrição ignorando maiúsculas/espaços nas pontas — mesma
    exigência das duas funções abaixo, para não duplicar a normalização."""
    return texto(xProd).strip().upper()


def marcas_conhecidas(codigo: str, xProd: str = "") -> list[str]:
    """Marcas/fabricantes já vistos para este código de barras **e** esta
    descrição de produto, mais usada primeiro.

    Mais de uma marca na lista é o caso normal, não um erro — é justamente o
    sinal de que este produto já veio de fabricantes diferentes e merece
    atenção redobrada na conferência.
    """
    codigo = normalizar_codigo(codigo)
    if not codigo or not texto(xProd) or etiquetas.e_codigo_interno(codigo):
        return []
    linhas = db.consultar(
        """SELECT marca_fabricante, COUNT(*) AS vezes, MAX(criado_em) AS ultima
           FROM historico_produtos WHERE codigo = ? AND UPPER(TRIM(xProd)) = ?
           GROUP BY marca_fabricante ORDER BY vezes DESC, ultima DESC""",
        (codigo, _mesmo_produto(xProd)),
    )
    return [l["marca_fabricante"] for l in linhas if texto(l["marca_fabricante"])]


def aghus_conhecidos(codigo: str, xProd: str = "") -> list[str]:
    """Códigos AGHU já usados para este código de barras **e** esta descrição
    de produto (mesma ressalva acima)."""
    codigo = normalizar_codigo(codigo)
    if not codigo or not texto(xProd) or etiquetas.e_codigo_interno(codigo):
        return []
    linhas = db.consultar(
        """SELECT codigo_aghu, COUNT(*) AS vezes, MAX(criado_em) AS ultima
           FROM historico_produtos WHERE codigo = ? AND UPPER(TRIM(xProd)) = ?
           GROUP BY codigo_aghu ORDER BY vezes DESC, ultima DESC""",
        (codigo, _mesmo_produto(xProd)),
    )
    return [l["codigo_aghu"] for l in linhas if texto(l["codigo_aghu"])]


def _registrar_historico(conn, *, codigo: str, xProd: str, codigo_aghu: str,
                          marca_fabricante: str, fornecedor_cnpj: str = "",
                          fornecedor: str = "", usuario: str = "") -> None:
    """Acrescenta ao histórico o que foi confirmado agora — sem apagar o que já
    havia. Diferentes marcas para o mesmo código convivem de propósito: cada
    uma é uma entrada distinta, não uma substituição da anterior.

    Um código interno gerado aqui dentro (`AGHU(LOTE)`) é específico daquele
    lote, não do produto, e não deve virar sugestão para outro lote do mesmo
    item — por isso é ignorado.
    """
    codigo = normalizar_codigo(codigo)
    if not codigo or etiquetas.e_codigo_interno(codigo) or not texto(marca_fabricante):
        return
    conn.execute(
        """INSERT OR IGNORE INTO historico_produtos
           (codigo, xProd, codigo_aghu, marca_fabricante, fornecedor_cnpj, fornecedor,
            criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (codigo, texto(xProd), texto(codigo_aghu), texto(marca_fabricante),
         texto(fornecedor_cnpj), texto(fornecedor), db.agora(), texto(usuario)),
    )


def backfilar_historico(usuario: str = "sistema") -> int:
    """Carrega no histórico o que já está nas unidades cadastradas antes desta versão.

    Sem isto, as sugestões só começariam a aparecer depois da primeira entrada
    de cada produto feita já com o histórico no ar. Roda a cada início da
    aplicação — é uma consulta simples e `INSERT OR IGNORE` não duplica.
    """
    candidatos = db.consultar(
        """SELECT DISTINCT COALESCE(NULLIF(cEAN, ''), codigo_barras) AS codigo,
                  xProd, codigo_aghu, marca_fabricante, fornecedor
           FROM unidades
           WHERE marca_fabricante <> ''
             AND COALESCE(NULLIF(cEAN, ''), codigo_barras) <> ''"""
    )
    gravados = 0
    with db.transacao() as conn:
        for linha in candidatos:
            codigo = normalizar_codigo(linha["codigo"])
            if not codigo or etiquetas.e_codigo_interno(codigo):
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO historico_produtos
                   (codigo, xProd, codigo_aghu, marca_fabricante, fornecedor,
                    criado_em, criado_por)
                   VALUES (?,?,?,?,?,?,?)""",
                (codigo, texto(linha["xProd"]), texto(linha["codigo_aghu"]),
                 texto(linha["marca_fabricante"]), texto(linha["fornecedor"]),
                 db.agora(), usuario),
            )
            gravados += cur.rowcount
    return gravados


# =========================================================
# CADASTRO MANUAL
# =========================================================

OBRIGATORIOS_MANUAL = {
    "xProd": "Descrição do produto",
    "codigo_barras": "Código de barras",
    "codigo_aghu": "Código AGHU",
    "fornecedor": "Fornecedor",
    "marca_fabricante": "Marca/Fabricante",
    "nLote": "Lote",
}


def limpar_codigo_do_formulario(dados: dict) -> dict:
    """v18.39: o campo "código de barras" recebendo a etiqueta inteira.

    No cadastro de 19/11/2026 o almoxarifado gravou etiquetas inteiras dentro
    do campo do código — `1727101810MK19A1212089` (validade+lote, sem GTIN) e
    `(01)7898716350396(17)300402(10)020426(21)562550(11)260402`. O material
    ficava com um "código" que nenhuma etiqueta reproduz, e o lote saía
    truncado. Aqui a etiqueta é desmontada: fica o GTIN no código e o que ela
    traz de lote, validade e série preenche o que estiver em branco.
    """
    bruto = texto(dados.get("codigo_barras"))
    if not bruto:
        return dados
    lido = gs1.interpretar(bruto)
    if not lido:
        return dados
    dados = dict(dados)
    # Com GTIN, fica o GTIN. Sem GTIN (etiqueta só de validade e lote), fica o
    # código como foi bipado: é o que a embalagem tem, e bipá-lo de novo acha o
    # material pelo lote e pela validade. Exigir outro código só daria trabalho
    # de etiqueta sem resolver nada (decisão da Camila, 20/11/2026).
    dados["codigo_barras"] = texto(lido.get("gtin")) or bruto
    for campo, valor in (("nLote", lido.get("lote_curto") or lido.get("lote")),
                         ("dVal", lido.get("validade") or lido.get("validade_do_lote")),
                         ("dFab", lido.get("fabricacao")),
                         ("numero_serie", lido.get("serie"))):
        if texto(valor) and not texto(dados.get(campo)):
            dados[campo] = valor
    return dados


def avisos_do_cadastro(dados: dict) -> list[str]:
    """Alertas que não impedem o cadastro, mas pedem conferência."""
    avisos = []
    codigo = texto(dados.get("codigo_barras"))
    aghu, lote = texto(dados.get("codigo_aghu")), texto(dados.get("nLote"))
    if codigo.isdigit() and len(codigo) == 14 and codigo[0] not in "09":
        avisos.append(f"O código {codigo} começa com {codigo[0]}: é o GTIN da CAIXA, não o da peça. "
                      f"A etiqueta da unidade costuma ser 0{codigo[1:]} — confira antes de salvar.")
    lido = gs1.interpretar(codigo)
    if lido and not texto(lido.get("gtin")):
        avisos.append("Este código traz só validade e lote, sem o identificador do produto. "
                      "Está cadastrado assim mesmo — mas, se a embalagem tiver outro código de "
                      "barras, bipe sempre o mesmo para o material ser achado.")
    if aghu and lote:
        iguais = db.consultar(
            """SELECT COUNT(*) AS n, MIN(criado_em) AS quando, MAX(criado_por) AS por
               FROM unidades WHERE codigo_aghu = ? AND lote_norm(nLote) = lote_norm(?)
                 AND status NOT IN ('baixado','devolvido_fornecedor')""", (aghu, lote))
        if iguais and iguais[0]["n"]:
            l = iguais[0]
            avisos.append(f"Já existem {l['n']} unidade(s) deste material com o lote {lote} "
                          f"(primeira em {data_hora_br(l['quando'])}, por {l['por'] or '—'}). "
                          "Se for a mesma peça, não cadastre de novo.")
    return avisos


def limpar_lote_do_formulario(dados: dict) -> dict:
    """v18.25: o campo Lote aceita a etiqueta bipada e o rótulo digitado junto.

    Quem cadastra costuma bipar a etiqueta GS1 dentro do campo Lote, ou digitar
    "LOTE: SP112...". Gravado assim, o material existia mas nunca era achado
    pela etiqueta. Aqui fica só o lote — e, se a etiqueta trazia validade e o
    formulário não, ela é aproveitada.
    """
    bruto = texto(dados.get("nLote"))
    if not bruto:
        return dados
    limpo = gs1.lote_limpo(bruto)
    if limpo == bruto:
        return dados
    dados = dict(dados)
    dados["nLote"] = limpo
    lido = gs1.interpretar(bruto)
    if lido and not texto(dados.get("dVal")):
        validade = lido.get("validade") or lido.get("validade_do_lote")
        if validade:
            dados["dVal"] = validade
    return dados


def aplicar_codigo_interno(dados: dict) -> dict:
    """Gera um código interno quando o item chega sem código de barras.

    Material sem código de barras de fábrica não teria como ser bipado nas
    etapas seguintes. O almoxarifado gera um código próprio no formato
    `AGHU(LOTE)`, imprime como QR Code e cola na embalagem — a partir daí o
    item é tratado como qualquer outro.
    """
    marcado = str(dados.get("sem_codigo_barras", "")).lower() in ("1", "true", "on", "sim")
    if marcado and not texto(dados.get("codigo_barras")):
        dados = dict(dados)
        dados["codigo_barras"] = etiquetas.gerar_codigo_interno(
            dados.get("codigo_aghu"), dados.get("nLote"))
    return dados


def codigo_consignado_valido(tipo_entrada: str, valor, codigo_aghu: str = "",
                             fornecedor: str = "") -> tuple[bool, str]:
    """nov/2026: material consignado entra com o código do consignado.

    v18.4.7: o código não é mais digitado — vem da relação AGHU × consignado
    (Consignados → Código consignado × AGHU). A tela só envia um valor quando o
    AGHU tem mais de um código (a pessoa escolhe qual). Fora do consignado o
    campo não se aplica e é gravado vazio.
    """
    if normalizar_tipo_entrada(tipo_entrada) != "consignado":
        return True, ""
    from . import consignado_aghu
    if texto(valor):
        # a tela só envia o código quando a pessoa escolhe entre os do AGHU
        return True, texto(valor)
    return consignado_aghu.resolver_por_aghu(codigo_aghu, fornecedor)


def descritivo_para_unidade(tipo_entrada, codigo_consignado, codigo_aghu, xprod) -> str:
    """Descrição que as telas mostram para a unidade.

    v18.11.5: CONSIGNADO mostra a descrição do PRÓPRIO material (a da relação
    consignado × AGHU ou, sem ela, a da NF/cadastro) — é onde vem o tamanho do
    balão/stent. O descritivo do AGHU é genérico ("2,25MM A 4,5MM") e continua no
    catálogo mestre. Os demais materiais seguem com o descritivo do AGHU.
    """
    if texto(tipo_entrada) == "consignado":
        linha = db.consultar_um("SELECT descricao FROM consignado_aghu WHERE codigo_consignado = ?",
                                (texto(codigo_consignado),)) if texto(codigo_consignado) else None
        return texto((linha or {}).get("descricao")) or texto(xprod) or texto(materiais.descritivo_hospital(codigo_aghu))
    return materiais.descritivo_hospital(codigo_aghu)


def cadastrar_manual(dados: dict, usuario: str, farmacia: str = "") -> tuple[bool, str]:
    """Cadastro manual. Com `farmacia` (nov/2026), as unidades entram direto no
    estoque daquela farmácia (Bloco ou Hemodinâmica) em vez do almoxarifado."""
    from ..config import FARMACIAS, rotulo_farmacia
    from ..domain import EM_ESTOQUE_FARMACIA
    farmacia = texto(farmacia).upper()
    if farmacia and farmacia not in FARMACIAS:
        return False, "Escolha a farmácia (Bloco Cirúrgico ou Hemodinâmica) onde o material vai ficar."
    status_entrada = EM_ESTOQUE_FARMACIA if farmacia else EM_ESTOQUE_RECEBIMENTO
    dados = limpar_codigo_do_formulario(dados)
    dados = aplicar_codigo_interno(dados)
    dados = limpar_lote_do_formulario(dados)

    faltando = [rot for campo, rot in OBRIGATORIOS_MANUAL.items() if not texto(dados.get(campo))]
    if faltando:
        return False, "Preencha: " + ", ".join(faltando) + "."

    if not texto(dados.get("quantidade")):
        return False, "Informe a quantidade."
    quantidade = inteiro(dados.get("quantidade"), 0)
    if quantidade <= 0:
        return False, "A quantidade precisa ser maior que zero."
    if quantidade > 500:
        return False, "Quantidade acima do limite de 500 unidades por lançamento."

    validade = data_iso(dados.get("dVal"))
    if texto(dados.get("dVal")) and not validade:
        return False, "Data de validade inválida. Use DD/MM/AAAA."

    numeros_serie = [texto(s) for s in (dados.get("numeros_serie") or "").splitlines() if texto(s)]
    if numeros_serie and len(numeros_serie) != quantidade:
        return False, (f"Foram informados {len(numeros_serie)} números de série "
                       f"para {quantidade} unidade(s). Os valores precisam bater.")

    tipo_entrada = normalizar_tipo_entrada(dados.get("tipo_entrada"))
    ok_consignado, codigo_consignado = codigo_consignado_valido(tipo_entrada, dados.get("codigo_consignado"),
                                                                       dados.get("codigo_aghu"), dados.get("fornecedor"))
    if not ok_consignado:
        return False, codigo_consignado
    # Nome oficial do material, se o catálogo mestre conhece este código AGHU
    # — vem da própria referência do hospital, não de um palpite.
    descritivo_hospital = descritivo_para_unidade(tipo_entrada, codigo_consignado, dados.get("codigo_aghu"),
                                                  dados.get("xProd"))
    agora = db.agora()

    with db.transacao() as conn:
        for indice in range(quantidade):
            id_unidade = gerar_id("U")
            conn.execute(
                """INSERT INTO unidades
                   (id_unidade, codigo_barras, codigo_aghu, xProd, marca_fabricante, fornecedor,
                    nLote, numero_serie, dFab, dVal, vUnCom, cEAN, origem, chave_nf, numero_nf,
                    tipo_entrada, status, descritivo_hospital, criado_em, criado_por,
                    atualizado_em, atualizado_por, codigo_consignado, farmacia)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'manual',?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    id_unidade,
                    normalizar_codigo(dados.get("codigo_barras")),
                    texto(dados.get("codigo_aghu")),
                    texto(dados.get("xProd")),
                    texto(dados.get("marca_fabricante")),
                    texto(dados.get("fornecedor")),
                    texto(dados.get("nLote")),
                    numeros_serie[indice] if numeros_serie else "",
                    data_iso(dados.get("dFab")),
                    validade,
                    decimal(dados.get("vUnCom")),
                    "",
                    texto(dados.get("numero_nf")),
                    texto(dados.get("numero_nf")),
                    tipo_entrada,
                    status_entrada,
                    descritivo_hospital,
                    agora, usuario, agora, usuario, codigo_consignado, farmacia or None,
                ),
            )
            db.registrar_evento(
                conn, tipo="entrada_manual", id_unidade=id_unidade,
                status_novo=status_entrada, usuario=usuario,
                observacao=(f"{texto(dados.get('xProd'))} · lote {texto(dados.get('nLote'))}"
                            + (f" · cadastrado direto no estoque da {rotulo_farmacia(farmacia)}" if farmacia else "")),
            )
        _registrar_historico(
            conn, codigo=dados.get("codigo_barras"), xProd=dados.get("xProd"),
            codigo_aghu=dados.get("codigo_aghu"), marca_fabricante=dados.get("marca_fabricante"),
            fornecedor=dados.get("fornecedor"), usuario=usuario,
        )

    mensagem = (f"{quantidade} unidade(s) cadastrada(s) e disponível(is) no estoque da {rotulo_farmacia(farmacia)}."
                if farmacia else f"{quantidade} unidade(s) cadastrada(s) e disponível(is) no Almoxarifado.")
    codigo_final = normalizar_codigo(dados.get("codigo_barras"))
    if etiquetas.e_codigo_interno(codigo_final):
        mensagem += (f" Código interno gerado: {codigo_final} — imprima a etiqueta QR "
                     f"e cole na embalagem antes de guardar.")
    return True, mensagem


# =========================================================
# NOTA FISCAL ELETRÔNICA
# =========================================================

def cean_utilizavel(cEAN: str) -> str:
    """O cEAN da NF-e, quando é mesmo um código de barras de fábrica.

    A NF-e usa o texto fixo "SEM GTIN" nesse campo quando o produto não tem
    código de barras — não é um código real, e sugerir isso na tela faria
    o almoxarifado "receber" um item com o código de barras errado.
    """
    codigo = normalizar_codigo(cEAN)
    if not codigo or codigo.upper().replace(" ", "") == "SEMGTIN":
        return ""
    return codigo


def _txt_xml(no, caminho: str, ns: dict) -> str:
    if no is None:
        return ""
    return texto(no.findtext(caminho, default="", namespaces=ns))


def _primeiro(conteudo: str, padroes: list[str]) -> str:
    conteudo = " ".join(texto(conteudo).split())
    for padrao in padroes:
        achado = re.search(padrao, conteudo, flags=re.IGNORECASE)
        if achado:
            return texto(achado.group(1)).strip(" .;,|")
    return ""


def _extrair_do_texto(conteudo: str) -> dict:
    return {
        "nLote": _primeiro(conteudo, [
            r"\bLote\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/\-]*)",
            r"\bLot\.?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/\-]*)",
        ]),
        "dFab": data_iso(_primeiro(conteudo, [
            r"\bD\.?\s*Fab\.?\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
            r"\bData\s*(?:de\s*)?Fab(?:rica[cç][aã]o)?\.?\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        ])),
        "dVal": data_iso(_primeiro(conteudo, [
            r"\bD\.?\s*Val\.?\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
            r"\bData\s*(?:de\s*)?Ven(?:c|cimento)\.?\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
            r"\bValidade\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        ])),
        "qtd": inteiro(_primeiro(conteudo, [
            r"\bQtde?\.?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)",
            r"\bQuantidade\s*[:\-]?\s*(\d+(?:[.,]\d+)?)",
        ]), 0),
    }


def ler_xml_nfe(conteudo: bytes) -> tuple[bool, str | dict]:
    """Extrai cabeçalho e itens da NF-e, agrupando por produto/lote."""
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError as erro:
        return False, f"Arquivo XML inválido: {erro}"

    ns = {"n": "http://www.portalfiscal.inf.br/nfe"}
    inf = raiz.find(".//n:infNFe", ns)
    if inf is None:
        return False, "Este XML não parece ser uma NF-e (elemento infNFe não encontrado)."

    chave = texto(inf.attrib.get("Id", "")).removeprefix("NFe")
    if not chave:
        chave = _txt_xml(raiz, ".//n:protNFe/n:infProt/n:chNFe", ns)

    emit = raiz.find(".//n:emit", ns)
    cabecalho = {
        "chave_nf": chave,
        "numero_nf": _txt_xml(raiz.find(".//n:ide", ns), "n:nNF", ns),
        "fornecedor": _txt_xml(emit, "n:xNome", ns),
        "fornecedor_cnpj": _txt_xml(emit, "n:CNPJ", ns),
    }

    itens: list[dict] = []
    for det in inf.findall("n:det", ns):
        prod = det.find("n:prod", ns)
        if prod is None:
            continue
        descricao = _txt_xml(prod, "n:xProd", ns)
        valor = decimal(_txt_xml(prod, "n:vUnCom", ns))
        qtd_comercial = inteiro(decimal(_txt_xml(prod, "n:qCom", ns)), 0)
        do_adicional = _extrair_do_texto(_txt_xml(det, "n:infAdProd", ns))
        da_descricao = _extrair_do_texto(descricao)

        base = {
            "xProd": descricao,
            "cEAN": _txt_xml(prod, "n:cEAN", ns),
            "vUnCom": valor,
            "nLote": do_adicional["nLote"] or da_descricao["nLote"],
            "dFab": do_adicional["dFab"] or da_descricao["dFab"],
            "dVal": do_adicional["dVal"] or da_descricao["dVal"],
        }

        rastros = prod.findall("n:rastro", ns)
        if rastros:
            for rastro in rastros:
                itens.append(base | {
                    "nLote": _txt_xml(rastro, "n:nLote", ns) or base["nLote"],
                    "dFab": data_iso(_txt_xml(rastro, "n:dFab", ns)) or base["dFab"],
                    "dVal": data_iso(_txt_xml(rastro, "n:dVal", ns)) or base["dVal"],
                    "qtd_total": inteiro(decimal(_txt_xml(rastro, "n:qLote", ns)), 0)
                                 or do_adicional["qtd"] or qtd_comercial,
                })
        else:
            itens.append(base | {
                "qtd_total": do_adicional["qtd"] or da_descricao["qtd"] or qtd_comercial
            })

    if not itens:
        return False, "Nenhum item encontrado na NF-e."

    agrupados: dict[tuple, dict] = {}
    for item in itens:
        chave_grupo = (item["xProd"], item["cEAN"], item["nLote"], item["dFab"], item["dVal"], item["vUnCom"])
        if chave_grupo in agrupados:
            agrupados[chave_grupo]["qtd_total"] += item["qtd_total"]
        else:
            agrupados[chave_grupo] = dict(item)

    lista = list(agrupados.values())
    marcar_lote_como_serie(lista)
    return True, {"cabecalho": cabecalho, "itens": lista}


def marcar_lote_como_serie(itens: list[dict]) -> None:
    """nov/2026 — notas que trazem o NÚMERO DE SÉRIE no campo lote.

    Alguns fornecedores (ex.: lentes intraoculares) mandam no `<rastro>` um
    "lote" por unidade: o mesmo produto aparece com vários lotes diferentes,
    cada um com quantidade 1 (0000002545, 0000002546...). Isso é número de
    série. Quando o produto (descrição + cEAN) tem 2 ou mais lotes e todos com
    quantidade 1, cada item é marcado com `lote_e_serie`: na entrada o valor
    vai também para o número de série (o lote continua igual ao da NF).
    """
    por_produto: dict[tuple, list[dict]] = {}
    for item in itens:
        item.setdefault("lote_e_serie", 0)
        if texto(item.get("nLote")):
            por_produto.setdefault((item["xProd"], item["cEAN"]), []).append(item)
    for grupo in por_produto.values():
        lotes = {texto(i["nLote"]) for i in grupo}
        if len(grupo) >= 2 and len(lotes) == len(grupo) and all(int(i["qtd_total"] or 0) == 1 for i in grupo):
            for i in grupo:
                i["lote_e_serie"] = 1


def importar_nfe(conteudo: bytes, usuario: str) -> tuple[bool, str, str]:
    ok, resultado = ler_xml_nfe(conteudo)
    if not ok:
        return False, str(resultado), ""

    cabecalho = resultado["cabecalho"]
    chave = cabecalho["chave_nf"]
    if not chave:
        return False, "Não foi possível identificar a chave da NF-e.", ""

    ja_existe = db.consultar_um("SELECT chave_nf FROM notas_fiscais WHERE chave_nf = ?", (chave,))
    if ja_existe:
        return True, "Esta NF já havia sido importada. Abrindo os itens pendentes.", chave

    agora = db.agora()
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO notas_fiscais
               (chave_nf, numero_nf, fornecedor, fornecedor_cnpj, data_importacao, usuario)
               VALUES (?,?,?,?,?,?)""",
            (chave, cabecalho["numero_nf"], cabecalho["fornecedor"],
             cabecalho.get("fornecedor_cnpj", ""), agora, usuario),
        )
        for item in resultado["itens"]:
            conn.execute(
                """INSERT INTO nf_itens
                   (id_item, chave_nf, xProd, cEAN, nLote, dFab, dVal, vUnCom,
                    qtd_total, qtd_pendente, criado_em, lote_e_serie)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (gerar_id("IT"), chave, item["xProd"], item["cEAN"], item["nLote"],
                 item["dFab"], item["dVal"], item["vUnCom"],
                 item["qtd_total"], item["qtd_total"], agora, int(item.get("lote_e_serie") or 0)),
            )
        db.registrar_evento(conn, tipo="nf_importada", usuario=usuario,
                            observacao=f"NF {cabecalho['numero_nf']} · {cabecalho['fornecedor']}")

    return True, f"NF {cabecalho['numero_nf']} importada com {len(resultado['itens'])} item(ns).", chave


def _item_lote_e_serie(item) -> bool:
    try:
        return bool(int(item["lote_e_serie"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def notas_com_pendencia() -> list[dict]:
    return db.consultar(
        """SELECT n.chave_nf, n.numero_nf, n.fornecedor, n.data_importacao,
                  SUM(i.qtd_pendente) AS pendentes, SUM(i.qtd_total) AS total
           FROM notas_fiscais n JOIN nf_itens i ON i.chave_nf = n.chave_nf
           GROUP BY n.chave_nf HAVING pendentes > 0
           ORDER BY n.data_importacao DESC"""
    )


# v17: textos que algumas NF-e trazem no lugar do lote quando o fornecedor não
# informa (ex.: "S"). Não são lote de verdade — a entrada pede o da embalagem.
LOTES_INVALIDOS = {"S", "SL", "SN", "NA", "NAO", "SEM", "SEMLOTE", "NI", "X", "0", "00", "000"}


def lote_informado(valor) -> bool:
    import re as _re
    limpo = _re.sub(r"[^0-9A-Z]", "", texto(valor).upper())
    return len(limpo) >= 2 and limpo not in LOTES_INVALIDOS


def situacao_exclusao_nota(chave_nf: str) -> dict:
    """v17 — o que acontece se esta nota for excluída.

    Só dá para excluir enquanto nada da nota foi movimentado: unidades que já
    entraram e continuam paradas no almoxarifado (sem uso, sem caixa, sem outro
    movimento) têm a entrada estornada; se alguma já andou, a exclusão é recusada.
    """
    unidades = db.consultar(
        """SELECT u.id_unidade, u.status, u.id_caixa,
                  (SELECT COUNT(*) FROM eventos e WHERE e.id_unidade = u.id_unidade
                     AND e.tipo NOT IN ('entrada_nf', 'correcao')) AS outros
           FROM unidades u WHERE u.chave_nf = ?""", (texto(chave_nf),))
    movimentadas = [u for u in unidades
                    if u["status"] != EM_ESTOQUE_RECEBIMENTO or texto(u["id_caixa"]) or u["outros"]]
    return {"recebidas": len(unidades), "movimentadas": len(movimentadas),
            "pode_excluir": not movimentadas}


def excluir_nota(chave_nf: str, usuario: str, motivo: str) -> tuple[bool, str]:
    """v17 — exclui uma NF importada por engano (para importar a certa)."""
    nota_fiscal = nota(chave_nf)
    if not nota_fiscal:
        return False, "Nota não encontrada."
    if not texto(motivo):
        return False, "Informe o motivo da exclusão."
    situacao = situacao_exclusao_nota(chave_nf)
    if not situacao["pode_excluir"]:
        return False, (f"Não é possível excluir: {situacao['movimentadas']} unidade(s) desta nota já "
                       f"foram movimentadas (usadas, em caixa ou com outro registro). Corrija essas "
                       f"unidades pela correção de cadastro ou fale com a administração.")
    agora = db.agora()
    with db.transacao() as conn:
        unidades = conn.execute("SELECT id_unidade FROM unidades WHERE chave_nf = ?",
                                (nota_fiscal["chave_nf"],)).fetchall()
        for (id_unidade,) in unidades:
            conn.execute(
                "UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?",
                (BAIXADO, agora, usuario, id_unidade))
            db.registrar_evento(
                conn, tipo="estorno_entrada_nf", id_unidade=id_unidade,
                status_anterior=EM_ESTOQUE_RECEBIMENTO, status_novo=BAIXADO, usuario=usuario,
                motivo=f"NF {nota_fiscal['numero_nf']} excluída: {texto(motivo)}",
                observacao="Entrada estornada — a unidade sai do estoque")
        conn.execute("DELETE FROM nf_itens WHERE chave_nf = ?", (nota_fiscal["chave_nf"],))
        conn.execute("DELETE FROM notas_fiscais WHERE chave_nf = ?", (nota_fiscal["chave_nf"],))
        db.registrar_evento(
            conn, tipo="nf_excluida", usuario=usuario, motivo=texto(motivo),
            observacao=(f"NF {nota_fiscal['numero_nf']} · {nota_fiscal['fornecedor']} · chave "
                        f"{nota_fiscal['chave_nf']} · {len(unidades)} unidade(s) com entrada estornada"))
    extra = f" {len(unidades)} unidade(s) que já tinham entrado saíram do estoque." if unidades else ""
    return True, (f"NF {nota_fiscal['numero_nf']} excluída.{extra} Se precisar, importe o XML "
                  f"correto de novo.")


def itens_da_nota(chave_nf: str) -> list[dict]:
    return db.consultar(
        "SELECT * FROM nf_itens WHERE chave_nf = ? ORDER BY xProd, nLote", (chave_nf,)
    )


def item_da_nota(id_item: str) -> dict | None:
    return db.consultar_um("SELECT * FROM nf_itens WHERE id_item = ?", (texto(id_item),))


def nota(chave_nf: str) -> dict | None:
    return db.consultar_um("SELECT * FROM notas_fiscais WHERE chave_nf = ?", (chave_nf,))


def dar_entrada_item_nf(dados: dict, usuario: str) -> tuple[bool, str]:
    """Transforma a quantidade pendente de um item de NF em unidades rastreáveis."""
    item = db.consultar_um("SELECT * FROM nf_itens WHERE id_item = ?", (texto(dados.get("id_item")),))
    if not item:
        return False, "Item de NF não encontrado."

    quantidade = inteiro(dados.get("quantidade"), 0)
    if quantidade <= 0:
        return False, "Informe a quantidade a receber."
    if quantidade > item["qtd_pendente"]:
        return False, f"Quantidade acima do pendente ({item['qtd_pendente']} unidade(s))."

    # Muito OPME chega pela NF sem código de barras na embalagem. O lote vem da
    # própria nota, então basta o AGHU para montar o código interno.
    if not texto(dados.get("codigo_aghu")):
        return False, "Informe o código AGHU."
    # v17: se a NF traz o cEAN, ele É o código de barras — a tela mostra o campo
    # travado e aqui ignoramos o que vier do formulário, para ninguém apagar ou
    # trocar o código achando que "não bate" com a embalagem (a etiqueta da
    # embalagem traz o cEAN mais validade e lote; o sistema separa na leitura).
    # v17: lote/validade que a NF não trouxe são digitados na entrada (ou vêm da
    # etiqueta GS1 bipada no campo do código de barras).
    from .. import gs1
    etiqueta = gs1.interpretar(dados.get("codigo_barras")) or {}
    lote = texto(item["nLote"])
    validade = texto(item["dVal"])
    digitados = []
    if not lote_informado(lote):
        lote = texto(dados.get("nLote_manual")) or texto(etiqueta.get("lote"))
        if not lote_informado(lote):
            return False, ("A NF não informa o lote deste item. Digite o lote que está na "
                           "embalagem (campo “Lote”).")
        digitados.append("lote")
    if not validade:
        # v18: validade obrigatória (saiu a opção "material sem validade").
        bruto = texto(dados.get("dVal_manual"))
        validade = data_iso(bruto) if bruto else texto(etiqueta.get("validade"))
        if bruto and not validade:
            return False, "Validade inválida. Use dd/mm/aaaa."
        if not validade:
            return False, "A NF não informa a validade deste item. Digite a validade da embalagem."
        digitados.append("validade")

    cean = cean_utilizavel(item["cEAN"])
    if cean:
        dados = dict(dados) | {"codigo_barras": cean, "sem_codigo_barras": ""}
    dados = aplicar_codigo_interno(dict(dados) | {"nLote": lote})

    codigo_barras = normalizar_codigo(dados.get("codigo_barras"))
    if not codigo_barras:
        return False, ("Bipe o código de barras da embalagem, ou marque "
                       "“item sem código de barras” para gerar um código e a etiqueta QR.")
    if not texto(dados.get("marca_fabricante")):
        return False, "Informe a marca/fabricante."

    nota_fiscal = nota(item["chave_nf"]) or {}
    tipo_entrada = normalizar_tipo_entrada(dados.get("tipo_entrada"))
    ok_consignado, codigo_consignado = codigo_consignado_valido(tipo_entrada, dados.get("codigo_consignado"),
                                                                       dados.get("codigo_aghu"), dados.get("fornecedor"))
    if not ok_consignado:
        return False, codigo_consignado
    fornecedor = texto(dados.get("fornecedor")) or texto(nota_fiscal.get("fornecedor"))
    numeros_serie = [texto(s) for s in (dados.get("numeros_serie") or "").splitlines() if texto(s)]
    if numeros_serie and len(numeros_serie) != quantidade:
        return False, "A quantidade de números de série não bate com a quantidade recebida."
    # nov/2026: a NF trouxe o número de série no campo lote (ver marcar_lote_como_serie).
    if not numeros_serie and quantidade == 1 and _item_lote_e_serie(item) and lote_informado(texto(item["nLote"])):
        numeros_serie = [texto(item["nLote"])]

    # Nome oficial do material, se o catálogo mestre conhece este código AGHU
    # — vem da própria referência do hospital, não de um palpite.
    descritivo_hospital = descritivo_para_unidade(tipo_entrada, codigo_consignado, dados.get("codigo_aghu"),
                                                  item["xProd"])

    agora = db.agora()
    with db.transacao() as conn:
        for indice in range(quantidade):
            id_unidade = gerar_id("U")
            conn.execute(
                """INSERT INTO unidades
                   (id_unidade, codigo_barras, codigo_aghu, xProd, marca_fabricante, fornecedor,
                    nLote, numero_serie, dFab, dVal, vUnCom, cEAN, origem, chave_nf, numero_nf,
                    id_item_nf, tipo_entrada, status, descritivo_hospital, criado_em, criado_por,
                    atualizado_em, atualizado_por, codigo_consignado)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'xml',?,?,?,?,?,?,?,?,?,?,?)""",
                (id_unidade, codigo_barras, texto(dados.get("codigo_aghu")), item["xProd"],
                 texto(dados.get("marca_fabricante")), fornecedor, lote,
                 numeros_serie[indice] if numeros_serie else "",
                 item["dFab"], validade or None, item["vUnCom"], item["cEAN"],
                 item["chave_nf"], texto(nota_fiscal.get("numero_nf")), item["id_item"],
                 tipo_entrada, EM_ESTOQUE_RECEBIMENTO, descritivo_hospital,
                 agora, usuario, agora, usuario, codigo_consignado),
            )
            db.registrar_evento(
                conn, tipo="entrada_nf", id_unidade=id_unidade,
                status_novo=EM_ESTOQUE_RECEBIMENTO, usuario=usuario,
                observacao=(f"NF {nota_fiscal.get('numero_nf')} · {item['xProd']}"
                            + (f" · {' e '.join(digitados)} digitado(s) na entrada (a NF não trouxe)"
                               if digitados else "")),
            )
        conn.execute(
            "UPDATE nf_itens SET qtd_pendente = qtd_pendente - ? WHERE id_item = ?",
            (quantidade, item["id_item"]),
        )
        _registrar_historico(
            conn, codigo=texto(item.get("cEAN")) or codigo_barras, xProd=item["xProd"],
            codigo_aghu=dados.get("codigo_aghu"), marca_fabricante=dados.get("marca_fabricante"),
            fornecedor_cnpj=nota_fiscal.get("fornecedor_cnpj"), fornecedor=fornecedor,
            usuario=usuario,
        )

    return True, f"{quantidade} unidade(s) recebida(s) e disponível(is) no Almoxarifado."


# =========================================================
# CORREÇÕES
# =========================================================

CAMPOS_EDITAVEIS = {
    "xProd": "Descrição",
    "codigo_barras": "Código de barras",
    "codigo_aghu": "Código AGHU",
    "marca_fabricante": "Marca/Fabricante",
    "fornecedor": "Fornecedor",
    "nLote": "Lote",
    "numero_serie": "Nº de série",
    "dFab": "Fabricação",
    "dVal": "Validade",
    "vUnCom": "Valor unitário",
    "tipo_entrada": "Classificação",
    "codigo_consignado": "Código consignado",
    "descritivo_hospital": "Descritivo do hospital",
}


def _normalizar_campo(campo: str, valor):
    """Mesma forma de gravar um campo, venha da correção individual ou em lote."""
    if campo in ("dFab", "dVal"):
        return data_iso(valor)
    if campo == "vUnCom":
        return decimal(valor)
    if campo == "tipo_entrada":
        return normalizar_tipo_entrada(valor)
    if campo == "codigo_barras":
        return normalizar_codigo(valor)
    return texto(valor)


def _calcular_correcao(atual: dict, dados: dict) -> tuple[dict, list[str]]:
    """O que muda nesta unidade, e a frase de auditoria de cada mudança.

    Só lê: não grava nada. Fica separado de quem grava para a correção em lote
    poder calcular tudo antes de abrir a transação — e gravar as 100 unidades de
    uma vez, ou nenhuma.
    """
    mudancas: list[str] = []
    valores: dict[str, object] = {}
    for campo, rotulo_campo in CAMPOS_EDITAVEIS.items():
        if campo not in dados:
            continue
        novo = _normalizar_campo(campo, dados.get(campo))
        if texto(novo) != texto(atual.get(campo)):
            valores[campo] = novo
            mudancas.append(f"{rotulo_campo}: “{texto(atual.get(campo)) or '—'}” → “{texto(novo) or '—'}”")

    # Corrigiu o código AGHU sem mexer no descritivo à mão? Atualiza também
    # pelo catálogo mestre — ele é determinístico por código (ao contrário de
    # marca/fabricante), então não faz sentido deixar o descritivo antigo.
    if "codigo_aghu" in valores and "descritivo_hospital" not in dados and texto(atual.get("tipo_entrada")) != "consignado":
        novo_descritivo = materiais.descritivo_hospital(valores["codigo_aghu"])
        if texto(novo_descritivo) != texto(atual.get("descritivo_hospital")):
            valores["descritivo_hospital"] = novo_descritivo
            mudancas.append(
                f"Descritivo do hospital (pelo catálogo): "
                f"“{texto(atual.get('descritivo_hospital')) or '—'}” → “{texto(novo_descritivo) or '—'}”"
            )
    return valores, mudancas


def _gravar_correcao(conn, atual: dict, valores: dict, mudancas: list[str],
                     usuario: str, motivo: str, observacao_extra: str = "") -> None:
    atribuicoes = ", ".join(f"{c} = ?" for c in valores)
    conn.execute(
        f"UPDATE unidades SET {atribuicoes}, atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?",
        (*valores.values(), db.agora(), usuario, atual["id_unidade"]),
    )
    observacao = " | ".join(mudancas)
    if observacao_extra:
        observacao = f"{observacao} | {observacao_extra}"
    db.registrar_evento(
        conn, tipo="correcao", id_unidade=atual["id_unidade"],
        id_atendimento=atual["id_atendimento"],
        status_anterior=atual["status"], status_novo=atual["status"], usuario=usuario,
        motivo=motivo, observacao=observacao,
    )
    # Corrigiu marca/fabricante ou AGHU aqui? O valor certo entra no
    # histórico de sugestões deste código de barras — sem apagar o que já
    # havia, no mesmo espírito do resto da auditoria deste sistema.
    if "marca_fabricante" in valores or "codigo_aghu" in valores:
        _registrar_historico(
            conn,
            codigo=texto(atual.get("cEAN")) or atual.get("codigo_barras"),
            xProd=atual.get("xProd"),
            codigo_aghu=valores.get("codigo_aghu", atual.get("codigo_aghu")),
            marca_fabricante=valores.get("marca_fabricante", atual.get("marca_fabricante")),
            fornecedor=atual.get("fornecedor"), usuario=usuario,
        )


def corrigir_unidade(id_unidade: str, dados: dict, usuario: str, motivo: str) -> tuple[bool, str]:
    if not texto(motivo):
        return False, "Informe o motivo da correção — ela fica registrada na auditoria."

    atual = db.consultar_um("SELECT * FROM unidades WHERE id_unidade = ?", (id_unidade,))
    if not atual:
        return False, "Unidade não encontrada."

    valores, mudancas = _calcular_correcao(atual, dados)
    if not valores:
        return False, "Nenhuma alteração informada."

    with db.transacao() as conn:
        _gravar_correcao(conn, atual, valores, mudancas, usuario, motivo)
    return True, "Correção registrada: " + " | ".join(mudancas)


# =========================================================
# CORREÇÃO EM LOTE
#
# Uma entrada manual de 100 unidades com a validade errada gerava 100 correções
# feitas uma a uma. Aqui as unidades cadastradas com os mesmos dados são
# corrigidas juntas — mas cada uma continua com o seu próprio evento de
# auditoria, com o mesmo motivo, como se tivesse sido corrigida sozinha.
# =========================================================

# O número de série fica de fora de propósito: ele é o que torna cada unidade
# única. Aplicar um valor só às 100 destruiria justamente a rastreabilidade
# individual que o número de série existe para garantir.
CAMPOS_EM_LOTE = {c: r for c, r in CAMPOS_EDITAVEIS.items() if c != "numero_serie"}

# Campos que definem "cadastradas juntas": unidades que coincidem em todos eles
# vieram, na prática, da mesma entrada — e erram juntas.
_CAMPOS_DO_GRUPO = ("xProd", "codigo_barras", "codigo_aghu", "marca_fabricante",
                    "fornecedor", "nLote", "dFab", "dVal", "vUnCom", "tipo_entrada",
                    "codigo_consignado")

LIMITE_LOTE = 2000


def grupos_para_correcao(termo: str) -> list[dict]:
    """Unidades ativas que batem com a busca, agrupadas pelo MATERIAL.

    v18.17: o agrupamento passou a ser por produto + lote + validade (a
    identidade física do material). Antes era por "todos os campos iguais": o
    mesmo lote entrava em dois, três cartões idênticos à primeira vista só
    porque o fornecedor estava escrito de um jeito numa entrada ("GMI") e de
    outro na seguinte ("Gabisa Medical"), ou porque uma tinha data de fabricação
    e a outra não — justamente o que a pessoa foi lá corrigir.

    Os campos que divergem dentro do grupo não somem: vêm vazios, com a lista do
    que está cadastrado e quantas unidades têm cada valor (`misto`), para a tela
    mostrar e a pessoa igualar de uma vez. O que ela não preencher fica como
    está em cada unidade.

    Só grupos de 2 ou mais — uma unidade sozinha se corrige pela tela de sempre.
    """
    termo = texto(termo)
    if not termo:
        return []
    cond, extra, etiqueta = busca.condicao(termo, CAMPOS_BUSCA)
    marcadores = ",".join("?" for _ in ESTOQUE_ATIVO)
    campos = ", ".join(f"u.{c}" for c in _CAMPOS_DO_GRUPO)
    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.status, u.criado_em, {campos}
            FROM unidades u
            WHERE u.status IN ({marcadores}) AND {cond}""",
        [*ESTOQUE_ATIVO, *extra],
    )
    linhas = busca.preferir_exatos(busca.refinar(linhas, etiqueta, termo), termo)

    grupos: dict[tuple, list[dict]] = {}
    for linha in linhas:
        chave = (gs1.gtin(linha.get("codigo_barras")), texto(linha.get("codigo_aghu")).upper(),
                 texto(linha.get("nLote")).upper(), texto(linha.get("dVal"))[:10])
        grupos.setdefault(chave, []).append(linha)

    saida = []
    for unidades in grupos.values():
        if len(unidades) < 2:
            continue
        grupo = {"quantidade": len(unidades),
                 "ids": sorted(texto(u["id_unidade"]) for u in unidades),
                 "situacoes": sorted({texto(u["status"]) for u in unidades if texto(u["status"])}),
                 "primeira_entrada": min(texto(u.get("criado_em")) for u in unidades),
                 "misto": {}}
        for campo in _CAMPOS_DO_GRUPO:
            valores: dict[str, int] = {}
            for u in unidades:
                valores[texto(u.get(campo))] = valores.get(texto(u.get(campo)), 0) + 1
            if len(valores) == 1:
                grupo[campo] = unidades[0].get(campo)
                continue
            # Campo cadastrado de jeitos diferentes: vai vazio e com a lista.
            grupo[campo] = ""
            grupo["misto"][campo] = [
                {"valor": valor, "quantidade": quantas}
                for valor, quantas in sorted(valores.items(), key=lambda x: (-x[1], x[0]))]
        saida.append(grupo)
    return sorted(saida, key=lambda g: (-g["quantidade"], texto(g.get("xProd"))))


def para_correcao(termo: str) -> dict:
    """v18.17: tudo o que a tela "Corrigir cadastro" mostra, coerente entre si.

    A etiqueta GS1 bipada traz o GTIN e o lote. A lista individual já era
    refinada pelo lote lido, mas os grupos não: quando o lote da etiqueta tinha
    uma unidade só (sem grupo), a tela abria com grupos de OUTROS lotes do mesmo
    produto em cima e a unidade bipada escondida dentro de "Ou corrija uma
    unidade por vez" — parecia que o código de barras não achava o item.

    Agora, quando a etiqueta aponta para unidades cadastradas, os grupos ficam
    restritos ao mesmo lote/série. Quando o lote da etiqueta não bate com nada
    (justamente o cadastro que precisa ser corrigido), nada é escondido e a tela
    recebe o aviso do `gs1.filtrar`.
    """
    from .. import gs1
    termo = texto(termo)
    if not termo:
        return {"itens": [], "grupos": [], "etiqueta": None, "aviso": ""}
    etiqueta = busca.interpretar(termo)
    itens = buscar_unidades(termo, "ativos")
    grupos = grupos_para_correcao(termo)
    aviso = ""
    if etiqueta and (etiqueta.get("lote") or etiqueta.get("serie")):
        _mesmas, aviso = gs1.filtrar(itens, etiqueta)
        if not aviso and itens:
            lotes = {texto(i.get("nLote")).upper() for i in itens}
            series = {texto(i.get("numero_serie")).upper() for i in itens}
            grupos = [g for g in grupos
                      if texto(g.get("nLote")).upper() in lotes
                      or (texto(g.get("numero_serie")).upper() in series
                          and texto(g.get("numero_serie")))]
    return {"itens": itens, "grupos": grupos, "etiqueta": etiqueta, "aviso": aviso}


def corrigir_em_lote(ids: list[str], dados: dict, originais: dict,
                     usuario: str, motivo: str) -> tuple[bool, str]:
    """Aplica a mesma correção a várias unidades: todas, ou nenhuma.

    Só vale o que a pessoa de fato mudou na tela — o campo cujo valor enviado é
    diferente do original que a tela mostrou. Isso protege de duas coisas: de
    apagar um campo que ninguém tocou, e de desfazer, sem ver, uma correção que
    outra pessoa fez numa dessas unidades enquanto esta tela estava aberta.
    """
    if not texto(motivo):
        return False, "Informe o motivo da correção — ela fica registrada na auditoria."

    ids = list(dict.fromkeys(texto(i) for i in (ids or []) if texto(i)))
    if not ids:
        return False, "Marque ao menos uma unidade para corrigir."
    if len(ids) > LIMITE_LOTE:
        return False, f"Corrija no máximo {LIMITE_LOTE} unidades por vez."

    alteracoes = {
        campo: dados[campo] for campo in CAMPOS_EM_LOTE
        if campo in dados
        and texto(_normalizar_campo(campo, dados[campo]))
            != texto(_normalizar_campo(campo, originais.get(campo, "")))
    }
    if not alteracoes:
        return False, "Nenhuma alteração informada — mude pelo menos um campo."

    marcadores = ",".join("?" for _ in ids)
    unidades = db.consultar(
        f"SELECT * FROM unidades WHERE id_unidade IN ({marcadores})", ids)
    if len(unidades) != len(ids):
        return False, "Alguma unidade selecionada não existe mais. Atualize a busca e tente de novo."
    fora = [u["id_unidade"] for u in unidades if u["status"] not in ESTOQUE_ATIVO]
    if fora:
        return False, (f"{len(fora)} unidade(s) já saíram do estoque ativo desde que a "
                       f"tela foi aberta (ex.: {fora[0]}). Atualize a busca e tente de novo.")

    # Tudo calculado antes de abrir a transação: a consulta ao catálogo (quando
    # muda o AGHU) usa conexão própria e não pode acontecer no meio da escrita.
    planos = []
    for unidade in unidades:
        valores, mudancas = _calcular_correcao(unidade, alteracoes)
        if valores:
            planos.append((unidade, valores, mudancas))
    if not planos:
        return False, "As unidades selecionadas já estão com esses valores."

    nota = f"correção em lote de {len(planos)} unidade(s)"
    with db.transacao() as conn:
        for unidade, valores, mudancas in planos:
            _gravar_correcao(conn, unidade, valores, mudancas, usuario, motivo, nota)

    resumo = " | ".join(planos[0][2])
    ja_certas = len(unidades) - len(planos)
    mensagem = f"{len(planos)} unidade(s) corrigida(s): {resumo}"
    if ja_certas:
        mensagem += f" ({ja_certas} já estava(m) com esses valores e não foi(ram) alterada(s))."
    return True, mensagem


# =========================================================
# nov/2026 — EXCLUIR CADASTRO ERRADO E AJUSTAR A QUANTIDADE
#
# Um item cadastrado por engano (produto errado, entrada em dobro, quantidade
# a mais) sai do estoque pela tela "Corrigir cadastro". Como em todo o sistema,
# nada é apagado: a unidade fica "Baixado", com um evento próprio
# (`cadastro_excluido`) que diz quem excluiu, quando e por quê — e não entra
# nos indicadores de perda, que contam só as baixas de verdade.
#
# Só se exclui o que ainda não andou: parado no almoxarifado, fora de caixa,
# sem envio, sem paciente, sem empenho e sem nenhum movimento além da entrada
# e de correções. O que já se movimentou se resolve pelas telas do fluxo.
# =========================================================

EVENTOS_DE_ENTRADA = ("entrada_manual", "entrada_nf", "entrada_planilha", "correcao")


def motivos_bloqueio_exclusao(ids: list[str]) -> dict[str, str]:
    """{id_unidade: por que não pode ser excluída} — só as que não podem."""
    ids = [texto(i) for i in ids if texto(i)]
    if not ids:
        return {}
    marcadores = ",".join("?" for _ in ids)
    eventos = ",".join("?" for _ in EVENTOS_DE_ENTRADA)
    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.status, u.id_caixa, u.caixa_destino, u.id_atendimento, u.farmacia,
                   (SELECT COUNT(*) FROM eventos e WHERE e.id_unidade = u.id_unidade
                      AND e.tipo NOT IN ({eventos})) AS movimentos,
                   (SELECT COUNT(*) FROM remessa_itens r WHERE r.id_unidade = u.id_unidade
                      AND r.situacao <> 'removido') AS envios,
                   (SELECT COUNT(*) FROM empenho_vinculos v WHERE v.id_unidade = u.id_unidade
                      AND v.status = 'ativo') AS empenhos
            FROM unidades u WHERE u.id_unidade IN ({marcadores})""",
        [*EVENTOS_DE_ENTRADA, *ids])
    motivos: dict[str, str] = {}
    achadas = set()
    for u in linhas:
        achadas.add(u["id_unidade"])
        if u["status"] != EM_ESTOQUE_RECEBIMENTO:
            from ..domain import rotulo
            motivos[u["id_unidade"]] = f"não está parada no almoxarifado ({rotulo(u['status'])})"
        elif texto(u["id_caixa"]) or texto(u["caixa_destino"]):
            motivos[u["id_unidade"]] = "está (ou vai) dentro de uma caixa"
        elif texto(u["id_atendimento"]) or texto(u["farmacia"]):
            motivos[u["id_unidade"]] = "já foi para farmácia ou paciente"
        elif u["envios"]:
            motivos[u["id_unidade"]] = "já entrou num envio para a farmácia"
        elif u["empenhos"]:
            motivos[u["id_unidade"]] = "está vinculada a um empenho"
        elif u["movimentos"]:
            motivos[u["id_unidade"]] = "já tem movimentação registrada além da entrada"
    for i in ids:
        if i not in achadas:
            motivos[i] = "unidade não encontrada"
    return motivos


def _excluir_no_banco(conn, unidade: dict, usuario: str, motivo: str, observacao: str) -> None:
    conn.execute(
        "UPDATE unidades SET status = ?, atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?",
        (BAIXADO, db.agora(), usuario, unidade["id_unidade"]))
    db.registrar_evento(
        conn, tipo="cadastro_excluido", id_unidade=unidade["id_unidade"],
        status_anterior=unidade["status"], status_novo=BAIXADO, usuario=usuario,
        motivo=motivo, observacao=observacao)
    # Entrada pela NF: a unidade volta a ficar pendente no item da nota, para
    # poder ser recebida de novo com os dados certos.
    if texto(unidade.get("id_item_nf")):
        conn.execute("UPDATE nf_itens SET qtd_pendente = qtd_pendente + 1 WHERE id_item = ?",
                     (unidade["id_item_nf"],))


def excluir_unidades(ids: list[str], usuario: str, motivo: str) -> tuple[bool, str]:
    """Exclui do estoque unidades cadastradas por engano: todas, ou nenhuma."""
    if not texto(motivo) or len(texto(motivo)) < 5:
        return False, "Informe o motivo da exclusão (mínimo de 5 caracteres) — ele fica no histórico."
    ids = list(dict.fromkeys(texto(i) for i in (ids or []) if texto(i)))
    if not ids:
        return False, "Marque ao menos uma unidade para excluir."
    if len(ids) > LIMITE_LOTE:
        return False, f"Exclua no máximo {LIMITE_LOTE} unidades por vez."
    bloqueios = motivos_bloqueio_exclusao(ids)
    if bloqueios:
        primeiro, porque = next(iter(bloqueios.items()))
        return False, (f"Não é possível excluir {len(bloqueios)} da(s) {len(ids)} unidade(s): "
                       f"{primeiro} {porque}. Só se exclui cadastro que ainda não se movimentou; "
                       f"o resto se corrige pelas telas do fluxo (ex.: Baixar, Devolver ao fornecedor).")
    marcadores = ",".join("?" for _ in ids)
    unidades = db.consultar(f"SELECT * FROM unidades WHERE id_unidade IN ({marcadores})", ids)
    nota = f"cadastro excluído ({len(unidades)} unidade(s) de uma vez)" if len(unidades) > 1 else "cadastro excluído"
    with db.transacao() as conn:
        for u in unidades:
            _excluir_no_banco(conn, u, usuario, texto(motivo),
                              f"{nota} · {texto(u['xProd'])} · lote {texto(u['nLote']) or '—'}")
    voltam_nf = sum(1 for u in unidades if texto(u.get("id_item_nf")))
    extra = (f" {voltam_nf} unidade(s) voltaram a ficar pendentes na nota fiscal, para receber de novo."
             if voltam_nf else "")
    return True, (f"{len(unidades)} unidade(s) excluída(s) do estoque. O registro continua no histórico "
                  f"de cada uma, com o motivo.{extra}")


def ajustar_quantidade(ids: list[str], nova_quantidade, usuario: str, motivo: str) -> tuple[bool, str]:
    """Corrige a quantidade de um cadastro feito de uma vez (unidades idênticas).

    Para menos: exclui as unidades a mais (as últimas cadastradas), com as
    mesmas regras da exclusão. Para mais: cria as unidades que faltaram com os
    mesmos dados — só para cadastro manual; entrada por NF ou planilha se
    completa pela própria NF/planilha.
    """
    if not texto(motivo) or len(texto(motivo)) < 5:
        return False, "Informe o motivo do ajuste (mínimo de 5 caracteres) — ele fica no histórico."
    if not texto(nova_quantidade):
        return False, "Informe a quantidade correta."
    nova = inteiro(nova_quantidade, -1)
    if nova < 0:
        return False, "Quantidade inválida."
    ids = list(dict.fromkeys(texto(i) for i in (ids or []) if texto(i)))
    if not ids:
        return False, "Nenhuma unidade informada."
    marcadores = ",".join("?" for _ in ids)
    unidades = db.consultar(
        f"SELECT * FROM unidades WHERE id_unidade IN ({marcadores}) ORDER BY criado_em DESC, id_unidade DESC", ids)
    if len(unidades) != len(ids):
        return False, "Alguma unidade não existe mais. Atualize a busca e tente de novo."
    fora = [u for u in unidades if u["status"] not in ESTOQUE_ATIVO]
    if fora:
        return False, "Alguma unidade já saiu do estoque desde que a tela foi aberta. Atualize a busca."
    atual = len(unidades)
    if nova == atual:
        return False, f"A quantidade já é {atual}."
    if nova > 500 or nova - atual > 500:
        return False, "Quantidade acima do limite de 500 unidades por cadastro."

    if nova < atual:
        sobrando = atual - nova
        bloqueios = motivos_bloqueio_exclusao([u["id_unidade"] for u in unidades])
        livres = [u for u in unidades if u["id_unidade"] not in bloqueios]
        if len(livres) < sobrando:
            return False, (f"Só {len(livres)} destas {atual} unidades ainda podem ser excluídas (as outras já "
                           f"se movimentaram). Para chegar a {nova}, seria preciso excluir {sobrando}.")
        with db.transacao() as conn:
            for u in livres[:sobrando]:
                _excluir_no_banco(conn, u, usuario, texto(motivo),
                                  f"ajuste de quantidade: {atual} → {nova} · {texto(u['xProd'])} · "
                                  f"lote {texto(u['nLote']) or '—'}")
        return True, (f"Quantidade ajustada de {atual} para {nova}: {sobrando} unidade(s) excluída(s) do "
                      f"estoque, com o motivo no histórico.")

    modelo = unidades[-1]  # a primeira cadastrada
    if any(texto(u["origem"]) != "manual" for u in unidades):
        return False, ("Para aumentar a quantidade de material que entrou por nota fiscal ou planilha, "
                       "dê entrada nas unidades que faltam pela própria NF/planilha (ou pelo cadastro manual).")
    faltam = nova - atual
    agora = db.agora()
    with db.transacao() as conn:
        for _ in range(faltam):
            id_unidade = gerar_id("U")
            conn.execute(
                """INSERT INTO unidades
                   (id_unidade, codigo_barras, codigo_aghu, xProd, marca_fabricante, fornecedor,
                    nLote, numero_serie, dFab, dVal, vUnCom, cEAN, origem, chave_nf, numero_nf,
                    tipo_entrada, status, descritivo_hospital, criado_em, criado_por,
                    atualizado_em, atualizado_por, codigo_consignado)
                   VALUES (?,?,?,?,?,?,?,'',?,?,?,?,'manual',?,?,?,?,?,?,?,?,?,?)""",
                (id_unidade, modelo["codigo_barras"], modelo["codigo_aghu"], modelo["xProd"],
                 modelo["marca_fabricante"], modelo["fornecedor"], modelo["nLote"], modelo["dFab"],
                 modelo["dVal"], modelo["vUnCom"], modelo["cEAN"] or "", modelo["chave_nf"], modelo["numero_nf"],
                 modelo["tipo_entrada"], EM_ESTOQUE_RECEBIMENTO, modelo["descritivo_hospital"],
                 agora, usuario, agora, usuario, modelo.get("codigo_consignado") or ""))
            db.registrar_evento(
                conn, tipo="entrada_manual", id_unidade=id_unidade,
                status_novo=EM_ESTOQUE_RECEBIMENTO, usuario=usuario, motivo=texto(motivo),
                observacao=(f"ajuste de quantidade: {atual} → {nova} · {texto(modelo['xProd'])} · "
                            f"lote {texto(modelo['nLote']) or '—'} (mesmos dados de {modelo['id_unidade']})"))
    return True, f"Quantidade ajustada de {atual} para {nova}: {faltam} unidade(s) incluída(s) com os mesmos dados."


# Colunas da busca por texto nas telas (Itens, Corrigir cadastro, Etiquetas).
CAMPOS_BUSCA = ["u.codigo_barras", "u.xProd", "u.nLote", "u.fornecedor", "u.id_unidade",
                "u.codigo_aghu", "u.numero_serie", "COALESCE(u.codigo_consignado, '')",
                "COALESCE(u.descritivo_hospital, '')"]


def buscar_unidades(termo: str = "", status: str = "", limite: int = 300) -> list[dict]:
    cond_termo, params_termo = "1=1", []
    cond_status, params_status = "1=1", []
    termo = texto(termo)
    etiqueta = None
    if termo:
        # nov/2026: entende o código bipado (etiqueta GS1 inteira) como a bipagem.
        cond_termo, params_termo, etiqueta = busca.condicao(termo, CAMPOS_BUSCA)
    if status == "ativos":
        cond_status = "u.status IN (" + ",".join("?" for _ in ESTOQUE_ATIVO) + ")"
        params_status = list(ESTOQUE_ATIVO)
    elif ":" in texto(status):
        # "em_estoque_farmacia:BLOCO CIRURGICO" — situação numa farmácia só.
        st, farm = texto(status).split(":", 1)
        cond_status, params_status = "u.status = ? AND u.farmacia = ?", [st, farm]
    elif texto(status):
        cond_status, params_status = "u.status = ?", [status]

    def consultar(cond: str, params: list) -> list[dict]:
        return db.consultar(
            f"""SELECT u.*, a.prontuario, a.sala, a.data_procedimento
                FROM unidades u LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                WHERE {cond} AND {cond_status}
                ORDER BY u.xProd, u.dVal, u.nLote LIMIT ?""",
            params + params_status + [limite])

    linhas = consultar(cond_termo, params_termo)
    return busca.preferir_exatos(busca.refinar(linhas, etiqueta, termo), termo)


def local_da_unidade(u: dict) -> str:
    """Onde a unidade está fisicamente, em palavras: almoxarifado, qual farmácia ou sala."""
    from ..config import rotulo_farmacia
    from ..domain import EM_ESTOQUE_FARMACIA as _EF, EM_ESTOQUE_RECEBIMENTO as _ER, TRANSITO_FARMACIA as _TF
    st = u.get("status")
    if st in (_ER, DIVERGENCIA_LOCAL):
        return "Almoxarifado"
    if st == _EF:
        return rotulo_farmacia(u.get("farmacia"))
    if st == _TF:
        return "a caminho da " + rotulo_farmacia(u.get("farmacia"))
    if st == "transito_almoxarifado":
        return "voltando da " + rotulo_farmacia(u.get("farmacia")) + " para o almoxarifado"
    if u.get("sala"):
        return f"Sala {u['sala']}"
    return "—"


DIVERGENCIA_LOCAL = "divergencia"


def estoque_consolidado(status: str, termo: str = "", farmacia: str = "") -> list[dict]:
    """Visão por produto/lote/validade — é assim que a farmácia enxerga o estoque."""
    params: list = [status]
    filtro = ""
    if texto(farmacia):
        # Os estoques das duas farmácias satélites são separados.
        filtro += " AND farmacia = ?"
        params.append(texto(farmacia))
    etiqueta = None
    cond_termo, params_termo = "", []
    if texto(termo):
        cond_termo, params_termo, etiqueta = busca.condicao(
            termo, ["codigo_barras", "xProd", "nLote", "fornecedor", "codigo_aghu"], alias="")

    def consultar(cond: str, extra: list) -> list[dict]:
        return db.consultar(
            f"""SELECT codigo_aghu, codigo_barras, xProd, nLote, dVal, fornecedor, marca_fabricante,
                       COUNT(*) AS quantidade, MIN(criado_em) AS entrada_mais_antiga
                FROM unidades WHERE status = ?{filtro}{(' AND ' + cond) if cond else ''}
                GROUP BY codigo_aghu, codigo_barras, xProd, nLote, dVal, fornecedor, marca_fabricante
                ORDER BY (dVal IS NULL OR dVal = ''), dVal, xProd""",
            params + extra)

    linhas = consultar(cond_termo, params_termo)
    return busca.preferir_exatos(busca.refinar(linhas, etiqueta, termo), termo)


def estoque_consolidado_detalhado(status: str, termo: str = "", farmacia: str = "") -> dict:
    """v18.23: o mesmo estoque, dizendo quando o LOTE da etiqueta não está aqui.

    Caso real (HC-UFPE, 18/11/2026): a etiqueta do lote SP1024120503 trazia
    "10 unidade(s) em estoque" — mas as 10 eram de OUTRO lote do mesmo produto,
    e o lote bipado estava todo no almoxarifado. A tela precisa dizer isso, em
    vez de mostrar outro lote como se fosse o da etiqueta.
    """
    from ..domain import rotulo
    linhas = estoque_consolidado(status, termo, farmacia)
    etiqueta = gs1.interpretar(texto(termo)) if texto(termo) else None
    vazio = {"linhas": linhas, "aviso": "", "etiqueta": etiqueta, "onde": []}
    if not etiqueta or not etiqueta.get("lote") or not linhas:
        return vazio
    _do_lote, aviso = gs1.filtrar(linhas, etiqueta)
    if not aviso:                       # o lote da etiqueta está nesta lista
        return vazio
    onde: dict[str, int] = {}
    for u in buscar_unidades(termo):            # sem filtro de situação: onde o lote está
        chave = texto(u.get("status"))
        if chave:
            onde[chave] = onde.get(chave, 0) + 1
    lote = etiqueta.get("lote_curto") or etiqueta["lote"]
    return {
        "linhas": linhas, "etiqueta": etiqueta,
        "onde": [{"status": s, "rotulo": rotulo(s), "quantidade": n}
                 for s, n in sorted(onde.items(), key=lambda kv: -kv[1])],
        "aviso": (f"Nenhuma unidade do lote {lote} (o lote desta etiqueta) está no estoque desta "
                  f"farmácia. O que aparece abaixo são OUTROS lotes do mesmo produto."),
    }
