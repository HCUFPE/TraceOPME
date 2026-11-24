"""Ajustes de nov/2026 (segunda leva, versão 17.3.0).

1. NF que traz o número de série no campo lote → grava também como série.
2. O almoxarifado cancela o envio enquanto a farmácia não deu ciência.
3. A farmácia devolve ao almoxarifado bipando; o almoxarifado dá ciência
   (bipando ou pela lista) — com pendência, tratativa e cancelamento.
4. Romaneio (PDF) da devolução ao fornecedor com assinaturas.
5. Empenho pelo código consignado, com associação consignado ↔ AGHU.
"""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["OPME_DB"] = str(os.path.join(tempfile.mkdtemp(), "nov2026b.db"))
os.environ["OPME_LOG_DIR"] = tempfile.mkdtemp()

from src.providers.implementations.opme import db, gs1  # noqa: E402
from src.providers.implementations.opme.domain import (  # noqa: E402
    DIVERGENCIA, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, TRANSITO_ALMOX, TRANSITO_FARMACIA)
from src.providers.implementations.opme.services import (  # noqa: E402
    atendimentos, consignado_aghu, empenhos, estoque, fluxo, remessas, romaneio_fornecedor)
from src.providers.implementations.opme.utils import hoje_iso  # noqa: E402

def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


FALHAS: list[str] = []
QUEM = {"username": "almox", "nome": "Almoxarife"}
FARM = {"username": "farm", "nome": "Farmacêutica"}


def conferir(condicao, descricao, extra=""):
    print(("  ok     " if condicao else "  FALHA  ") + descricao
          + (f"   [{extra}]" if not condicao and extra else ""))
    if not condicao:
        FALHAS.append(descricao)


def cadastrar(**dados):
    base = {"xProd": "CATETER", "codigo_barras": "7896000001001", "codigo_aghu": "92607",
            "fornecedor": "FORN A", "marca_fabricante": "MARCA", "nLote": "L1", "dVal": "2031-01-01",
            "quantidade": "1", "tipo_entrada": "aquisicao_propria"}
    ok, msg = estoque.cadastrar_manual(base | dados, "almox")
    assert ok, msg


def status(id_unidade):
    return db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (id_unidade,))


def ids(lote):
    return [r["id_unidade"] for r in db.consultar("SELECT id_unidade FROM unidades WHERE nLote = ? ORDER BY id_unidade", (lote,))]


db.inicializar()

print("\n1. NF com o número de série no campo lote")
itens = [{"xProd": "LENTE MEDIFLEX", "cEAN": "07899330204645", "nLote": "0000002545", "qtd_total": 1},
         {"xProd": "LENTE MEDIFLEX", "cEAN": "07899330204645", "nLote": "0000002546", "qtd_total": 1},
         {"xProd": "STENT", "cEAN": "07890000000001", "nLote": "LOTE9", "qtd_total": 3},
         {"xProd": "STENT", "cEAN": "07890000000001", "nLote": "LOTE8", "qtd_total": 1},
         {"xProd": "AGULHA", "cEAN": "07890000000002", "nLote": "A1", "qtd_total": 1}]
estoque.marcar_lote_como_serie(itens)
conferir([i["lote_e_serie"] for i in itens] == [1, 1, 0, 0, 0],
         "só o produto com vários lotes de 1 unidade cada é marcado", str([i["lote_e_serie"] for i in itens]))
db.executar("INSERT INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES ('NFL','77','MEDIPHACOS',?)",
            (db.agora(),))
for n, lote in enumerate(("0000002545", "0000002546")):
    db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total, qtd_pendente,
                   criado_em, lote_e_serie) VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                (f"ITL{n}", "NFL", "LENTE MEDIFLEX", "07899330204645", lote, "2030-04-15", 100, 1, 1, db.agora()))
ok, msg = estoque.dar_entrada_item_nf({"id_item": "ITL0", "quantidade": "1", "codigo_aghu": "102739",
                                       "marca_fabricante": "MEDIFLEX"}, "almox")
u = db.consultar_um("SELECT nLote, numero_serie FROM unidades WHERE id_item_nf = 'ITL0'")
conferir(ok and u["nLote"] == "0000002545" and u["numero_serie"] == "0000002545",
         "na entrada, o lote da NF vai também para o número de série", str(dict(u) if u else msg))
ok, msg = estoque.dar_entrada_item_nf({"id_item": "ITL1", "quantidade": "1", "codigo_aghu": "102739",
                                       "marca_fabricante": "MEDIFLEX", "tipo_entrada": "consignado",
                                       "codigo_consignado": "CG-1"}, "almox")
db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total, qtd_pendente, criado_em)
               VALUES ('ITL2','NFL','LENTE MEDIFLEX','07899330204645','0039671573','2029-01-31',100,3,3,?)""", (db.agora(),))
ok2, msg2 = estoque.dar_entrada_item_nf({"id_item": "ITL2", "quantidade": "3", "codigo_aghu": "102739",
                                         "marca_fabricante": "MEDIFLEX"}, "almox")
from src.providers.implementations.opme.services import planilha_aghu
lin = planilha_aghu.linhas("NFL")
conferir(ok and ok2 and len(lin) == 3 and [l["quantidade"] for l in lin] == [3, 1, 1],
         "planilha AGHU: uma linha por lote/validade, com a quantidade somada", str(lin))
conteudo, nome = planilha_aghu.xlsx("NFL")
import io, openpyxl
ws = openpyxl.load_workbook(io.BytesIO(conteudo)).active
conferir([c.value for c in ws[1]] == planilha_aghu.COLUNAS and nome == "NF_77_entrada_AGHU.xlsx",
         "Excel com as colunas pedidas", str([c.value for c in ws[1]]))
# v18: coluna "Código master" entrou na 2ª posição.
conferir(ws["D2"].value == "0039671573" and ws["E2"].value == "31/01/2029" and ws["H2"].value == 3
         and any(r[2].value == "CG-1" for r in ws.iter_rows(min_row=2)),
         "lote com zero à esquerda, validade dd/mm/aaaa, quantidade e código consignado")
conferir(planilha_aghu.xlsx("NAOEXISTE")[0] is None, "nota inexistente não gera planilha")
etq = gs1.interpretar("010789933020464517300415300121S0000002545")
linhas = [{"nLote": "0000002545", "numero_serie": "0000002545", "dVal": "2030-04-15"},
          {"nLote": "0000002546", "numero_serie": "0000002546", "dVal": "2030-04-15"}]
conferir([l["nLote"] for l in gs1.filtrar(linhas, etq)[0]] == ["0000002545"],
         "a etiqueta com série S0000002545 acha a unidade certa")

print("\n2. Cancelar o envio antes da ciência da farmácia")
cadastrar(nLote="ENV", quantidade="3")
ok, id_env = remessas.abrir("BLOCO CIRURGICO", "almox")
r = remessas.bipar(id_env, "7896000001001", "almox", 3)
conferir(r["ok"] and r["total"] == 3, "3 unidades no envio", r.get("mensagem"))
ok, msg = remessas.finalizar_envio(id_env, "almox")
conferir(all(status(i) == TRANSITO_FARMACIA for i in ids("ENV")), "em trânsito para a farmácia")
ok, msg = remessas.cancelar(id_env, "almox", "")
conferir(not ok and "motivo" in msg.lower(), "cancelar exige motivo", msg)
ok, msg = remessas.cancelar(id_env, "almox", "farmácia errada")
rem = remessas.buscar(id_env)
conferir(ok and rem["status"] == "cancelada" and rem["motivo_cancelamento"] == "farmácia errada",
         "envio cancelado com motivo", msg)
conferir(all(status(i) == EM_ESTOQUE_RECEBIMENTO for i in ids("ENV"))
         and not db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote='ENV' AND COALESCE(farmacia,'') <> ''"),
         "os itens voltaram ao estoque do almoxarifado (sem farmácia)")
conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo = 'envio_cancelado'") == 3,
         "o cancelamento fica no histórico de cada item")
ok, msg = remessas.conferir(id_env, set(), FARM)
conferir(not ok, "envio cancelado não pode mais receber ciência", msg)
ok, id_env2 = remessas.abrir("BLOCO CIRURGICO", "almox")
remessas.bipar(id_env2, "7896000001001", "almox", 3)
remessas.finalizar_envio(id_env2, "almox")
itens_env2 = remessas.buscar(id_env2)["pendentes"]
ok, msg = remessas.conferir(id_env2, {str(i["id_item"]) for i in itens_env2}, FARM)
conferir(ok and all(status(i) == EM_ESTOQUE_FARMACIA for i in ids("ENV")), "farmácia dá ciência: entra no estoque dela")
ok, msg = remessas.cancelar(id_env2, "almox", "tarde demais")
conferir(not ok and "ciência" in msg, "depois da ciência não dá para cancelar", msg)

print("\n3. Devolução da farmácia para o almoxarifado")
ok, id_dev = remessas.abrir("BLOCO CIRURGICO", "farm", remessas.DEVOLUCAO)
conferir(ok and id_dev.startswith("DEV"), "devolução aberta", id_dev)
r = remessas.bipar(id_dev, "7896000001001", "farm", 1)
conferir(r["ok"], "farmácia bipa o material do estoque dela", r.get("mensagem"))
r = remessas.bipar(id_dev, "7896000001001", "farm", 5)
conferir(not r["ok"] and "estoque da" in r["mensagem"], "não devolve mais do que tem", r.get("mensagem"))
r = remessas.bipar(id_dev, "7896000001001", "farm", 2)
conferir(r["ok"] and r["total"] == 3, "3 unidades na devolução")
conferir(all(status(i) == TRANSITO_ALMOX for i in ids("ENV")), "saem do estoque da farmácia: em devolução para o almoxarifado")
ok_h, id_hemo = remessas.abrir("HEMODINAMICA - PDT", "farm", remessas.DEVOLUCAO)
conferir(ok_h and id_hemo.startswith("DEV"), "devolução da Hemodinâmica aberta", id_hemo)
r = remessas.bipar(id_hemo, "7896000001001", "farm", 1)
conferir(not r["ok"] and "Hemodinâmica" in r.get("mensagem", ""), "a Hemodinâmica não devolve material do Bloco", r.get("mensagem"))
ok, msg = remessas.finalizar_envio(id_dev, "farm")
conferir(ok and "almoxarifado" in msg, "devolução finalizada", msg)
conferir(remessas.contar_a_receber(sentido=remessas.DEVOLUCAO) == 1 and remessas.contar_a_receber() == 0,
         "aparece para o almoxarifado (e não como envio à farmácia)")
pend = remessas.buscar(id_dev)["pendentes"]
r = remessas.identificar(id_dev, "7896000001001")
conferir(r["ok"] and len(r["itens"]) == 3, "o almoxarifado identifica o item bipado")
recebidos = {str(pend[0]["id_item"]), str(pend[1]["id_item"])}
ok, msg = remessas.conferir(id_dev, recebidos, QUEM, "bipando")
conferir(ok and "do almoxarifado" in msg and "1 item" in msg, "almoxarifado dá ciência bipando (2 de 3)", msg)
conferir([status(i["id_unidade"]) for i in pend] == [EM_ESTOQUE_RECEBIMENTO, EM_ESTOQUE_RECEBIMENTO, TRANSITO_ALMOX],
         "recebidos voltam ao almoxarifado; o não recebido fica pendente")
conferir(not db.escalar("SELECT farmacia FROM unidades WHERE id_unidade = ?", (pend[0]["id_unidade"],)),
         "no almoxarifado a unidade deixa de pertencer à farmácia")
conferir(len(remessas.pendencias(sentido=remessas.DEVOLUCAO)) == 1 and not remessas.pendencias(),
         "pendência aparece só na devolução")
ok, msg = remessas.tratar(pend[2]["id_item"], "voltou_almoxarifado", "farm")
conferir(not ok, "tratativa do envio não vale na devolução", msg)
ok, msg = remessas.tratar(pend[2]["id_item"], "voltou_farmacia", "farm")
conferir(ok and status(pend[2]["id_unidade"]) == EM_ESTOQUE_FARMACIA, "tratativa: voltou ao estoque da farmácia", msg)
conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo = 'receber_almoxarifado'") == 2,
         "a ciência fica no histórico (receber_almoxarifado)")
# pela lista (todos marcados = "dar ciência") e cancelamento
ok, id_dev2 = remessas.abrir("BLOCO CIRURGICO", "farm", remessas.DEVOLUCAO)
remessas.bipar(id_dev2, "7896000001001", "farm", 1)
remessas.finalizar_envio(id_dev2, "farm")
ok, msg = remessas.cancelar(id_dev2, "farm", "devolvi por engano")
conferir(ok and status(pend[2]["id_unidade"]) == EM_ESTOQUE_FARMACIA, "farmácia cancela a devolução antes da ciência", msg)
ok, id_dev3 = remessas.abrir("BLOCO CIRURGICO", "farm", remessas.DEVOLUCAO)
remessas.bipar(id_dev3, "7896000001001", "farm", 1)
remessas.finalizar_envio(id_dev3, "farm")
todos = {str(i["id_item"]) for i in remessas.buscar(id_dev3)["pendentes"]}
ok, msg = remessas.conferir(id_dev3, todos, QUEM, "lista")
conferir(ok and all(status(i) == EM_ESTOQUE_RECEBIMENTO for i in ids("ENV")), "ciência pela lista: tudo no almoxarifado", msg)

print("\n4. Romaneio da devolução ao fornecedor")
cadastrar(nLote="DF1", codigo_barras="7896000002002", quantidade="2", fornecedor="FORN ROM", vUnCom="50")
cadastrar(nLote="DF2", codigo_barras="7896000002003", quantidade="1", fornecedor="OUTRO FORN")
for cod in ("7896000002002", "7896000002002", "7896000002003"):
    r = fluxo.bipar(operacao="devolver_fornecedor", codigo=cod, usuario="almox", motivo="avaria na embalagem")
    conferir(r["ok"], f"devolve {cod} ao fornecedor", r.get("mensagem"))
dev = romaneio_fornecedor.devolucoes(hoje_iso(), hoje_iso())
grupos = romaneio_fornecedor.por_fornecedor(dev)
conferir(len(dev) == 3 and sorted(g["fornecedor"] for g in grupos) == ["FORN ROM", "OUTRO FORN"],
         "devoluções do dia, agrupadas por fornecedor", str([g["fornecedor"] for g in grupos]))
conferir(romaneio_fornecedor.devolucoes(hoje_iso(), hoje_iso(), "FORN ROM").__len__() == 2, "filtro por fornecedor")
ids_rom = [l["id_unidade"] for l in dev if l["fornecedor_nome"] == "FORN ROM"]
pdf, nome = romaneio_fornecedor.pdf(ids_rom, "Almoxarife")
conferir(pdf and pdf.startswith(b"%PDF") and nome.endswith(".pdf"), "PDF do romaneio gerado", nome)
conferir(pdf and b"Pelo fornecedor" in pdf and b"Pelo hospital" in pdf and b"FORN ROM" in pdf,
         "romaneio tem assinatura do hospital e do fornecedor")
conferir(pdf and b"avaria na embalagem" in pdf and b"DF1" in pdf, "romaneio lista lote e motivo")
pdf2, msg = romaneio_fornecedor.pdf([l["id_unidade"] for l in dev], "x")
conferir(pdf2 is None and "fornecedor" in msg, "um romaneio por fornecedor", msg)

print("\n5. Empenho pelo código consignado")
ok, msg = consignado_aghu.salvar(" c-55 ", "400555", "almox", "FORN C")
conferir(ok and consignado_aghu.aghu_de("C-55") == "400555", "associação gravada (código normalizado)", msg)
ok, id_emp = empenhos.cadastrar({"numero": "EC1", "fornecedor": "FORN C", "codigos_consignado": "C-55",
                                 "quantidade_total": "3", "valor_unitario": "10", "data_empenho": "2026-01-01"}, "almox")
emp = empenhos.buscar(id_emp) if ok else {}
conferir(ok and emp["pares"] == [{"consignado": "C-55", "aghu": "400555"}] and emp["codigos_aghu"] == ["400555"],
         "empenho só com o código consignado: o AGHU vem da associação", str(emp.get("pares")))
conferir(empenhos.listar(termo="C-55") and empenhos.listar(termo="C-55")[0]["id_empenho"] == id_emp,
         "busca de empenho pelo código consignado")
ok_ex, msg = consignado_aghu.excluir("C-55", "almox")
conferir(not ok_ex and "empenho" in msg, "associação usada em empenho ativo não é excluída", msg)
ok, at = _abrir_at({"prontuario": "123", "sala": "01", "especialidade": "CARDIOLOGIA",
                             "data_procedimento": hoje_iso()}, "sala1")
cadastrar(nLote="EC", codigo_barras="7896000003001", codigo_aghu="400555", tipo_entrada="consignado",
          codigo_consignado="C-55")
cadastrar(nLote="ED", codigo_barras="7896000003002", codigo_aghu="400555", tipo_entrada="consignado",
          codigo_consignado="C-66")
r = fluxo.bipar(operacao="registrar_uso", codigo="7896000003001", usuario="sala1", id_atendimento=at)
conferir(r["ok"] and "EC1" in (r.get("empenho") or "") and empenhos.buscar(id_emp)["saldo"] == 2,
         "uso de unidade com o código consignado debita o empenho", r.get("empenho"))
r = fluxo.bipar(operacao="registrar_uso", codigo="7896000003002", usuario="sala1", id_atendimento=at)
conferir(r["ok"] and empenhos.buscar(id_emp)["saldo"] == 2 and "C-66" in (r.get("empenho") or ""),
         "outro código consignado com o mesmo AGHU NÃO debita este empenho", r.get("empenho"))
vinc = empenhos.vinculos_do_empenho(id_emp)
conferir(vinc and vinc[0]["codigo_consignado"] == "C-55" and vinc[0]["codigo_aghu"] == "400555",
         "vínculos do empenho trazem o código consignado e o AGHU")
pdf_emp = empenhos.pdf_vinculos(id_emp)
conferir(pdf_emp and b"C-55" in pdf_emp, "PDF do empenho mostra o código consignado")
# nov/2026: mais de um empenho do mesmo material → debita o de fim de vigência mais próximo.
consignado_aghu.salvar("C-88", "400888", "almox")
base_emp = {"fornecedor": "FORN C", "codigos_consignado": "C-88", "quantidade_total": "5", "valor_unitario": "10",
            "vigencia_inicio": "2026-01-01"}
ok1, emp_longe = empenhos.cadastrar(base_emp | {"numero": "LONGE", "vigencia_fim": "2027-12-31",
                                                "data_empenho": "2026-01-01"}, "almox")
ok2, emp_perto = empenhos.cadastrar(base_emp | {"numero": "PERTO", "vigencia_fim": "2026-12-31",
                                                "data_empenho": "2026-06-01"}, "almox")
ok3, emp_sem = empenhos.cadastrar(base_emp | {"numero": "SEMFIM", "data_empenho": "2025-01-01",
                                              "vigencia_inicio": ""}, "almox")
cadastrar(nLote="EV", codigo_barras="7896000003088", codigo_aghu="400888", tipo_entrada="consignado",
          codigo_consignado="C-88")
r = fluxo.bipar(operacao="registrar_uso", codigo="7896000003088", usuario="sala1", id_atendimento=at)
conferir(ok1 and ok2 and ok3 and "PERTO" in (r.get("empenho") or "") and empenhos.buscar(emp_perto)["saldo"] == 4
         and empenhos.buscar(emp_longe)["saldo"] == 5,
         "com dois empenhos do mesmo material, debita o de fim de vigência mais próximo", r.get("empenho"))
ok, msg, res = consignado_aghu.importar_planilha(
    "Código consignado;Código AGHU;Fornecedor\nP-1;400601;F\nP-2;;F\n".encode("utf-8"), "a.csv", "almox")
conferir(res["salvos"] == 1 and len(res["erros"]) == 1 and consignado_aghu.aghu_de("P-1") == "400601",
         "importação de associações por planilha", msg)

print("\n" + "=" * 60)
if FALHAS:
    print(f"  {len(FALHAS)} verificação(ões) falharam:")
    for f in FALHAS:
        print("   -", f)
    sys.exit(1)
print("  Todas as verificações passaram.")
