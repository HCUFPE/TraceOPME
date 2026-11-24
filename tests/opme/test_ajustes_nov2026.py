"""Ajustes pedidos em nov/2026.

1. Excluir, em "Corrigir cadastro", um item cadastrado por engano.
2. Corrigir a quantidade de um cadastro.
3. Achar o item pelo código bipado (etiqueta GS1 inteira) nas buscas.
4. Código consignado obrigatório quando a classificação é "Consignado".
5. Quantidade obrigatória no cadastro manual (sem valor padrão).
6. Aviso (com ciência, sem travar) de lote com validade mais próxima ao
   enviar à farmácia e ao dispensar para a sala.
"""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["OPME_DB"] = str(os.path.join(tempfile.mkdtemp(), "nov2026.db"))
os.environ["OPME_LOG_DIR"] = tempfile.mkdtemp()

from src.providers.implementations.opme import db  # noqa: E402
from src.providers.implementations.opme.domain import BAIXADO, EM_ESTOQUE_RECEBIMENTO  # noqa: E402
from src.providers.implementations.opme.services import (  # noqa: E402
    atendimentos, dispensacoes, estoque, relatorios, remessas)
from src.providers.implementations.opme.utils import hoje_iso  # noqa: E402

def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


FALHAS: list[str] = []


def conferir(condicao, descricao, extra=""):
    print(("  ok     " if condicao else "  FALHA  ") + descricao
          + (f"   [{extra}]" if not condicao and extra else ""))
    if not condicao:
        FALHAS.append(descricao)


def cadastrar(**dados):
    base = {"xProd": "CATETER BALAO", "codigo_barras": "07606005371551", "codigo_aghu": "92607",
            "fornecedor": "FORN", "marca_fabricante": "MARCA", "nLote": "L1", "dVal": "2031-01-01",
            "quantidade": "3", "tipo_entrada": "aquisicao_propria"}
    return estoque.cadastrar_manual(base | dados, "almox")


def ids_de(lote):
    return [r["id_unidade"] for r in db.consultar(
        "SELECT id_unidade FROM unidades WHERE nLote = ? AND status = ? ORDER BY criado_em, id_unidade",
        (lote, EM_ESTOQUE_RECEBIMENTO))]


db.inicializar()

print("\n5. Quantidade obrigatória")
ok, msg = cadastrar(quantidade="")
conferir(not ok and "quantidade" in msg.lower(), "sem quantidade, o cadastro é recusado", msg)

print("\n4. Código consignado")
ok, msg = cadastrar(tipo_entrada="consignado", nLote="LC0")
conferir(ok and db.escalar("SELECT codigo_consignado FROM unidades WHERE nLote='LC0' LIMIT 1")
         == db.escalar("SELECT codigo_aghu FROM unidades WHERE nLote='LC0' LIMIT 1"),
         "consignado sem relação usa o próprio AGHU (v18.11.4 — não trava)", msg)
ok, msg = cadastrar(tipo_entrada="consignado", nLote="LC", codigo_consignado=" CG-778 ")
conferir(ok, "consignado com código é cadastrado", msg)
conferir({r["codigo_consignado"] for r in db.consultar("SELECT codigo_consignado FROM unidades WHERE nLote='LC'")}
         == {"CG-778"}, "o código consignado fica gravado em cada unidade")
ok, msg = cadastrar(nLote="LA", codigo_consignado="IGNORADO")
conferir(ok and not db.escalar("SELECT COUNT(*) FROM unidades WHERE nLote='LA' AND codigo_consignado <> ''"),
         "fora do consignado o campo não é gravado")
ok, msg = estoque.corrigir_unidade(ids_de("LC")[0], {"codigo_consignado": "CG-779"}, "almox", "código digitado errado")
conferir(ok and "Código consignado" in msg, "o código consignado se corrige em Corrigir cadastro", msg)

print("\n3. Busca pelo código bipado (etiqueta GS1 inteira)")
etiqueta = "0107606005371551172711231023016157"  # (01)07606005371551 (17)271123 (10)23016157
cadastrar(nLote="23016157", dVal="2027-11-23", quantidade="2")
achados = estoque.buscar_unidades(etiqueta)
conferir(achados and all(a["nLote"] == "23016157" for a in achados),
         "Consultas → Itens acha pela etiqueta e mostra o lote da etiqueta", str([a["nLote"] for a in achados]))
conferir(len(estoque.buscar_unidades("7606005371551")) >= 8,
         "GTIN sem o zero à esquerda também acha", str(len(estoque.buscar_unidades("7606005371551"))))
conferir(any(l["nLote"] == "23016157" for l in relatorios.rastrear_por_lote(etiqueta)),
         "rastreio por lote aceita a etiqueta inteira")
conferir(estoque.grupos_para_correcao(etiqueta) and estoque.grupos_para_correcao(etiqueta)[0]["nLote"] == "23016157",
         "Corrigir cadastro acha pela etiqueta")
conferir(estoque.buscar_unidades("10230161571727112", "") is not None, "etiqueta secundária (só lote) não quebra a busca")
conferir(any(a["nLote"] == "23016157" for a in estoque.buscar_unidades("172711231023016157")),
         "etiqueta secundária (só o lote) acha pelo lote")
conferir(estoque.buscar_unidades("CATETER"), "a busca por texto continua igual")

print("\n1. Excluir cadastro errado")
cadastrar(nLote="L1")
ids = ids_de("L1")
ok, msg = estoque.excluir_unidades(ids[:1], "almox", "")
conferir(not ok, "sem motivo não exclui")
ok, msg = estoque.excluir_unidades(ids[:1], "almox", "produto errado no cadastro")
conferir(ok, "exclui a unidade parada no almoxarifado", msg)
u = db.consultar_um("SELECT status FROM unidades WHERE id_unidade = ?", (ids[0],))
ev = db.consultar_um("SELECT * FROM eventos WHERE id_unidade = ? AND tipo = 'cadastro_excluido'", (ids[0],))
conferir(u["status"] == BAIXADO and ev and ev["motivo"] == "produto errado no cadastro",
         "nada é apagado: a unidade fica baixada com o evento e o motivo")
conferir(not any(a["id_unidade"] == ids[0] for a in estoque.buscar_unidades("CATETER", "ativos")),
         "a excluída some do estoque ativo")
ok_r, id_rem = remessas.abrir("BLOCO CIRURGICO", "almox")
r = remessas.bipar(id_rem, ids[1], "almox", ciencia_validade=True)
conferir(r["ok"], "envia uma unidade para a farmácia", r.get("mensagem"))
ok, msg = estoque.excluir_unidades([ids[1], ids[2]], "almox", "entrada em duplicidade")
conferir(not ok and db.consultar_um("SELECT status FROM unidades WHERE id_unidade=?", (ids[2],))["status"]
         == EM_ESTOQUE_RECEBIMENTO, "se uma já andou, recusa e não exclui nenhuma", msg)
from src.providers.implementations.opme import indicadores as _ind  # noqa: E402,F401
conferir(not db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo = 'baixar'"),
         "exclusão de cadastro não conta como baixa (indicador de perda)")

print("\n2. Corrigir a quantidade")
cadastrar(nLote="LQ", quantidade="10")
ids_q = ids_de("LQ")
ok, msg = estoque.ajustar_quantidade(ids_q, "", "almox", "contagem errada")
conferir(not ok, "sem a quantidade nova não ajusta")
ok, msg = estoque.ajustar_quantidade(ids_q, "7", "almox", "eram 7, não 10")
conferir(ok and len(ids_de("LQ")) == 7, "de 10 para 7: exclui 3", msg)
conferir(set(ids_de("LQ")) == set(ids_q[:7]), "as excluídas são as últimas cadastradas")
ok, msg = estoque.ajustar_quantidade(ids_de("LQ"), "12", "almox", "faltou lançar 5")
novas = ids_de("LQ")
conferir(ok and len(novas) == 12, "de 7 para 12: inclui 5 com os mesmos dados", msg)
conferir(db.escalar("SELECT COUNT(DISTINCT xProd || dVal || codigo_aghu || fornecedor) FROM unidades "
                    "WHERE nLote='LQ' AND status=?", (EM_ESTOQUE_RECEBIMENTO,)) == 1,
         "as incluídas têm exatamente os mesmos dados")
conferir(len(estoque.grupos_para_correcao("LQ")) == 1 and estoque.grupos_para_correcao("LQ")[0]["quantidade"] == 12,
         "continuam formando um grupo só em Corrigir cadastro")
db.executar("UPDATE unidades SET origem = 'xml' WHERE nLote = 'LQ'")
ok, msg = estoque.ajustar_quantidade(ids_de("LQ"), "13", "almox", "faltou lançar")
conferir(not ok and "nota fiscal" in msg, "entrada por NF não aumenta por aqui (vai pela NF)", msg)

print("\n6. Aviso de lote com validade mais próxima")
cadastrar(codigo_barras="7891111111111", codigo_aghu="50001", nLote="VENCE-DEPOIS", dVal="2032-01-01", quantidade="2")
cadastrar(codigo_barras="7891111111111", codigo_aghu="50001", nLote="VENCE-ANTES", dVal="2030-06-01", quantidade="2")
depois = ids_de("VENCE-DEPOIS")
r = remessas.bipar(id_rem, depois[0], "almox")
conferir(not r["ok"] and r.get("aviso_validade") and r["mais_proximo"]["lote"] == "VENCE-ANTES",
         "envio: avisa que há lote que vence antes", r.get("mensagem"))
conferir(db.consultar_um("SELECT status FROM unidades WHERE id_unidade=?", (depois[0],))["status"]
         == EM_ESTOQUE_RECEBIMENTO, "envio: antes da ciência nada sai do estoque")
r = remessas.bipar(id_rem, depois[0], "almox", grupo=r["grupo"], ciencia_validade=True)
conferir(r["ok"] and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='ciencia_validade' AND id_unidade=?", (depois[0],)) == 1,
         "envio: com a ciência segue e registra no histórico", r.get("mensagem"))
antes = ids_de("VENCE-ANTES")
r = remessas.bipar(id_rem, antes[0], "almox")
conferir(r["ok"], "envio do lote que vence antes: sem aviso", r.get("mensagem"))

# Farmácia: dois lotes no estoque do Bloco
with db.transacao() as conn:
    for i in ids_de("VENCE-DEPOIS") + ids_de("VENCE-ANTES"):
        conn.execute("UPDATE unidades SET status='em_estoque_farmacia', farmacia='BLOCO CIRURGICO' WHERE id_unidade=?", (i,))
ok, id_at = _abrir_at({"prontuario": "9001", "sala": "02", "especialidade": "CARDIOLOGIA",
                                "data_procedimento": hoje_iso()}, "farm")
farm_depois = [r["id_unidade"] for r in db.consultar(
    "SELECT id_unidade FROM unidades WHERE nLote='VENCE-DEPOIS' AND status='em_estoque_farmacia'")]
r = dispensacoes.bipar(codigo=farm_depois[0], id_atendimento=id_at, usuario="farm",
                       id_unidade=farm_depois[0], farmacia="BLOCO CIRURGICO")
conferir(not r["ok"] and r.get("aviso_validade") and r["escolhido"]["id_unidade"] == farm_depois[0],
         "dispensa: avisa que há lote que vence antes", r.get("mensagem"))
conferir(not db.escalar("SELECT COUNT(*) FROM dispensacao_itens"), "dispensa: nada gravado antes da ciência")
r = dispensacoes.bipar(codigo=farm_depois[0], id_atendimento=id_at, usuario="farm",
                       id_unidade=farm_depois[0], farmacia="BLOCO CIRURGICO", ciencia_validade=True)
conferir(r["ok"] and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='ciencia_validade' AND id_atendimento=?",
                                (id_at,)) == 1, "dispensa: com a ciência segue e registra", r.get("mensagem"))
farm_antes = [r["id_unidade"] for r in db.consultar(
    "SELECT id_unidade FROM unidades WHERE nLote='VENCE-ANTES' AND status='em_estoque_farmacia'")]
r = dispensacoes.bipar(codigo=farm_antes[0], id_atendimento=id_at, usuario="farm",
                       id_unidade=farm_antes[0], farmacia="BLOCO CIRURGICO")
conferir(r["ok"], "dispensa do lote que vence antes: sem aviso", r.get("mensagem"))
conferir("ciencia_validade" in relatorios.ROTULO_TIPO, "a ciência aparece com nome no histórico")

print("\n" + "=" * 60)
if FALHAS:
    print(f"  {len(FALHAS)} verificação(ões) FALHARAM.")
    sys.exit(1)
print("  Todos os ajustes de nov/2026 conferem.")
print("=" * 60)
