"""nov/2026 — planilha (Excel) da entrada por NF para lançar no AGHU.

Depois de dar entrada nos itens de uma nota fiscal, o almoxarifado baixa uma
planilha com uma linha por material + lote + validade (somando a quantidade),
nas colunas que a automação de lançamento no AGHU usa:

    Código AGHU | Código master | Código consignado | Lote | Validade | Fornecedor | Marca | Quantidade
    | Nº NF | Série | Valor unitário | Valor total     (nov/2026, para o robô do AGHU;
    a unidade de medida é sempre UNIDADE e o almoxarifado sempre o 1)

Só entram as unidades que deram entrada por esta NF; cadastro excluído por
engano não conta. Vale só para a entrada por NF.
"""

import io
import re

from .. import db
from ..utils import data_br, texto

COLUNAS = ["Código AGHU", "Código master", "Código consignado", "Lote", "Validade", "Fornecedor", "Marca", "Quantidade",
           "Nº NF", "Série", "Valor unitário", "Valor total"]


def serie_da_chave(chave_nf: str) -> str:
    """Série da NF-e: posições 23–25 da chave de 44 dígitos (sem zeros à esquerda)."""
    chave = re.sub(r"\D", "", texto(chave_nf))
    if len(chave) != 44:
        return ""
    return str(int(chave[22:25]))


def linhas(chave_nf: str) -> list[dict]:
    return db.consultar(
        """SELECT COALESCE(u.codigo_aghu, '') AS codigo_aghu,
                  COALESCE((SELECT m.codigo_master FROM materiais_mestre m WHERE m.codigo_aghu = u.codigo_aghu), '')
                    AS codigo_master,
                  COALESCE(u.codigo_consignado, '') AS codigo_consignado,
                  UPPER(COALESCE(u.nLote, '')) AS lote, substr(COALESCE(u.dVal, ''), 1, 10) AS validade,
                  COALESCE(u.fornecedor, '') AS fornecedor, COALESCE(u.marca_fabricante, '') AS marca,
                  COUNT(*) AS quantidade, ROUND(COALESCE(u.vUnCom, 0), 2) AS valor_unitario
           FROM unidades u
           WHERE u.chave_nf = ? AND COALESCE(u.origem, '') = 'xml'
             AND NOT EXISTS (SELECT 1 FROM eventos e WHERE e.id_unidade = u.id_unidade
                             AND e.tipo IN ('cadastro_excluido', 'estorno_entrada_nf'))
           GROUP BY 1, 2, 3, 4, 5, 6, 7, 9
           ORDER BY codigo_aghu, validade, lote""", (texto(chave_nf),))


def xlsx(chave_nf: str) -> tuple[bytes | None, str]:
    """(conteúdo do .xlsx, nome do arquivo) — ou (None, motivo)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    nota = db.consultar_um("SELECT numero_nf, fornecedor FROM notas_fiscais WHERE chave_nf = ?", (texto(chave_nf),))
    if not nota:
        return None, "Nota fiscal não encontrada."
    dados = linhas(chave_nf)
    if not dados:
        return None, "Nenhum item desta nota deu entrada ainda."
    wb = Workbook()
    ws = wb.active
    ws.title = "Entrada AGHU"
    ws.append(COLUNAS)
    for celula in ws[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="0C3A67")
        celula.alignment = Alignment(horizontal="center", vertical="center")
    serie = serie_da_chave(chave_nf)
    for l in dados:
        vu = float(l["valor_unitario"] or 0)
        ws.append([l["codigo_aghu"], l["codigo_master"], l["codigo_consignado"], l["lote"], data_br(l["validade"]) or "",
                   l["fornecedor"], l["marca"], int(l["quantidade"]), texto(nota["numero_nf"]), serie,
                   vu, round(vu * int(l["quantidade"]), 2)])
    # Códigos, lote e validade como TEXTO: o Excel não pode comer zero à esquerda
    # (lote 0039671573) nem trocar a data de formato antes da automação ler.
    for linha in ws.iter_rows(min_row=2, max_col=7):
        for celula in linha:
            celula.number_format = "@"
    for linha in ws.iter_rows(min_row=2, min_col=9, max_col=10):
        for celula in linha:
            celula.number_format = "@"
    for linha in ws.iter_rows(min_row=2, min_col=11, max_col=12):
        for celula in linha:
            celula.number_format = "#,##0.00"
    larguras = [14, 14, 18, 18, 12, 40, 24, 12, 12, 8, 14, 14]
    for i, largura in enumerate(larguras, 1):
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{ws.max_row}"
    saida = io.BytesIO()
    wb.save(saida)
    numero = re.sub(r"[^0-9A-Za-z]", "", texto(nota["numero_nf"])) or "sem_numero"
    return saida.getvalue(), f"NF_{numero}_entrada_AGHU.xlsx"
