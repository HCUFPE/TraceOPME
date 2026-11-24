"""Correção em lote: 100 unidades cadastradas com a validade errada, corrigidas de
uma vez — sem perder o que torna cada uma rastreável.

Os riscos que este teste vigia são os de uma alteração em massa: apagar um
campo que ninguém tocou, sobrescrever o número de série (que é individual),
desfazer sem ver a correção de outra pessoa, e gravar pela metade.
"""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["OPME_DB"] = str(os.path.join(tempfile.mkdtemp(), "lote.db"))
os.environ["OPME_LOG_DIR"] = tempfile.mkdtemp()

from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_RECEBIMENTO, UTILIZADO
from src.providers.implementations.opme.services import estoque

FALHAS: list[str] = []


def conferir(condicao, descricao, extra=""):
    print(("  ok     " if condicao else "  FALHA  ") + descricao
          + (f"   [{extra}]" if not condicao and extra else ""))
    if not condicao:
        FALHAS.append(descricao)


db.inicializar()
U = "camila"

print("\nCenário: entrada manual de 100 unidades com a validade errada")
ok, msg = estoque.cadastrar_manual({
    "xProd": "teste", "codigo_barras": "1111111111", "codigo_aghu": "401029",
    "fornecedor": "teste", "marca_fabricante": "teste", "nLote": "132456",
    "dFab": "2022-02-01", "dVal": "2025-02-01", "quantidade": "100",
    "tipo_entrada": "consignado", "codigo_consignado": "CONS-100",
}, U)
conferir(ok, "100 unidades cadastradas", msg)
ids = [l["id_unidade"] for l in db.consultar(
    "SELECT id_unidade FROM unidades WHERE codigo_barras = '1111111111' ORDER BY id_unidade")]
conferir(len(ids) == 100, "são 100 unidades", str(len(ids)))
# duas delas com número de série próprio — o lote não pode tocar nisso
db.executar("UPDATE unidades SET numero_serie = 'SN-A' WHERE id_unidade = ?", (ids[0],))
db.executar("UPDATE unidades SET numero_serie = 'SN-B' WHERE id_unidade = ?", (ids[1],))
db.executar("UPDATE unidades SET numero_serie = NULL WHERE numero_serie = ''")

print("\nAgrupamento")
grupos = estoque.grupos_para_correcao("1111111111")
conferir(len(grupos) == 1 and grupos[0]["quantidade"] == 100,
         "a busca mostra um grupo com as 100 unidades", str([g["quantidade"] for g in grupos]))
conferir(sorted(grupos[0]["ids"]) == ids, "o grupo traz os ids de todas")

originais = {"xProd": "teste", "codigo_barras": "1111111111", "codigo_aghu": "401029",
             "marca_fabricante": "teste", "fornecedor": "teste", "nLote": "132456",
             "dFab": "2022-02-01", "dVal": "2025-02-01", "vUnCom": "0.0",
             "tipo_entrada": "consignado"}

print("\nSem motivo, nada acontece")
ok, msg = estoque.corrigir_em_lote(ids, {**originais, "dVal": "2027-02-01"}, originais, U, "")
conferir(not ok, "exige motivo", msg)

print("\nSem mudança, nada acontece")
ok, msg = estoque.corrigir_em_lote(ids, dict(originais), originais, U, "teste")
conferir(not ok, "formulário enviado sem mudar nada é recusado", msg)

print("\nA correção da validade, de uma vez")
eventos_antes = db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo = 'correcao'")
ok, msg = estoque.corrigir_em_lote(ids, {**originais, "dVal": "2027-02-01"}, originais, U,
                                   "validade digitada errada na entrada manual")
conferir(ok, "lote aplicado", msg)
conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_barras='1111111111' AND dVal='2027-02-01'") == 100,
         "as 100 unidades estão com a validade nova")
conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo = 'correcao'") - eventos_antes == 100,
         "cada unidade ganhou o seu próprio evento de auditoria")
ev = db.consultar_um("SELECT motivo, observacao FROM eventos WHERE tipo='correcao' AND id_unidade = ?", (ids[5],))
conferir(ev["motivo"] == "validade digitada errada na entrada manual" and "lote de 100" in ev["observacao"],
         "o evento guarda o motivo e diz que foi correção em lote", ev["observacao"])

print("\nO que não foi mudado continua como estava")
conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_barras='1111111111' AND dFab='2022-02-01' AND nLote='132456' AND fornecedor='teste'") == 100,
         "fabricação, lote e fornecedor intactos nas 100")
series = {l["id_unidade"]: l["numero_serie"] for l in db.consultar(
    "SELECT id_unidade, numero_serie FROM unidades WHERE id_unidade IN (?,?)", (ids[0], ids[1]))}
conferir(series == {ids[0]: "SN-A", ids[1]: "SN-B"},
         "números de série individuais preservados", str(series))

print("\nNúmero de série nunca entra no lote, mesmo que venha no formulário")
ok, msg = estoque.corrigir_em_lote(ids[:2], {**originais, "dVal": "2027-02-01", "numero_serie": "SN-X"},
                                   {**originais, "dVal": "2027-02-01"}, U, "teste")
conferir(not ok, "sem outra mudança, o número de série sozinho não é aplicado", msg)
conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE numero_serie='SN-X'") == 0,
         "nenhuma unidade recebeu o número de série do formulário")

print("\nNão desfaz a correção de outra pessoa")
# alguém corrigiu o lote de UMA unidade depois que a tela abriu
estoque.corrigir_unidade(ids[10], {"nLote": "LOTE-CERTO"}, "outra.pessoa", "lote errado nesta")
novos_originais = {**originais, "dVal": "2027-02-01"}
ok, msg = estoque.corrigir_em_lote(ids, {**novos_originais, "fornecedor": "FORNECEDOR CERTO"},
                                   novos_originais, U, "fornecedor errado")
conferir(ok, "lote do fornecedor aplicado", msg)
conferir(db.escalar("SELECT nLote FROM unidades WHERE id_unidade = ?", (ids[10],)) == "LOTE-CERTO",
         "o lote corrigido pela outra pessoa não foi revertido (só vale o campo que mudou)")

print("\nTirar unidades da correção")
alvo = ids[:40]
ok, msg = estoque.corrigir_em_lote(alvo, {**novos_originais, "fornecedor": "FORNECEDOR CERTO",
                                          "marca_fabricante": "MARCA NOVA"},
                                   {**novos_originais, "fornecedor": "FORNECEDOR CERTO"}, U, "marca")
conferir(ok and db.escalar("SELECT COUNT(*) FROM unidades WHERE marca_fabricante='MARCA NOVA'") == 40,
         "só as 40 marcadas foram alteradas", msg)

print("\nTudo ou nada")
db.executar("UPDATE unidades SET status = ? WHERE id_unidade = ?", (UTILIZADO, ids[99]))
antes = db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = 'NOVO'")
ok, msg = estoque.corrigir_em_lote(ids, {**novos_originais, "fornecedor": "FORNECEDOR CERTO", "nLote": "NOVO"},
                                   {**novos_originais, "fornecedor": "FORNECEDOR CERTO"}, U, "teste")
conferir(not ok, "recusa quando uma das unidades já saiu do estoque", msg)
conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote = 'NOVO'") == antes,
         "e nenhuma das outras 99 foi alterada")

print("\n" + "=" * 60)
if FALHAS:
    print(f"  {len(FALHAS)} falha(s): {FALHAS}")
    sys.exit(1)
print("  A correção em lote é segura para uso.")
print("=" * 60)
