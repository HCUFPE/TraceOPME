# tests/test_v18_codigo_master.py
"""v18 (item 13): código master pela relação com o AGHU; planilha do robô usa o master."""
import io

from openpyxl import Workbook, load_workbook

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import materiais, planilha_aghu


def _xlsx(linhas):
    wb = Workbook()
    for l in linhas:
        wb.active.append(l)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_relacao_aghu_master(client):
    ok, msg, _ = materiais.importar_planilha(_xlsx([["Código AGHU", "Nome Material"], ["44501", "HC - CATETER X"],
                                                    ["44502", "HC - STENT Y"]]), "mat.xlsx", "admin")
    assert ok, msg
    ok, msg, r = materiais.importar_planilha(_xlsx([["Cód. AGHU", "Código Master"], ["44501", "900123"],
                                                    ["044502", "900456"], ["99999", "1"]]), "rel.xlsx", "admin")
    assert ok and r["relacao_master"], msg
    assert r["alterados"] == 2 and r["fora_do_catalogo"] == 1
    assert materiais.codigo_master("44501") == "900123"
    assert materiais.codigo_master("44502") == "900456"
    # nome não foi apagado
    assert materiais.descritivo_hospital("44502") == "HC - STENT Y"


def test_planilha_robo_tem_master(client):
    chave = "2" * 44
    db.executar("INSERT OR IGNORE INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                (chave, "123", "F", db.agora()))
    db.executar("INSERT INTO unidades (id_unidade, codigo_barras, codigo_aghu, nLote, dVal, fornecedor, marca_fabricante, chave_nf, origem,"
                " status, xProd, criado_em, vUnCom) VALUES ('UMASTER1','789MASTER','44501','L1','2030-01-01','F','M',?,'xml',"
                "'em_estoque_recebimento','X',?,10)", (chave, db.agora()))
    conteudo, _ = planilha_aghu.xlsx(chave)
    ws = load_workbook(io.BytesIO(conteudo)).active
    cab = [c.value for c in ws[1]]
    assert cab[:2] == ["Código AGHU", "Código master"]
    assert ws.cell(2, 2).value == "900123"
