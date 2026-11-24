"""nov/2026 — associação entre o código consignado e o código AGHU.

O empenho de consignado passa a ser cadastrado pelo CÓDIGO CONSIGNADO (o
código do item no contrato/fornecedor). Cada código consignado é associado a
um código AGHU — é por ele que o hospital conhece o material (descrição HC,
estoque, relatórios). A associação é cadastrada aqui (ou na hora do empenho,
quando o código ainda não tem AGHU) e serve ao empenho, à tabela de empenhos e
aos relatórios, que mostram os dois números juntos.
"""

import re

from .. import db
from ..utils import texto

MSG_SEM_AGHU = ("O código consignado {c} ainda não está associado a um código AGHU. "
                "Informe o AGHU ao lado dele.")


def normalizar(codigo) -> str:
    return re.sub(r"\s+", "", texto(codigo)).upper()


def listar(termo: str = "", limite: int = 1000) -> list[dict]:
    cond, params = "", []
    if texto(termo):
        cond = ("WHERE c.codigo_consignado LIKE ? OR c.codigo_aghu LIKE ? OR UPPER(COALESCE(c.fornecedor,'')) LIKE ? "
                "OR UPPER(COALESCE(c.descricao,'')) LIKE ? OR UPPER(COALESCE(m.descritivo_hospital,'')) LIKE ?")
        t = f"%{texto(termo).upper()}%"
        params = [t] * 5
    linhas = db.consultar(
        f"""SELECT c.*, m.descritivo_hospital,
                   (SELECT COUNT(*) FROM empenho_consignado x JOIN empenhos e ON e.id_empenho = x.id_empenho
                     WHERE x.codigo_consignado = c.codigo_consignado AND e.status = 'ativo') AS empenhos_ativos
            FROM consignado_aghu c LEFT JOIN materiais_mestre m ON m.codigo_aghu = c.codigo_aghu
            {cond} ORDER BY c.codigo_consignado LIMIT {int(limite)}""", params)
    return linhas


def buscar(codigo_consignado) -> dict | None:
    c = normalizar(codigo_consignado)
    if not c:
        return None
    return db.consultar_um(
        """SELECT c.*, m.descritivo_hospital FROM consignado_aghu c
           LEFT JOIN materiais_mestre m ON m.codigo_aghu = c.codigo_aghu WHERE c.codigo_consignado = ?""", (c,))


def de_aghu(codigo_aghu) -> list[dict]:
    """v18.4.7: códigos consignados associados a um AGHU (pela relação importada).
    Compara também sem zeros à esquerda."""
    a = normalizar(codigo_aghu)
    if not a:
        return []
    return db.consultar(
        """SELECT codigo_consignado, codigo_aghu, fornecedor, descricao FROM consignado_aghu
           WHERE codigo_aghu = ? OR LTRIM(codigo_aghu, '0') = LTRIM(?, '0')
           ORDER BY codigo_consignado""", (a, a))


def resolver_por_aghu(codigo_aghu, fornecedor: str = "") -> tuple[bool, str]:
    """v18.4.7: o código consignado do material vem do AGHU. Devolve (True, código)
    ou (False, mensagem). Com mais de um código para o AGHU, usa o do fornecedor da nota."""
    opcoes = de_aghu(codigo_aghu)
    if not opcoes:
        # v18.11.4: sem a relação importada, NÃO trava o cadastro — usa provisoriamente
        # o próprio código AGHU como código consignado (dá para corrigir depois).
        provisorio = normalizar(codigo_aghu)
        if provisorio:
            return True, provisorio
        return False, "Material consignado: informe o código AGHU."
    if len(opcoes) == 1:
        return True, opcoes[0]["codigo_consignado"]
    forn = re.sub(r"\W+", "", texto(fornecedor).upper())
    if forn:
        do_fornecedor = [o for o in opcoes if o["fornecedor"] and
                         (re.sub(r"\W+", "", o["fornecedor"].upper()) in forn or forn in re.sub(r"\W+", "", o["fornecedor"].upper()))]
        if len(do_fornecedor) == 1:
            return True, do_fornecedor[0]["codigo_consignado"]
    return False, (f"O AGHU {texto(codigo_aghu)} tem mais de um código consignado associado "
                   f"({', '.join(o['codigo_consignado'] for o in opcoes)}). Escolha qual é este material.")


def aghu_de(codigo_consignado) -> str:
    linha = buscar(codigo_consignado)
    return texto(linha["codigo_aghu"]) if linha else ""


def salvar(codigo_consignado, codigo_aghu, usuario: str, fornecedor: str = "", descricao: str = "",
           conn=None) -> tuple[bool, str]:
    """Cria ou atualiza a associação (um código consignado → um AGHU)."""
    c, a = normalizar(codigo_consignado), normalizar(codigo_aghu)
    if not c:
        return False, "Informe o código consignado."
    if not a:
        return False, f"Informe o código AGHU do consignado {c}."
    agora = db.agora()
    sql = """INSERT INTO consignado_aghu (codigo_consignado, codigo_aghu, fornecedor, descricao, criado_em, criado_por,
                                          atualizado_em, atualizado_por)
             VALUES (?,?,?,?,?,?,?,?)
             ON CONFLICT(codigo_consignado) DO UPDATE SET codigo_aghu = excluded.codigo_aghu,
                 fornecedor = COALESCE(NULLIF(excluded.fornecedor, ''), consignado_aghu.fornecedor),
                 descricao = COALESCE(NULLIF(excluded.descricao, ''), consignado_aghu.descricao),
                 atualizado_em = excluded.atualizado_em, atualizado_por = excluded.atualizado_por"""
    params = (c, a, texto(fornecedor), texto(descricao), agora, usuario, agora, usuario)
    # v18.11.5: consignado mostra a descrição do próprio material (tamanho do balão…)
    sql_desc = """UPDATE unidades SET descritivo_hospital = ?
                  WHERE codigo_consignado = ? AND tipo_entrada = 'consignado'"""
    if conn is not None:
        conn.execute(sql, params)
        if texto(descricao):
            conn.execute(sql_desc, (texto(descricao), c))
    else:
        db.executar(sql, params)
        if texto(descricao):
            db.executar(sql_desc, (texto(descricao), c))
    return True, f"Código consignado {c} associado ao AGHU {a}."


def excluir(codigo_consignado, usuario: str) -> tuple[bool, str]:
    c = normalizar(codigo_consignado)
    linha = buscar(c)
    if not linha:
        return False, "Associação não encontrada."
    ativos = db.escalar("""SELECT COUNT(*) FROM empenho_consignado x JOIN empenhos e ON e.id_empenho = x.id_empenho
                           WHERE x.codigo_consignado = ? AND e.status = 'ativo'""", (c,))
    if ativos:
        return False, (f"O código consignado {c} está em {ativos} empenho(s) ativo(s). "
                       "Para trocar o AGHU, edite a associação em vez de excluir.")
    db.executar("DELETE FROM consignado_aghu WHERE codigo_consignado = ?", (c,))
    return True, f"Associação do código consignado {c} excluída."


def resolver_pares(pares: list[tuple[str, str]]) -> tuple[bool, str | list[tuple[str, str, bool]]]:
    """[(consignado, aghu digitado)] → [(consignado, aghu, associação_nova)].

    AGHU em branco vem da associação. AGHU digitado para um código ainda sem
    associação cria a associação. AGHU digitado diferente do associado é
    recusado (para trocar, edite a associação).
    """
    vistos: dict[str, tuple[str, str, bool]] = {}
    for bruto_c, bruto_a in pares:
        c, a = normalizar(bruto_c), normalizar(bruto_a)
        if not c:
            continue
        associado = aghu_de(c)
        if associado and a and a != associado:
            return False, (f"O código consignado {c} já está associado ao AGHU {associado} (e não ao {a}). "
                           "Se mudou, corrija em Consignados → Código consignado × AGHU.")
        if not associado and not a:
            return False, MSG_SEM_AGHU.format(c=c)
        vistos[c] = (c, associado or a, not associado)
    if not vistos:
        return False, "Informe o código consignado coberto por este empenho (um ou vários)."
    return True, list(vistos.values())


def importar_planilha(conteudo: bytes, nome_arquivo: str, usuario: str) -> tuple[bool, str, dict]:
    """Uma associação por linha: colunas Código consignado e Código AGHU (Fornecedor e Descrição opcionais)."""
    from .materiais import PlanilhaInvalida, _cabecalho, _codigo, _linhas_csv, _linhas_xlsx
    try:
        linhas = (_linhas_csv(conteudo) if texto(nome_arquivo).lower().endswith(".csv") else _linhas_xlsx(conteudo))
    except PlanilhaInvalida as erro:
        return False, str(erro), {}
    inicio, mapa = None, {}
    for i, linha in enumerate(linhas[:10]):
        m = {}
        for n, bruto in enumerate(linha):
            t = _cabecalho(bruto)
            if not t:
                continue
            if "consignado" in t and "consignado" not in m:
                m["consignado"] = n
            elif "aghu" in t and "aghu" not in m:
                m["aghu"] = n
            elif "fornecedor" in t and "fornecedor" not in m:
                m["fornecedor"] = n
            elif ("descri" in t or "material" in t) and "descricao" not in m:
                m["descricao"] = n
        if "consignado" in m and "aghu" in m:
            inicio, mapa = i, m
            break
    if inicio is None:
        return False, "Não encontrei o cabeçalho. A planilha precisa ter as colunas Código consignado e Código AGHU.", {}
    resultado = {"salvos": 0, "erros": []}
    with db.transacao() as conn:
        for numero, linha in enumerate(linhas[inicio + 1:], start=inicio + 2):
            cel = lambda k: texto(linha[mapa[k]]) if k in mapa and mapa[k] < len(linha) else ""
            if not any(texto(x) for x in linha):
                continue
            ok, msg = salvar(_codigo(cel("consignado")), _codigo(cel("aghu")), usuario, cel("fornecedor"),
                             cel("descricao"), conn=conn)
            if ok:
                resultado["salvos"] += 1
            else:
                resultado["erros"].append({"linha": numero, "mensagem": msg})
    msg = f"{resultado['salvos']} associação(ões) gravada(s)."
    if resultado["erros"]:
        msg += f" {len(resultado['erros'])} linha(s) com problema."
    return True, msg, resultado
