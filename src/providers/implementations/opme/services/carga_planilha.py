"""Entrada de estoque pela planilha de lotes do AGHU (out/2026).

A planilha traz, por lote: cod_material, material, fornecedor, marca_comercial,
lote, serie, data_validade e qtde_disponivel_lote. Regras (definidas pela Camila):

- descrição = `material`;
- fornecedor = `marca_comercial` (o campo fornecedor da planilha é genérico,
  "FORNECEDOR NACIONAL EM GERAL");
- cada linha fica PENDENTE. Só entra no estoque quando o almoxarifado bipa o
  material: o bip grava o código de barras e cria a unidade. Enquanto não
  bipado, não existe no estoque.

Como o bip encontra a linha:
1. etiqueta GS1 com lote → a linha daquele lote;
2. código de barras já bipado antes num lote desta carga → aquele lote;
3. código novo → a pessoa escolhe a linha na lista ("é este") e bipa; a partir
   daí aquele lote conhece o código.
Quando mais de uma linha serve, a tela pergunta qual é.
"""

from __future__ import annotations

import csv
import io
import re

from .. import busca, db, gs1, log
from ..domain import EM_ESTOQUE_RECEBIMENTO
from ..utils import data_br, data_iso, gerar_id, inteiro, normalizar_codigo, texto
from . import etiquetas, materiais

COLUNAS = {
    "codigo_aghu": ("COD_MATERIAL", "CODIGO_MATERIAL", "COD_AGHU", "CODIGO_AGHU", "AGHU"),
    "material": ("MATERIAL", "DESCRICAO", "DESCRIÇÃO"),
    "marca": ("MARCA_COMERCIAL", "MARCA"),
    "fornecedor": ("FORNECEDOR",),
    "lote": ("LOTE",),
    "serie": ("SERIE", "SÉRIE", "NUMERO_SERIE"),
    "validade": ("DATA_VALIDADE", "VALIDADE", "DT_VALIDADE"),
    "quantidade": ("QTDE_DISPONIVEL_LOTE", "QTDE_LOTE", "QUANTIDADE", "QTDE"),
}
SEM_VALIDADE = ("3000-01-01",)   # o AGHU usa 01/01/3000 para "sem validade"


def _linhas_do_arquivo(conteudo: bytes, nome: str) -> list[dict]:
    if (nome or "").lower().endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError as erro:
            raise ValueError("Para .xlsx, salve a planilha como CSV (separado por ponto e vírgula).") from erro
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        ws = wb.active
        linhas = list(ws.iter_rows(values_only=True))
        if not linhas:
            return []
        cab = [texto(c) for c in linhas[0]]
        return [{cab[i]: ("" if v is None else v) for i, v in enumerate(l) if i < len(cab)} for l in linhas[1:]]
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            txt = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    primeira = txt.splitlines()[0] if txt else ""
    sep = max((";", ",", "\t"), key=primeira.count)
    return list(csv.DictReader(io.StringIO(txt), delimiter=sep))


def _pega(linha: dict, campo: str) -> str:
    mapa = {re.sub(r"\s+", "_", texto(k).upper()): v for k, v in linha.items() if k is not None}
    for nome in COLUNAS[campo]:
        if nome in mapa:
            v = mapa[nome]
            if hasattr(v, "strftime"):
                return v.strftime("%d/%m/%Y")
            return texto(v)
    return ""


def importar(conteudo: bytes, nome_arquivo: str, usuario: str) -> tuple[bool, str, str]:
    try:
        linhas = _linhas_do_arquivo(conteudo, nome_arquivo)
    except ValueError as erro:
        return False, str(erro), ""
    if not linhas:
        return False, "A planilha está vazia.", ""
    if not _pega(linhas[0], "codigo_aghu") and not _pega(linhas[0], "material"):
        return False, ("Não reconheci as colunas. A planilha precisa de: cod_material, material, "
                       "marca_comercial, lote, data_validade e qtde_disponivel_lote."), ""
    novas, ignoradas, repetidas, unidades = [], 0, 0, 0
    # A extração do AGHU pode repetir o mesmo lote várias vezes (uma por
    # extração, coluna extraido_em). O mesmo AGHU + lote + validade + marca +
    # série conta UMA vez — fica a última ocorrência.
    unicas: dict[tuple, dict] = {}
    for l in linhas:
        chave = (_pega(l, "codigo_aghu"), _pega(l, "lote"), _pega(l, "validade"), _pega(l, "marca"),
                 _pega(l, "serie"))
        unicas[chave] = l
    duplicadas_arquivo = len(linhas) - len(unicas)
    linhas = list(unicas.values())
    with db.transacao() as conn:
        for l in linhas:
            aghu = _pega(l, "codigo_aghu")
            qtd = inteiro(_pega(l, "quantidade"), 0)
            if not aghu or qtd <= 0:
                ignoradas += 1
                continue
            validade = data_iso(_pega(l, "validade"))
            if validade in SEM_VALIDADE:
                validade = ""
            lote = _pega(l, "lote")
            marca = _pega(l, "marca") or _pega(l, "fornecedor")
            # Reimportar a mesma planilha não duplica: o mesmo AGHU + lote + validade
            # + marca ainda pendente (ou já bipado) de outra carga é pulado.
            if conn.execute(
                    """SELECT 1 FROM carga_itens WHERE codigo_aghu = ? AND COALESCE(lote,'') = ?
                       AND COALESCE(dVal,'') = ? AND COALESCE(marca,'') = ? AND situacao <> 'cancelado'""",
                    (aghu, lote, validade, marca)).fetchone():
                repetidas += 1
                continue
            novas.append((aghu, _pega(l, "material"), marca, lote, _pega(l, "serie"), validade, qtd))
            unidades += qtd
        if not novas:
            msg = "Nenhuma linha nova na planilha."
            if repetidas:
                msg += f" {repetidas} linha(s) já tinham sido importadas antes."
            return False, msg, ""
        id_carga = gerar_id("CARGA")
        conn.execute("""INSERT INTO cargas_planilha (id_carga, arquivo, criado_por, criado_em, linhas, unidades)
                        VALUES (?,?,?,?,?,?)""", (id_carga, texto(nome_arquivo), usuario, db.agora(),
                                                  len(novas), unidades))
        conn.executemany(
            """INSERT INTO carga_itens (id_carga, codigo_aghu, material, marca, lote, serie, dVal,
                                        qtd_total, qtd_pendente)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(id_carga, a, m, mc, lt, sr, v or None, q, q) for a, m, mc, lt, sr, v, q in novas])
        db.registrar_evento(conn, tipo="carga_planilha", usuario=usuario,
                            observacao=f"Planilha {nome_arquivo}: {len(novas)} lote(s), {unidades} unidade(s) pendentes de bip.")
    msg = (f"Planilha importada: {len(novas)} lote(s), {unidades} unidade(s) pendentes. "
           "Elas só entram no estoque quando forem bipadas.")
    if repetidas:
        msg += f" {repetidas} linha(s) repetida(s) de importação anterior foram puladas."
    if ignoradas:
        msg += f" {ignoradas} linha(s) sem código ou sem quantidade foram ignoradas."
    if duplicadas_arquivo:
        msg += f" {duplicadas_arquivo} linha(s) repetidas na própria planilha foram contadas uma vez só."
    return True, msg, id_carga


# ---------------------------------------------------------------- consultas

def cargas() -> list[dict]:
    return db.consultar(
        """SELECT c.*, (SELECT COALESCE(SUM(qtd_pendente),0) FROM carga_itens i
                        WHERE i.id_carga = c.id_carga AND i.situacao = 'pendente') AS pendentes,
                       (SELECT COUNT(*) FROM carga_itens i
                        WHERE i.id_carga = c.id_carga AND i.situacao = 'pendente') AS linhas_pendentes
           FROM cargas_planilha c ORDER BY c.criado_em DESC""")


def total_pendente() -> int:
    return int(db.escalar("SELECT COALESCE(SUM(qtd_pendente),0) FROM carga_itens WHERE situacao = 'pendente'") or 0)


def pendentes(termo: str = "", limite: int = 400) -> list[dict]:
    cond, params = ["i.situacao = 'pendente'"], []
    for palavra in texto(termo).split():
        cond.append("(i.codigo_aghu LIKE ? OR i.material LIKE ? OR i.lote LIKE ? OR i.marca LIKE ? "
                    "OR i.codigo_barras LIKE ?)")
        params += [f"%{palavra}%"] * 5
    linhas = db.consultar(
        f"""SELECT i.* FROM carga_itens i WHERE {' AND '.join(cond)}
            ORDER BY i.material, i.lote LIMIT {int(limite)}""", tuple(params))
    for l in linhas:
        l["validade"] = data_br(l["dVal"]) if l["dVal"] else "sem validade"
    return linhas


def _formatar(l: dict) -> dict:
    return {"id_item": l["id_item"], "aghu": l["codigo_aghu"], "material": l["material"],
            "marca": l["marca"] or "—", "lote": l["lote"] or "—",
            "validade": data_br(l["dVal"]) if l["dVal"] else "sem validade",
            "pendente": l["qtd_pendente"], "total": l["qtd_total"]}


# ---------------------------------------------------------------- bip

def _candidatas(codigo: str, etiqueta: dict | None) -> tuple[list[dict], str]:
    pend = [dict(r) for r in db.consultar("SELECT * FROM carga_itens WHERE situacao = 'pendente'")]
    if etiqueta and etiqueta.get("lote"):
        por_lote = [l for l in pend if gs1._confere(l["lote"], etiqueta["lote"], etiqueta.get("lote_ate_o_fim"))]
        por_lote = [l for l in por_lote if not texto(l["codigo_barras"]) or l["codigo_barras"] == codigo]
        if por_lote:
            return por_lote, "lote da etiqueta"
    mesmo_codigo = [l for l in pend if texto(l["codigo_barras"]) == codigo]
    if mesmo_codigo:
        return mesmo_codigo, "código já bipado neste lote"
    aghus = {r["codigo_aghu"] for r in db.consultar(
        "SELECT DISTINCT codigo_aghu FROM historico_produtos WHERE codigo = ? AND COALESCE(codigo_aghu,'') <> ''",
        (codigo,))}
    aghus |= {r["codigo_aghu"] for r in db.consultar(
        "SELECT DISTINCT codigo_aghu FROM carga_itens WHERE codigo_barras = ?", (codigo,))}
    if aghus:
        sugeridas = [l for l in pend if l["codigo_aghu"] in aghus and not texto(l["codigo_barras"])]
        if sugeridas:
            return sugeridas, "sugestão pelo código AGHU já usado com este código de barras"
    return [], ""


def bipar(codigo_lido: str, usuario: str, id_item=None, quantidade=1, tipo_entrada: str = "") -> dict:
    bruto = texto(codigo_lido)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    etiqueta = busca.interpretar(bruto)
    codigo = normalizar_codigo(bruto)
    if etiqueta and not etiqueta.get("gtin") and not inteiro(id_item, 0):
        return {"ok": False, "mensagem": ("Esta é a etiqueta só com lote/validade. Bipe o código de barras "
                                          "do produto (GTIN).")}
    if inteiro(id_item, 0):
        linha = db.consultar_um("SELECT * FROM carga_itens WHERE id_item = ? AND situacao = 'pendente'",
                                (inteiro(id_item, 0),))
        if not linha:
            return {"ok": False, "mensagem": "Esta linha não está mais pendente."}
        linha = dict(linha)
        if texto(linha["codigo_barras"]) and linha["codigo_barras"] != codigo:
            return {"ok": False, "mensagem": (f"Este lote já foi bipado com o código {linha['codigo_barras']}. "
                                              f"O código {codigo} é de outro material ou de outro lote.")}
    else:
        candidatas, como = _candidatas(codigo, etiqueta)
        if not candidatas:
            return {"ok": False, "codigo_novo": True, "codigo": bruto,
                    "mensagem": (f"Código {codigo} ainda não conhecido. Encontre o material na lista, "
                                 "clique em “é este” e bipe de novo.")}
        if len(candidatas) > 1:
            return {"ok": False, "escolher": True, "codigo": bruto, "como": como,
                    "opcoes": [_formatar(l) for l in candidatas[:30]],
                    "mensagem": f"O código {codigo} serve para {len(candidatas)} linhas. Escolha qual é."}
        linha = candidatas[0]

    qtd = max(1, inteiro(quantidade, 1))
    qtd = min(qtd, int(linha["qtd_pendente"]))
    alertas = []
    if etiqueta and etiqueta.get("lote") and texto(linha["lote"]) and not gs1._confere(
            linha["lote"], etiqueta["lote"], etiqueta.get("lote_ate_o_fim")):
        alertas.append(f"Lote da etiqueta ({etiqueta['lote']}) diferente do lote da planilha ({linha['lote']}).")
    if etiqueta and etiqueta.get("validade") and linha["dVal"] and etiqueta["validade"] != linha["dVal"]:
        alertas.append(f"Validade da etiqueta ({data_br(etiqueta['validade'])}) diferente da planilha "
                       f"({data_br(linha['dVal'])}).")
    _dar_entrada(linha, codigo, qtd, usuario, "bip" + (" (escolhido na lista)" if inteiro(id_item, 0) else ""),
                 tipo_entrada)
    restante = int(linha["qtd_pendente"]) - qtd
    return {"ok": True, "quantidade": qtd, "restante": restante, "alertas": alertas,
            "item": _formatar(linha | {"qtd_pendente": restante}),
            "mensagem": (f"{qtd} unidade(s) de {linha['material'][:60]} (lote {linha['lote'] or '—'}) "
                         f"entraram no estoque." + (f" Faltam {restante} deste lote." if restante else
                                                     " Lote completo."))}


def entrada_sem_codigo(id_item, quantidade, usuario: str, tipo_entrada: str = "") -> tuple[bool, str, str]:
    """Material sem código de barras: gera o código interno (etiqueta QR)."""
    linha = db.consultar_um("SELECT * FROM carga_itens WHERE id_item = ? AND situacao = 'pendente'",
                            (inteiro(id_item, 0),))
    if not linha:
        return False, "Esta linha não está mais pendente.", ""
    linha = dict(linha)
    codigo = texto(linha["codigo_barras"]) or etiquetas.gerar_codigo_interno(linha["codigo_aghu"], linha["lote"])
    qtd = min(max(1, inteiro(quantidade, 1)), int(linha["qtd_pendente"]))
    _dar_entrada(linha, codigo, qtd, usuario, "sem código de barras (código interno)", tipo_entrada)
    return True, (f"{qtd} unidade(s) entraram no estoque com o código interno {codigo}. "
                  "Imprima a etiqueta e cole na embalagem."), codigo


def _dar_entrada(linha: dict, codigo: str, qtd: int, usuario: str, como: str, tipo_entrada: str = "") -> None:
    """`tipo_entrada`: classificação (aquisição própria, consignado, doação,
    empréstimo). Não é obrigatória: em branco vale "aquisição própria"."""
    from .estoque import TIPOS_ENTRADA, normalizar_tipo_entrada
    tipo = normalizar_tipo_entrada(tipo_entrada)
    descritivo = materiais.descritivo_hospital(linha["codigo_aghu"]) or linha["material"]
    agora = db.agora()
    with db.transacao() as conn:
        for _ in range(qtd):
            id_unidade = gerar_id("U")
            conn.execute(
                """INSERT INTO unidades
                   (id_unidade, codigo_barras, codigo_aghu, xProd, marca_fabricante, fornecedor,
                    nLote, numero_serie, dVal, origem, tipo_entrada, status, descritivo_hospital,
                    criado_em, criado_por, atualizado_em, atualizado_por)
                   VALUES (?,?,?,?,?,?,?,?,?,'planilha',?,?,?,?,?,?,?)""",
                (id_unidade, codigo, linha["codigo_aghu"], linha["material"], linha["marca"] or "",
                 linha["marca"] or "", linha["lote"] or "", linha["serie"] or "", linha["dVal"] or None,
                 tipo, EM_ESTOQUE_RECEBIMENTO, descritivo, agora, usuario, agora, usuario))
            db.registrar_evento(
                conn, tipo="entrada_planilha", id_unidade=id_unidade, status_novo=EM_ESTOQUE_RECEBIMENTO,
                usuario=usuario,
                observacao=(f"Planilha de lotes AGHU · {linha['material'][:80]} · lote {linha['lote'] or '—'} · {como}"
                            f" · {TIPOS_ENTRADA[tipo]}"))
        novo = int(linha["qtd_pendente"]) - qtd
        conn.execute("""UPDATE carga_itens SET qtd_pendente = ?, codigo_barras = COALESCE(NULLIF(codigo_barras,''), ?),
                        situacao = ? WHERE id_item = ?""",
                     (novo, codigo, "concluido" if novo <= 0 else "pendente", linha["id_item"]))
        if not etiquetas.e_codigo_interno(codigo) and texto(linha["marca"]):
            conn.execute(
                """INSERT OR IGNORE INTO historico_produtos
                   (codigo, xProd, codigo_aghu, marca_fabricante, fornecedor_cnpj, fornecedor, criado_em, criado_por)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (codigo, linha["material"], linha["codigo_aghu"], linha["marca"], "", linha["marca"], agora, usuario))
    log.info(f"entrada pela planilha · item={linha['id_item']} · {qtd} unid.", usuario)


def _tipo_padrao() -> str:
    from .estoque import normalizar_tipo_entrada
    return normalizar_tipo_entrada("")


def cancelar_linha(id_item, usuario: str, motivo: str) -> tuple[bool, str]:
    """Linha que não vai ser bipada (o material não está fisicamente no estoque)."""
    motivo = texto(motivo)
    if len(motivo) < 3:
        return False, "Informe o motivo (ex.: material não encontrado no estoque físico)."
    linha = db.consultar_um("SELECT * FROM carga_itens WHERE id_item = ? AND situacao = 'pendente'",
                            (inteiro(id_item, 0),))
    if not linha:
        return False, "Esta linha não está mais pendente."
    with db.transacao() as conn:
        conn.execute("UPDATE carga_itens SET situacao = 'cancelado' WHERE id_item = ?", (linha["id_item"],))
        db.registrar_evento(conn, tipo="carga_planilha", usuario=usuario, motivo=motivo,
                            observacao=(f"Linha da planilha retirada sem bipar: {linha['material'][:80]} · "
                                        f"lote {linha['lote'] or '—'} · {linha['qtd_pendente']} unid. pendentes"))
    return True, "Linha retirada da lista de pendentes."
