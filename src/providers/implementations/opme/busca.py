"""Busca de unidades pelo que o leitor manda (nov/2026).

Na entrada, a etiqueta GS1/UDI completa vira só o GTIN — é por ele que o
material fica cadastrado (ver `gs1.codigo_de_busca`). A bipagem já sabia
separar o GTIN do resto da etiqueta; as telas de busca (Consultas → Itens,
rastreio por lote, Corrigir cadastro, estoque da farmácia, envio...) não:
procuravam o texto bipado inteiro dentro do código cadastrado e não achavam
nada. Aqui a busca passa a entender o código bipado do mesmo jeito que a
bipagem:

* etiqueta GS1 com GTIN → procura pelo GTIN (com ou sem zeros à esquerda) e,
  se a etiqueta traz lote/série/validade, mostra primeiro as unidades daquele
  lote/série (sem esconder as outras se nenhuma conferir);
* etiqueta secundária (só lote/validade, sem GTIN) → procura pelo lote;
* número de 8 a 14 dígitos → também compara como GTIN (763000726591 é o mesmo
  produto que 00763000726591);
* qualquer outro texto → a busca de sempre (parte do texto, em vários campos).
"""

import re

from . import db, gs1
from .utils import texto


def e_codigo_cadastrado(termo) -> bool:
    """O texto bipado é, ele mesmo, um código de barras de material cadastrado?

    v18.43.1: o código do SET DE MANGUEIRAS (AGHU 403331) é "10706;26". Começa
    com "10", que em GS1 é o identificador de LOTE, então o sistema o lia como
    etiqueta, concluía que o lote era "706;26" e, na hora de enviar para a
    farmácia, dizia que esse lote não existia no almoxarifado — mesmo tendo
    achado o material. Se o texto bipado está gravado como código de alguma
    unidade, ele é um código, não uma etiqueta: ponto final.
    """
    t = texto(termo)
    if not t:
        return False
    return bool(db.escalar(
        "SELECT 1 FROM unidades WHERE UPPER(TRIM(COALESCE(codigo_barras, ''))) = ? LIMIT 1",
        (t.upper(),)))


def interpretar(termo) -> dict | None:
    """A etiqueta GS1 bipada, ou None quando o termo é texto comum.

    Código cadastrado nunca é lido como etiqueta (ver `e_codigo_cadastrado`).
    """
    if e_codigo_cadastrado(termo):
        return None
    return gs1.interpretar(texto(termo))


def condicao(termo, campos: list[str], alias: str = "u") -> tuple[str, list, dict | None]:
    """(condição SQL entre parênteses, parâmetros, etiqueta interpretada).

    `campos` são as colunas da busca por texto, já com o prefixo da tabela
    (ex.: ``["u.xProd", "u.nLote"]``). `alias` é o da tabela de unidades na
    consulta ("" quando a consulta não usa alias).
    """
    termo = texto(termo)
    p = f"{alias}." if alias else ""
    etiqueta = interpretar(termo)
    # v18.41: o texto bipado, exatamente como veio, sempre vale como busca.
    #
    # Quando o código é lido como etiqueta GS1, a busca passava a ser só pelo
    # que a etiqueta diz (GTIN, lote, série) — e, se a leitura errasse, não
    # havia segunda chance. Caso real (HC-UFPE, 20/11/2026): o código
    # "10706;26" começa com "10", que em GS1 é o identificador de lote, então
    # o sistema procurava pelo lote "706;26" e não achava o material, mesmo
    # com o código gravado igual, caractere por caractere. Isto aqui é
    # igualdade literal — não traz material parecido, só o que tem exatamente
    # aquele código.
    igual = f"UPPER(TRIM(COALESCE({p}codigo_barras, ''))) = ?"
    par_igual = [termo.upper()]
    if etiqueta and etiqueta.get("gtin"):
        codigo = gs1.gtin(etiqueta["gtin"])
        return (f"(gtin({p}codigo_barras) = ? OR gtin(COALESCE({p}cEAN, '')) = ? OR {igual})",
                [codigo, codigo] + par_igual, etiqueta)
    cond_lote, params_lote = gs1.sql_por_lote(etiqueta, alias or "unidades")
    if cond_lote:
        if not alias:
            cond_lote = cond_lote.replace("unidades.", "")
        return f"({cond_lote} OR {igual})", params_lote + par_igual, etiqueta
    if etiqueta and etiqueta.get("serie") and not etiqueta.get("gtin"):
        # Etiqueta secundária só com o número de série.
        return (f"(UPPER(REPLACE(COALESCE({p}numero_serie, ''), ' ', '')) = ? OR {igual})",
                [re.sub(r"\s+", "", etiqueta["serie"]).upper()] + par_igual, etiqueta)
    partes = [f"{c} LIKE ?" for c in campos]
    params: list = [f"%{termo}%"] * len(campos)
    limpo = re.sub(r"\s+", "", termo)
    if limpo.isdigit() and 8 <= len(limpo) <= 14:
        partes.append(f"gtin({p}codigo_barras) = ?")
        params.append(gs1.gtin(limpo))
    return "(" + " OR ".join(partes) + ")", params, etiqueta


def refinar(linhas: list[dict], etiqueta: dict | None, termo="") -> list[dict]:
    """Com etiqueta GS1, as unidades do lote/série da etiqueta (se houver alguma).

    A unidade cujo código de barras é exatamente o texto bipado nunca é
    descartada aqui: foi cadastrada com aquele código (v18.41).
    """
    if not etiqueta or not linhas:
        return linhas
    filtradas, _aviso = gs1.filtrar(linhas, etiqueta)
    alvo = texto(termo).upper()
    if alvo:
        vistos = {id(l) for l in filtradas}
        filtradas = filtradas + [l for l in linhas if id(l) not in vistos
                                 and texto(l.get("codigo_barras")).upper() == alvo]
    return filtradas


def preferir_exatos(linhas: list[dict], termo) -> list[dict]:
    """v18: quem bipa/digita um código inteiro quer só aquele código.

    Se alguma unidade tem exatamente o código buscado (código de barras, nº de
    série ou ID), mostra só essas — "abc" não traz mais "abc2". Sem nenhuma
    igual, fica a busca por parte do texto de sempre."""
    from .utils import normalizar_codigo
    alvo = texto(termo).upper()
    if not alvo or not linhas:
        return linhas
    alvos = {alvo, texto(normalizar_codigo(termo)).upper()} - {""}
    exatos = [l for l in linhas
              if {texto(l.get("codigo_barras")).upper(), texto(l.get("numero_serie")).upper(),
                  texto(l.get("id_unidade")).upper()} & alvos]
    return exatos or linhas
