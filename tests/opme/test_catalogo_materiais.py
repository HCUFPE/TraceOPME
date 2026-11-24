"""Atualização da lista de materiais do hospital pela tela de Administração.

Usa a planilha real da MasterTools quando ela está disponível na pasta de
testes; senão monta uma planilha mínima. O que se vigia: nada é apagado, nada
muda sem ter mudado, e arquivo errado não estraga o catálogo.
"""
import io, os, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["OPME_DB"] = str(os.path.join(tempfile.mkdtemp(), "cat.db"))
os.environ["OPME_LOG_DIR"] = tempfile.mkdtemp()

from src.providers.implementations.opme import db
from src.providers.implementations.opme.services import materiais

FALHAS = []
def conferir(c, d, extra=""):
    print(("  ok     " if c else "  FALHA  ") + d + (f"   [{extra}]" if not c and extra else ""))
    if not c: FALHAS.append(d)

db.inicializar()

def xlsx(linhas):
    """Planilha .xlsx mínima, montada à mão (texto em linha)."""
    def cel(v, col, lin):
        ref = f"{chr(65 + col)}{lin}"
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>'
    corpo = "".join(f'<row r="{i+1}">' + "".join(cel(v, j, i+1) for j, v in enumerate(l)) + "</row>"
                    for i, l in enumerate(linhas))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="A" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
                   '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   f'<sheetData>{corpo}</sheetData></worksheet>')
    return buf.getvalue()

real = Path(__file__).resolve().parent / "dados" / "mastertools_exemplo.xlsx"
print("\nPrimeira carga")
if real.exists():
    ok, msg, r = materiais.importar_planilha(real.read_bytes(), "mastertools.xlsx", "admin")
    conferir(ok and r["novos"] == 2467 and r["ignoradas"] == 447,
             "planilha real da MasterTools: 2467 códigos, 447 linhas sem AGHU ignoradas", str(r))
    ok, msg, r = materiais.importar_planilha(real.read_bytes(), "mastertools.xlsx", "admin")
    conferir(ok and r["novos"] == 0 and r["alterados"] == 0,
             "subir a MESMA planilha de novo não muda nada (nem espaço duplo conta)", str(r))
    conferir("  " in materiais.descritivo_hospital("400097"),
             "a descrição oficial é guardada exatamente como veio")
else:
    print("  (planilha real ausente — só os casos sintéticos)")

cab = ["Código Master", "Código AGHU", "Nome Material", "Valor Unitário"]
materiais.importar_planilha(xlsx([cab, [1, "900001", "PARAFUSO A", 10.5],
                                   [2, "900002", "PLACA B", 20]]), "v1.xlsx", "admin")

print("\nAtualização: um novo, um alterado, um que saiu")
ok, msg, r = materiais.importar_planilha(
    xlsx([["Nome Material", "Valor Unitário", "Código AGHU"],   # colunas em outra ordem
          ["PARAFUSO A — NOVA DESCRIÇÃO", 11.0, "900001"],
          ["HASTE C", 30, "900003"]]), "v2.xlsx", "camila")
conferir(ok and r["novos"] == 1 and r["alterados"] == 1, "1 novo e 1 alterado", str(r))
conferir(materiais.descritivo_hospital("900001") == "PARAFUSO A — NOVA DESCRIÇÃO",
         "a descrição alterada vale, mesmo com as colunas em outra ordem")
conferir(materiais.descritivo_hospital("900002") == "PLACA B",
         "o código que saiu da planilha continua no sistema")
conferir(materiais.material("900001")["codigo_master"] == "1",
         "coluna ausente na planilha nova não apaga o código master antigo")

print("\nCSV brasileiro")
csvb = "Código AGHU;Nome Material;Valor Unitário\n900004;BROCA D;1.234,56\n".encode("latin-1")
ok, msg, r = materiais.importar_planilha(csvb, "lista.csv", "camila")
conferir(ok and materiais.material("900004")["valor_unitario_licitado"] == 1234.56,
         "CSV com ; e 1.234,56 lido certo", str(materiais.material("900004")))

print("\nArquivo errado")
total = materiais.situacao_catalogo()["total"]
ok, msg, r = materiais.importar_planilha(xlsx([["Prontuário", "Paciente"], ["1", "X"]]), "outra.xlsx", "camila")
conferir(not ok and "AGHU" in msg, "planilha sem as colunas é recusada", msg)
ok, msg, r = materiais.importar_planilha(b"isto nao e uma planilha", "x.xlsx", "camila")
conferir(not ok, "arquivo que não é planilha é recusado", msg)
conferir(materiais.situacao_catalogo()["total"] == total, "e o catálogo continua intacto")

print("\n" + "=" * 60)
if FALHAS:
    print(f"  {len(FALHAS)} falha(s): {FALHAS}"); sys.exit(1)
print("  A lista de materiais atualiza sem perder nada.")
print("=" * 60)
