"""Descritivo oficial do material do hospital, pelo código AGHU.

O hospital tem seu próprio nome para cada material (diferente do texto que o
fornecedor usa na NF-e, ou do que alguém digita no cadastro manual), definido
numa planilha própria de licitações. Essa associação é estável — o mesmo AGHU
sempre corresponde ao mesmo descritivo, e só muda quando um material novo é
adquirido fora dessa lista. Por isso não tem tela de importação aqui: a tabela
`materiais_mestre` é carregada uma vez e atualizada sob demanda.
"""

from .. import db
from ..utils import texto


def descritivo_hospital(codigo_aghu: str) -> str:
    """Nome oficial do material para este código AGHU, se for conhecido."""
    codigo_aghu = texto(codigo_aghu).strip()
    if not codigo_aghu:
        return ""
    linha = db.consultar_um(
        "SELECT descritivo_hospital FROM materiais_mestre WHERE codigo_aghu = ?",
        (codigo_aghu,),
    )
    return texto(linha["descritivo_hospital"]) if linha else ""


def codigo_master(codigo_aghu: str) -> str:
    """v18: código master do material (vem da planilha MasterTools ou da
    relação AGHU → master). Vazio quando não se conhece."""
    m = material(codigo_aghu)
    return _codigo_master(m["codigo_master"]) if m and m.get("codigo_master") else ""


def material(codigo_aghu: str) -> dict | None:
    """Linha completa do catálogo para este código, se existir."""
    codigo_aghu = texto(codigo_aghu).strip()
    if not codigo_aghu:
        return None
    return db.consultar_um(
        "SELECT * FROM materiais_mestre WHERE codigo_aghu = ?", (codigo_aghu,)
    )


# =========================================================
# ATUALIZAÇÃO PELA PLANILHA (tela de Administração)
#
# A planilha de licitações vigentes (MasterTools) muda de tempos em tempos. O
# administrador sobe o arquivo como ele sai do sistema — .xlsx ou .csv — e o
# catálogo é atualizado por MESCLAGEM:
#   · código novo entra;
#   · código que já existia e mudou (descrição, valor, código master) é atualizado;
#   · código que sumiu da planilha NÃO é apagado — material que ainda chega com
#     um código antigo continua mostrando a descrição que ele tinha.
# Unidades que já deram entrada guardam a descrição da época em que entraram:
# atualizar o catálogo não reescreve o passado.
# =========================================================

import csv
import io
import re
import zipfile
from xml.etree import ElementTree

from .. import log
from ..utils import decimal, sem_acento

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


class PlanilhaInvalida(Exception):
    pass


def _linhas_xlsx(conteudo: bytes) -> list[list[str]]:
    """Lê a primeira aba de um .xlsx sem biblioteca externa.

    O .xlsx é um zip com XML dentro. Ler direto evita depender de instalar um
    pacote novo no computador do hospital — o que exigiria internet na hora de
    abrir o sistema. Cobre o que a exportação da MasterTools usa: texto
    (compartilhado ou em linha) e número.
    """
    try:
        pacote = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        raise PlanilhaInvalida("O arquivo não é uma planilha .xlsx válida.")

    compartilhados: list[str] = []
    if "xl/sharedStrings.xml" in pacote.namelist():
        raiz = ElementTree.fromstring(pacote.read("xl/sharedStrings.xml"))
        for si in raiz.findall("m:si", _NS):
            compartilhados.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))

    # primeira aba, pelo workbook (o nome do arquivo interno nem sempre é sheet1)
    caminho = "xl/worksheets/sheet1.xml"
    try:
        livro = ElementTree.fromstring(pacote.read("xl/workbook.xml"))
        primeira = livro.find("m:sheets/m:sheet", _NS)
        rid = primeira.get(f"{{{_NS['r']}}}id")
        relacoes = ElementTree.fromstring(pacote.read("xl/_rels/workbook.xml.rels"))
        for rel in relacoes.findall("rel:Relationship", _NS):
            if rel.get("Id") == rid:
                alvo = rel.get("Target").lstrip("/")
                caminho = alvo if alvo.startswith("xl/") else f"xl/{alvo}"
    except (KeyError, AttributeError, ElementTree.ParseError):
        pass
    if caminho not in pacote.namelist():
        raise PlanilhaInvalida("Não encontrei a aba de dados dentro da planilha.")

    def coluna(ref: str) -> int:
        letras = re.match(r"[A-Z]+", ref or "A").group(0)
        n = 0
        for letra in letras:
            n = n * 26 + (ord(letra) - 64)
        return n - 1

    linhas: list[list[str]] = []
    folha = ElementTree.fromstring(pacote.read(caminho))
    for linha in folha.iter(f"{{{_NS['m']}}}row"):
        valores: dict[int, str] = {}
        for c in linha.findall("m:c", _NS):
            tipo = c.get("t")
            if tipo == "inlineStr":
                valor = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            else:
                v = c.find("m:v", _NS)
                valor = v.text if v is not None and v.text is not None else ""
                if tipo == "s" and valor:
                    valor = compartilhados[int(valor)]
            valores[coluna(c.get("r"))] = valor
        if valores:
            linhas.append([valores.get(i, "") for i in range(max(valores) + 1)])
    return linhas


def _linhas_csv(conteudo: bytes) -> list[list[str]]:
    try:
        textoarq = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        textoarq = conteudo.decode("latin-1")
    amostra = textoarq[:2000]
    separador = ";" if amostra.count(";") >= amostra.count(",") else ","
    return list(csv.reader(io.StringIO(textoarq), delimiter=separador))


def _cabecalho(celula: str) -> str:
    return " ".join(sem_acento(texto(celula)).lower().split())


def _codigo(valor: str) -> str:
    """'400097', 400097 e '400097.0' são o mesmo código."""
    valor = texto(valor)
    if re.fullmatch(r"\d+\.0+", valor):
        valor = valor.split(".")[0]
    return valor


def _codigo_master(valor) -> str:
    """v18.4.7: o código master vem da MasterTools com ponto ("1.234", "22.") — o
    ponto é ignorado. Número inteiro lido como 22.0 continua 22."""
    return re.sub(r"[.\s]", "", _codigo(texto(valor)))


def _valor(bruto: str) -> float | None:
    """Número da planilha, em qualquer formato; None se não der para ler.

    None, e não zero: um valor ilegível não pode apagar o preço licitado que já
    estava no catálogo. "1.234,56" (CSV brasileiro), "1234.56" e 1234.56 valem o
    mesmo.
    """
    bruto = texto(bruto).replace("R$", "").replace(" ", "")
    if not bruto:
        return None
    if "," in bruto and "." in bruto:
        bruto = bruto.replace(".", "")
    bruto = bruto.replace(",", ".")
    try:
        return float(bruto)
    except ValueError:
        return None


def ler_planilha(conteudo: bytes, nome_arquivo: str) -> tuple[dict[str, dict], int]:
    """Devolve {codigo_aghu: dados} e quantas linhas foram ignoradas.

    As colunas são achadas pelo NOME do cabeçalho, não pela posição: se a
    MasterTools mudar a ordem das colunas, a importação continua certa. O que é
    obrigatório: uma coluna com "AGHU" e uma com o nome/descrição do material.
    """
    if nome_arquivo.lower().endswith(".csv"):
        linhas = _linhas_csv(conteudo)
    else:
        linhas = _linhas_xlsx(conteudo)

    for i, linha in enumerate(linhas[:20]):
        cab = [_cabecalho(c) for c in linha]
        col_aghu = next((j for j, c in enumerate(cab) if "aghu" in c), None)
        col_nome = next((j for j, c in enumerate(cab)
                         if "nome" in c or "descri" in c or c == "material"), None)
        if col_aghu is not None and col_nome is None and any("master" in c for c in cab):
            # v18: planilha só com a relação "Código AGHU → Código master".
            raise SoRelacaoMaster(i)
        if col_aghu is not None and col_nome is not None:
            col_master = next((j for j, c in enumerate(cab) if "master" in c), None)
            col_valor = next((j for j, c in enumerate(cab) if "valor" in c), None)
            corpo = linhas[i + 1:]
            break
    else:
        raise PlanilhaInvalida(
            "Não encontrei as colunas “Código AGHU” e “Nome Material” no cabeçalho. "
            "Confira se é a planilha de materiais (MasterTools).")

    def cel(linha, j):
        return texto(linha[j]) if j is not None and j < len(linha) else ""

    catalogo: dict[str, dict] = {}
    ignoradas = 0
    for linha in corpo:
        codigo = _codigo(cel(linha, col_aghu))
        # A descrição oficial é guardada exatamente como vem (só sem espaço nas
        # pontas): mexer em espaços internos faria centenas de códigos
        # aparecerem como "alterados" sem nada ter mudado.
        nome = cel(linha, col_nome).strip()
        if not codigo or not nome:
            ignoradas += 1
            continue
        catalogo[codigo] = {
            "descritivo_hospital": nome,
            "codigo_master": _codigo_master(cel(linha, col_master)),
            "valor_unitario_licitado": _valor(cel(linha, col_valor)),
        }
    return catalogo, ignoradas


def situacao_catalogo() -> dict:
    linha = db.consultar_um(
        """SELECT COUNT(*) AS total, MAX(atualizado_em) AS quando,
                  (SELECT atualizado_por FROM materiais_mestre
                    ORDER BY atualizado_em DESC LIMIT 1) AS quem
           FROM materiais_mestre""")
    return dict(linha) if linha else {"total": 0, "quando": None, "quem": None}


class SoRelacaoMaster(Exception):
    """A planilha tem só AGHU e master (sem o nome do material)."""


def importar_relacao_master(conteudo: bytes, nome_arquivo: str, usuario: str) -> tuple[bool, str, dict]:
    """v18: preenche o CÓDIGO MASTER pela relação com o código AGHU.

    Aceita uma planilha (.xlsx/.csv) com uma coluna "AGHU" e uma "Master" —
    a ordem não importa. Só atualiza o código master dos materiais que já estão
    no catálogo; os códigos AGHU que não estão no catálogo são contados e
    listados (alguns exemplos), sem criar material sem nome."""
    linhas = _linhas_csv(conteudo) if texto(nome_arquivo).lower().endswith(".csv") else _linhas_xlsx(conteudo)
    for i, linha in enumerate(linhas[:20]):
        cab = [_cabecalho(c) for c in linha]
        col_aghu = next((j for j, c in enumerate(cab) if "aghu" in c), None)
        col_master = next((j for j, c in enumerate(cab) if "master" in c), None)
        if col_aghu is not None and col_master is not None:
            corpo = linhas[i + 1:]
            break
    else:
        return False, "Não encontrei as colunas “Código AGHU” e “Código master” no cabeçalho.", {}
    relacao, ignoradas = {}, 0
    for linha in corpo:
        aghu = _codigo(texto(linha[col_aghu]) if col_aghu < len(linha) else "")
        master = _codigo_master(texto(linha[col_master]) if col_master < len(linha) else "")
        if not aghu or not master:
            ignoradas += 1
            continue
        relacao[aghu] = master
    if not relacao:
        return False, "A planilha não tem nenhuma linha com código AGHU e código master.", {}
    atual = {l["codigo_aghu"]: texto(l["codigo_master"]) for l in
             db.consultar("SELECT codigo_aghu, codigo_master FROM materiais_mestre")}
    # o catálogo guarda o AGHU como veio; compara também sem zeros à esquerda
    por_numero = {k.lstrip("0") or k: k for k in atual}
    alterados, iguais, fora = [], 0, []
    for aghu, master in relacao.items():
        chave = aghu if aghu in atual else por_numero.get(aghu.lstrip("0") or aghu)
        if not chave:
            fora.append(aghu)
        elif atual[chave] == master:
            iguais += 1
        else:
            alterados.append((chave, master))
    agora = db.agora()
    with db.transacao() as conn:
        for chave, master in alterados:
            conn.execute("UPDATE materiais_mestre SET codigo_master = ?, atualizado_em = ?, atualizado_por = ? "
                         "WHERE codigo_aghu = ?", (master, agora, usuario, chave))
    resumo = {"arquivo": texto(nome_arquivo), "lidos": len(relacao), "novos": 0, "alterados": len(alterados),
              "iguais": iguais, "ausentes": 0, "ignoradas": ignoradas, "exemplos": [],
              "relacao_master": True, "fora_do_catalogo": len(fora), "exemplos_fora": fora[:10]}
    log.info(f"relação AGHU→master importada · {nome_arquivo} · lidos={len(relacao)} · "
             f"atualizados={len(alterados)} · fora do catálogo={len(fora)}", usuario)
    msg = f"Código master preenchido em {len(alterados)} material(is)"
    msg += f" ({iguais} já estavam certos)." if iguais else "."
    if fora:
        msg += (f" {len(fora)} código(s) AGHU da planilha não estão no catálogo — carregue antes a planilha "
                "de materiais (MasterTools) e importe a relação de novo.")
    return True, msg, resumo


def importar_planilha(conteudo: bytes, nome_arquivo: str, usuario: str) -> tuple[bool, str, dict]:
    """Atualiza o catálogo com a planilha enviada. Tudo ou nada."""
    if not conteudo:
        return False, "Escolha o arquivo da planilha.", {}
    try:
        novo, ignoradas = ler_planilha(conteudo, texto(nome_arquivo))
    except SoRelacaoMaster:
        return importar_relacao_master(conteudo, nome_arquivo, usuario)
    except PlanilhaInvalida as erro:
        return False, str(erro), {}
    except (ElementTree.ParseError, ValueError, IndexError) as erro:
        log.erro(f"planilha de materiais ilegível · {nome_arquivo}", usuario, erro)
        return False, "Não consegui ler a planilha. Salve-a de novo como .xlsx ou .csv e tente outra vez.", {}
    if not novo:
        return False, "A planilha não tem nenhuma linha com código AGHU e nome do material.", {}

    atual = {l["codigo_aghu"]: l for l in db.consultar("SELECT * FROM materiais_mestre")}
    novos, alterados, exemplos = [], [], []
    for codigo, dados in novo.items():
        antes = atual.get(codigo)
        if not antes:
            novos.append(codigo)
            continue
        mudou_nome = texto(antes["descritivo_hospital"]) != dados["descritivo_hospital"]
        mudou_valor = (dados["valor_unitario_licitado"] is not None and
                       round(decimal(antes["valor_unitario_licitado"]), 2)
                       != round(dados["valor_unitario_licitado"], 2))
        mudou_master = (bool(dados["codigo_master"])
                        and _codigo_master(antes["codigo_master"]) != dados["codigo_master"])
        if mudou_nome or mudou_valor or mudou_master:
            alterados.append(codigo)
            if len(exemplos) < 5:
                exemplos.append({
                    "codigo": codigo,
                    "antes": antes["descritivo_hospital"] if mudou_nome else f"valor {antes['valor_unitario_licitado']}",
                    "depois": dados["descritivo_hospital"] if mudou_nome else f"valor {dados['valor_unitario_licitado']}",
                })
    ausentes = len(set(atual) - set(novo))

    agora = db.agora()
    with db.transacao() as conn:
        for codigo in novos + alterados:
            d = novo[codigo]
            conn.execute(
                """INSERT INTO materiais_mestre (codigo_aghu, codigo_master, descritivo_hospital,
                                                 valor_unitario_licitado, atualizado_em, atualizado_por)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(codigo_aghu) DO UPDATE SET
                     codigo_master = COALESCE(NULLIF(excluded.codigo_master,''), materiais_mestre.codigo_master),
                     descritivo_hospital = excluded.descritivo_hospital,
                     valor_unitario_licitado = COALESCE(excluded.valor_unitario_licitado,
                                                        materiais_mestre.valor_unitario_licitado),
                     atualizado_em = excluded.atualizado_em,
                     atualizado_por = excluded.atualizado_por""",
                (codigo, d["codigo_master"], d["descritivo_hospital"],
                 d["valor_unitario_licitado"], agora, usuario),
            )

    resumo = {"arquivo": texto(nome_arquivo), "lidos": len(novo), "novos": len(novos),
              "alterados": len(alterados), "iguais": len(novo) - len(novos) - len(alterados),
              "ausentes": ausentes, "ignoradas": ignoradas, "exemplos": exemplos}
    log.info(f"catálogo de materiais atualizado · {nome_arquivo} · lidos={len(novo)} · "
             f"novos={len(novos)} · alterados={len(alterados)} · ausentes={ausentes} · "
             f"ignoradas={ignoradas}", usuario)
    if not novos and not alterados:
        return True, "A planilha é igual ao catálogo atual — nada mudou.", resumo
    return True, (f"Catálogo atualizado: {len(novos)} código(s) novo(s) e "
                  f"{len(alterados)} alterado(s)."), resumo
