"""Versão 17 — suíte completa portada para o Framework SETISD.

Executar:  python -m tests.opme.test_v17   (ou: pytest tests/)
Banco temporário; nada toca o banco de produção.
"""

import os
import sys
import tempfile
from pathlib import Path

def _abrir_at(dados, usuario, *a, **k):
    """v18.9: registrar uso exige a sala aberta — nestes testes antigos a sala é aberta junto."""
    ok, ida = atendimentos.abrir(dados, usuario, *a, **k)
    if ok:
        db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = ?",
                    (db.agora(), ida))
    return ok, ida


RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
_temp = tempfile.mkdtemp(prefix="opme_v17_")
os.environ["OPME_DB"] = str(Path(_temp) / "teste.db")
os.environ["OPME_LOG_DIR"] = str(Path(_temp) / "logs")
os.environ["APP_DB_URL"] = f"sqlite+aiosqlite:///{Path(_temp) / 'app.db'}"
os.environ.pop("AD_URL", None)  # testes no modo local (senhas do próprio TraceOPME)

from src.providers.implementations.opme import db  # noqa: E402
from src.providers.implementations.opme.domain import (  # noqa: E402
    BAIXADO, DIVERGENCIA, EM_ESTOQUE_RECEBIMENTO, OPERACOES, UTILIZADO,
)
from src.providers.implementations.opme.services import atendimentos, caixas, estoque, fluxo, relatorios  # noqa: E402
from src.providers.implementations.opme.utils import hoje_iso  # noqa: E402


def _abrir_sala_da_disp(id_disp):
    """v18.3: a sala abre a sala antes de dar ciência do material."""
    db.executar("UPDATE atendimentos SET sala_aberta_em = COALESCE(sala_aberta_em, ?) WHERE id_atendimento = "
                "(SELECT id_atendimento FROM dispensacoes WHERE id_dispensacao = ?)", (db.agora(), id_disp))

FALHAS: list[str] = []
TOTAL = 0


def conferir(condicao, descricao: str, detalhe="") -> None:
    global TOTAL
    TOTAL += 1
    print(f"  {'ok  ' if condicao else 'FALHA'} {descricao} {'' if condicao else detalhe}")
    if not condicao:
        FALHAS.append(descricao)


def unidade(codigo_barras: str, n: int = 0) -> dict:
    return db.consultar(
        "SELECT * FROM unidades WHERE codigo_barras = ? ORDER BY id_unidade", (codigo_barras,))[n]


def cadastrar(xprod, barras, lote, validade, qtd="1", farmacia=None, **extra):  # extra: tipo_entrada etc.
    """`farmacia`: já coloca no estoque da farmácia (como se o almoxarifado tivesse
    enviado e a farmácia dado ciência) — a farmácia só dispensa do estoque dela."""
    antes = {r["id_unidade"] for r in db.consultar("SELECT id_unidade FROM unidades WHERE codigo_barras = ?", (barras,))}
    if extra.get("tipo_entrada") == "consignado":
        extra.setdefault("codigo_consignado", "CONS-TESTE")
    ok, msg = estoque.cadastrar_manual({
        "xProd": xprod, "codigo_barras": barras, "codigo_aghu": "400097",
        "fornecedor": "ORTOMED", "marca_fabricante": "Orto", "nLote": lote,
        "dVal": validade, "quantidade": qtd, "vUnCom": "500", **extra}, "almox")
    assert ok, msg
    if farmacia:
        novos = [r["id_unidade"] for r in db.consultar("SELECT id_unidade FROM unidades WHERE codigo_barras = ?", (barras,))
                 if r["id_unidade"] not in antes]
        with db.transacao() as conn:
            for u in novos:
                conn.execute("UPDATE unidades SET status = 'em_estoque_farmacia', farmacia = ? WHERE id_unidade = ?",
                             (farmacia, u))


def main() -> int:
    db.inicializar()

    print("== Operações disponíveis")
    removidas = ("enviar_farmacia", "conferir_farmacia", "separar",
                 "enviar_sala", "conferir_sala", "devolver_farmacia", "conferir_retorno",
                 "cancelar_separacao", "estornar_envio_farmacia")
    conferir(all(o not in OPERACOES for o in removidas),
             "nenhuma operação de farmácia/dispensação/devolução existe mais")
    conferir(EM_ESTOQUE_RECEBIMENTO in OPERACOES["registrar_uso"].de and "dispensar_sala" in OPERACOES,
             "registrar uso aceita estoque e dispensado; dispensação da farmácia existe")
    r = fluxo.bipar(operacao="enviar_farmacia", codigo="x", usuario="u")
    conferir(not r["ok"], "bipar numa operação removida é recusado")

    print("== Cadastro e uso direto")
    cadastrar("HASTE FEMORAL", "7890000000017", "L1", "01/06/2030", qtd="2")
    conferir(unidade("7890000000017")["status"] == EM_ESTOQUE_RECEBIMENTO,
             "cadastro manual entra em estoque no almoxarifado")
    ok, id_at = _abrir_at({"prontuario": "21.472.063", "paciente": "Paciente",
                                    "sala": "02", "especialidade": "ORTOPEDIA",
                                    "data_procedimento": hoje_iso()}, "sala1")
    conferir(ok, "a sala abre o atendimento")

    r = fluxo.bipar(operacao="registrar_uso", codigo="7890000000017", usuario="sala1")
    conferir(not r["ok"], "uso sem atendimento é recusado")

    r = fluxo.bipar(operacao="registrar_uso", codigo="7890000000017", usuario="sala1",
                    id_atendimento=id_at)
    conferir(r["ok"], "uso bipado direto do estoque do almoxarifado", r.get("mensagem"))
    u = fluxo.buscar_unidade(r["item"]["id_unidade"])
    conferir(u["status"] == UTILIZADO and u["id_atendimento"] == id_at,
             "item fica Utilizado e vinculado ao atendimento/prontuário")
    evento = db.consultar_um("SELECT * FROM eventos WHERE id_unidade = ? AND tipo='registrar_uso'",
                             (u["id_unidade"],))
    conferir(evento and evento["status_anterior"] == EM_ESTOQUE_RECEBIMENTO
             and evento["usuario"] == "sala1", "evento de uso gravado com quem bipou e de onde saiu")

    r = fluxo.bipar(operacao="registrar_uso", codigo="7890000000017", usuario="sala1",
                    id_atendimento=id_at)
    conferir(r["ok"] and all(unidade("7890000000017", i)["status"] == UTILIZADO for i in (0, 1)),
             "segunda leitura do mesmo código usa a segunda unidade")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7890000000017", usuario="sala1",
                    id_atendimento=id_at)
    conferir(not r["ok"] and "utilizado" in r["mensagem"].lower(),
             "terceira leitura: não há mais unidade — recusa clara", r.get("mensagem"))

    print("== Vencido e lote diferente")
    cadastrar("PLACA", "7891111111111", "LV", "01/01/2020")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7891111111111", usuario="sala1",
                    id_atendimento=id_at)
    conferir(not r["ok"] and unidade("7891111111111")["status"] == EM_ESTOQUE_RECEBIMENTO,
             "vencido sem justificativa não é registrado")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7891111111111", usuario="sala1",
                    id_atendimento=id_at, motivo="implantado antes de conferir a validade")
    conferir(r["ok"], "vencido com justificativa é registrado (e vira alerta)")

    cadastrar("PARAFUSO", "7892222222222", "LA", "01/01/2031")
    cadastrar("PARAFUSO", "7892222222222", "LB", "01/01/2032")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7892222222222", usuario="sala1",
                    id_atendimento=id_at)
    conferir(r.get("escolha") and len(r["opcoes"]) == 2,
             "mesmo código com lotes diferentes: pede para escolher")

    print("== Estorno e desfazer")
    usado = unidade("7890000000017", 0)["id_unidade"]
    ok, msg = fluxo.estornar_uso(usado, "sala1", "bipado no paciente errado")
    u = fluxo.buscar_unidade(usado)
    # v18: o estorno volta pela farmácia, com ciência (devolução pendente).
    from src.providers.implementations.opme.services import devolucoes as _dev18
    dv18 = _dev18.pendente_do_atendimento(id_at)
    conferir(ok and u["status"] == "em_sala" and u["id_atendimento"] == id_at and dv18,
             "v18: estorno fica aguardando a ciência da farmácia", msg)
    ok, msg = _dev18.confirmar(id_devolucao=dv18["id_devolucao"], operador="admin",
                               responsavel={"username": "admin", "nome": "Admin", "papel": "admin"})
    u = fluxo.buscar_unidade(usado)
    conferir(ok and u["status"] == EM_ESTOQUE_RECEBIMENTO and not u["id_atendimento"],
             "estorno devolve ao estoque (depois da ciência) e desvincula o paciente", msg)
    conferir(set(fluxo.DESTINOS_ESTORNO) == {EM_ESTOQUE_RECEBIMENTO, DIVERGENCIA, BAIXADO},
             "destinos de estorno sem farmácia/sala")
    r = fluxo.bipar(operacao="registrar_uso", codigo=usado, usuario="sala1", id_atendimento=id_at)
    ok, msg = fluxo.desfazer_ultimo(usado, "sala1", "teste")
    u = fluxo.buscar_unidade(usado)
    conferir(ok and u["status"] == EM_ESTOQUE_RECEBIMENTO and not u["id_atendimento"],
             "desfazer o uso volta ao almoxarifado sem paciente", msg)

    print("== Entrega da caixa ao paciente")
    from src.providers.implementations.opme.services import entrega_paciente
    ok, msg = entrega_paciente.marcar("400200, 400201\n400200", "cartão de implante", "admin")
    conferir(ok and "2 código(s) incluído(s)" in msg, "admin inclui códigos (repetido ignorado)", msg)
    ok, msg = estoque.cadastrar_manual({
        "xProd": "STENT", "codigo_barras": "7894444444444", "codigo_aghu": "400200",
        "fornecedor": "CARDIO", "marca_fabricante": "Cardio", "nLote": "LS",
        "dVal": "01/01/2031", "quantidade": "1", "vUnCom": "900"}, "almox")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7894444444444", usuario="sala1",
                    id_atendimento=id_at)
    conferir(r["ok"] and r.get("entrega_paciente", {}).get("aghu") == "400200",
             "bipar AGHU da lista devolve o aviso de entrega ao paciente")
    r2 = fluxo.bipar(operacao="registrar_uso", codigo="7892222222222", usuario="sala1",
                     id_atendimento=id_at, id_unidade=unidade("7892222222222", 0)["id_unidade"])
    conferir(r2["ok"] and "entrega_paciente" not in r2, "AGHU fora da lista não avisa")
    ok, msg = atendimentos.encerrar(id_at, "sala1")
    conferir(not ok and "ciência" in msg, "não encerra sem a ciência da entrega", msg)
    ok, msg = entrega_paciente.registrar_ciencia(r["item"]["id_unidade"], "sala1")
    conferir(ok and not entrega_paciente.pendentes_de_ciencia(id_at), "ciência registrada", msg)

    print("== Concluir: excluir bip")
    alvo = r2["item"]["id_unidade"]
    ok, msg = fluxo.excluir_bip(alvo, id_at, "sala1", "")
    conferir(not ok, "excluir bip exige motivo")
    ok, msg = fluxo.excluir_bip(alvo, id_at, "sala1", "Bipado em duplicidade")
    u = fluxo.buscar_unidade(alvo)
    conferir(ok and u["status"] == EM_ESTOQUE_RECEBIMENTO and not u["id_atendimento"],
             "bip excluído volta ao estoque sem paciente", msg)
    conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE id_unidade=? AND tipo='excluir_bip'",
                        (alvo,)) == 1, "exclusão fica no histórico com motivo")

    print("== Encerrar e reabrir")
    ok, msg = atendimentos.encerrar(id_at, "sala1")
    conferir(ok, "atendimento encerra depois da conclusão", msg)
    r = fluxo.bipar(operacao="registrar_uso", codigo=usado, usuario="sala1", id_atendimento=id_at)
    conferir(not r["ok"] and "encerrado" in r["mensagem"],
             "não registra uso em atendimento encerrado")
    usado_agora = db.consultar_um(
        "SELECT id_unidade FROM unidades WHERE id_atendimento=? AND status=?", (id_at, UTILIZADO))["id_unidade"]
    ok, _ = fluxo.excluir_bip(usado_agora, id_at, "sala1", "Bipado em duplicidade")
    conferir(not ok, "encerrado: não exclui bip")
    ok, _ = fluxo.desfazer_ultimo(usado_agora, "sala1", "x")
    conferir(not ok, "encerrado: não desfaz")
    # v18: estorno depois de encerrado é permitido (bipado em duplicidade) e volta pela farmácia.
    ok, msg = fluxo.estornar_uso(usado_agora, "sala1", "bipado em duplicidade depois de encerrar")
    dv18 = _dev18.pendente_do_atendimento(id_at)
    conferir(ok and fluxo.buscar_unidade(usado_agora)["status"] == "em_sala" and dv18,
             "v18: encerrado estorna e aguarda a ciência da farmácia", msg)
    ok, msg = _dev18.confirmar(id_devolucao=dv18["id_devolucao"], operador="admin",
                               responsavel={"username": "admin", "nome": "Admin", "papel": "admin"})
    conferir(ok and fluxo.buscar_unidade(usado_agora)["status"] == EM_ESTOQUE_RECEBIMENTO,
             "v18: ciência da farmácia devolve ao estoque", msg)

    from src.providers.implementations.opme.security import gerar_hash
    for nome, papel in (("sup1", "supervisao"), ("sala2", "sala-procedimento")):
        db.executar("""INSERT INTO usuarios (username, senha_hash, nome, email, setor, papel, status, criado_em)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (nome, gerar_hash("Senha2026"), nome.upper(), "", "", papel, "ativo", db.agora()))
    ok, msg = atendimentos.reabrir(id_at, "sala1", "sala2", "Senha2026", "material esquecido")
    conferir(not ok and "Supervisão" in msg, "sala não reabre sozinha", msg)
    ok, msg = atendimentos.reabrir(id_at, "sala1", "sup1", "errada123", "material esquecido")
    conferir(not ok, "senha errada da supervisora não reabre")
    ok, msg = atendimentos.reabrir(id_at, "sala1", "sup1", "Senha2026", "")
    conferir(not ok, "reabrir exige motivo")
    ok, msg = atendimentos.reabrir(id_at, "sala1", "sup1", "Senha2026", "material esquecido")
    conferir(ok and atendimentos.buscar(id_at)["status"] == "aberto", "supervisora reabre com a senha", msg)
    ev = db.consultar_um("SELECT * FROM eventos WHERE tipo='atendimento_reaberto' AND id_atendimento=?", (id_at,))
    conferir(ev and ev["usuario"] == "sup1" and ev["motivo"], "reabertura registra quem autorizou e o motivo")
    r = fluxo.bipar(operacao="registrar_uso", codigo=usado, usuario="sala1", id_atendimento=id_at)
    conferir(r["ok"], "reaberto: volta a bipar o material esquecido", r.get("mensagem"))
    ok, msg = atendimentos.encerrar(id_at, "sala1")
    conferir(ok, "encerra de novo")

    print("== Inventário do almoxarifado")
    from src.providers.implementations.opme.services import inventario
    conferir(list(inventario.locais())[0] == "almoxarifado" and len(inventario.locais()) == 3,
             "locais a contar: almoxarifado, Farmácia do Bloco e Farmácia da Hemodinâmica")
    ok, msg, id_inv = inventario.abrir("almoxarifado", "almox", "teste")
    conferir(ok and id_inv, "contagem aberta no almoxarifado", msg)
    r = inventario.bipar(id_inv, "7892222222222", "almox")
    conferir(r.get("ok"), "material do estoque confere na contagem", r.get("mensagem"))
    inventario.bipar(id_inv, "7890000000000", "almox")
    rel = inventario.relatorio(id_inv)
    conferir(isinstance(rel, dict), "relatório da contagem sai")
    cons = {l["codigo_aghu"]: l for l in rel["consolidado"]}
    tot_esp = sum(l["esperado"] for l in rel["consolidado"])
    conferir(tot_esp == rel["resumo"]["esperados"]
             and sum(l["encontrado"] for l in rel["consolidado"]) == rel["resumo"]["conferidos"]
             and sum(l["nao_encontrado"] for l in rel["consolidado"]) == len(rel["nao_encontrados"])
             and cons.get("sem cadastro", {}).get("a_mais") == 1,
             "inventário: consolidado por AGHU (esperado, encontrado, não encontrado, a mais)")
    csv_c = inventario.consolidado_para_exportar(id_inv)
    conferir(csv_c and "nao_encontrado" in csv_c[0], "consolidado exporta em CSV")

    print("== Utilizados hoje conta a unidade, não o bip")
    from src.providers.implementations.opme.services import relatorios as _rl
    antes_uso = _rl.usos_do_dia()
    _u1, _u2 = [l["id_unidade"] for l in db.consultar("SELECT id_unidade FROM unidades WHERE status = 'em_estoque_recebimento' LIMIT 2")]
    with db.transacao() as _c:
        for _ in range(3):
            db.registrar_evento(_c, tipo="registrar_uso", id_unidade=_u1, usuario="t", status_anterior="", status_novo="utilizado")
        db.registrar_evento(_c, tipo="registrar_uso", id_unidade=_u2, usuario="t", status_anterior="", status_novo="utilizado")
        _c.execute("UPDATE unidades SET status = 'utilizado' WHERE id_unidade = ?", (_u1,))
    conferir(_rl.usos_do_dia() == antes_uso + 1, "bipado 3x (2 excluídos) conta 1; bipado e excluído não conta")
    with db.transacao() as _c:
        _c.execute("UPDATE unidades SET status = 'em_estoque_recebimento' WHERE id_unidade = ?", (_u1,))

    print("== Cancelamento de procedimento")
    from src.providers.implementations.opme.services import indicadores as calc
    ok, id_c1 = _abrir_at({"prontuario": "5551", "sala": "03", "especialidade": "VASCULAR",
                                    "data_procedimento": hoje_iso(), "opme_solicitado": "endoprótese"}, "sala1")
    ok, id_c2 = _abrir_at({"prontuario": "5552", "sala": "04", "especialidade": "VASCULAR",
                                    "data_procedimento": hoje_iso(), "opme_solicitado": "stent"}, "sala1")
    ok, msg = atendimentos.cancelar(id_c1, "sala1", "", "")
    conferir(not ok, "cancelar exige motivo")
    ok, msg = atendimentos.cancelar(id_c1, "sala1", "Outro", "")
    conferir(not ok, "motivo 'Outro' exige descrição")
    ok, msg = atendimentos.cancelar(id_c1, "sala1", "Falta de leito / UTI", "")
    conferir(ok and atendimentos.buscar(id_c1)["status"] == "cancelado", "procedimento cancelado com motivo", msg)
    ok, msg = atendimentos.cancelar(id_c1, "sala1", "Falta de leito / UTI", "")
    conferir(not ok, "não cancela duas vezes")
    r = fluxo.bipar(operacao="registrar_uso", codigo=usado, usuario="sala1", id_atendimento=id_c1)
    conferir(not r["ok"], "cancelado não recebe bip")
    cadastrar("CATETER", "7895555555555", "LK", "01/01/2031")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895555555555", usuario="sala1", id_atendimento=id_c2)
    conferir(r["ok"], "bip no segundo atendimento", r.get("mensagem"))
    ok, msg = atendimentos.cancelar(id_c2, "sala1", "Falta de leito / UTI", "")
    conferir(not ok and "utilizado" in msg, "com material usado não cancela (exclua o bip antes)", msg)
    det = calc.cancelamentos(hoje_iso(), hoje_iso())
    conferir(det["cancelados"] == 1 and det["previstos"] >= 3
             and det["por_motivo"][0]["motivo"] == "Falta de leito / UTI",
             "indicador conta cancelados ÷ previstos e agrupa por motivo", str(det)[:200])
    valores = calc.calcular_valores(hoje_iso(), hoje_iso())
    conferir(valores["taxa_cancelamento"] == round(100 * det["cancelados"] / det["previstos"], 1)
             or abs(valores["taxa_cancelamento"] - 100 * det["cancelados"] / det["previstos"]) < 0.1,
             "taxa de cancelamento calculada", str(valores["taxa_cancelamento"]))
    ok, msg = atendimentos.reabrir(id_c1, "sala1", "sup1", "Senha2026", "cancelado por engano")
    conferir(ok and not atendimentos.buscar(id_c1)["motivo_cancelamento"],
             "supervisão reabre cancelado por engano (limpa o motivo)", msg)
    atendimentos.cancelar(id_c1, "sala1", "Falta de leito / UTI", "")

    print("== Empenho por código consignado (associado ao AGHU) — nov/2026")
    from src.providers.implementations.opme.services import empenhos
    ok, msg = empenhos.cadastrar({"numero": "E1", "fornecedor": "MEDFORN", "quantidade_total": "5",
                                  "valor_unitario": "100"}, "almox")
    conferir(not ok and "consignado" in msg, "empenho exige código consignado", msg)
    ok, msg = empenhos.cadastrar({"numero": "E1", "fornecedor": "MEDFORN", "codigos_consignado": "CONS-100",
                                  "quantidade_total": "5", "valor_unitario": "100"}, "almox")
    conferir(not ok and "AGHU" in msg, "código consignado sem associação e sem AGHU é recusado", msg)
    ok, msg = empenhos.cadastrar({"numero": "E1", "fornecedor": "MEDFORN", "codigos_consignado": "CONS-100",
                                  "codigos_aghu": "500100",
                                  "material": "Balão", "quantidade_total": "5",
                                  "valor_unitario": "100", "limite_seguranca": "5"}, "almox")
    conferir(not ok, "limite de segurança precisa ser menor que a quantidade")
    ok, id_e1 = empenhos.cadastrar({"numero": "E1", "fornecedor": "MEDFORN",
                                    "pares": [("CONS-100", "500100"), ("cons-101", "500101")], "material": "Balão",
                                    "quantidade_total": "3", "valor_unitario": "100",
                                    "limite_seguranca": "1", "data_empenho": "2026-01-01"}, "almox")
    conferir(ok, "empenho cadastrado com dois códigos consignados (e seus AGHU)", id_e1)
    conferir(ok and empenhos.buscar(id_e1)["pares"] == [{"consignado": "CONS-100", "aghu": "500100"},
                                                       {"consignado": "CONS-101", "aghu": "500101"}]
             and empenhos.buscar(id_e1)["codigos_aghu"] == ["500100", "500101"],
             "empenho guarda consignado → AGHU", str(empenhos.buscar(id_e1)["pares"] if ok else ""))
    from src.providers.implementations.opme.services import consignado_aghu
    conferir(consignado_aghu.aghu_de("cons-100") == "500100", "a associação consignado → AGHU foi criada no cadastro")
    ok, msg = empenhos.cadastrar({"numero": "EX", "fornecedor": "MEDFORN", "pares": [("CONS-100", "500999")],
                                  "quantidade_total": "2", "valor_unitario": "100"}, "almox")
    conferir(not ok and "500100" in msg, "AGHU diferente do associado é recusado", msg)
    ok, id_e2 = empenhos.cadastrar({"numero": "E2", "fornecedor": "MEDFORN", "codigos_consignado": "CONS-100",
                                    "material": "Balão", "quantidade_total": "2",
                                    "valor_unitario": "100", "data_empenho": "2026-02-01"}, "almox")
    conferir(empenhos.buscar(id_e2)["limite"] == 1, "limite padrão = 20% (arredondado para cima)")
    ok, id_ae = _abrir_at({"prontuario": "8881", "sala": "05", "especialidade": "CARDIOLOGIA",
                                    "data_procedimento": hoje_iso(), "opme_solicitado": "balão"}, "sala1")
    for i, (aghu, barras) in enumerate((("500100", "7896000000100"), ("500101", "7896000000101"),
                                        ("500100", "7896000000102"), ("500100", "7896000000103"))):
        estoque.cadastrar_manual({"xProd": "BALAO", "codigo_barras": barras, "codigo_aghu": aghu,
                                  "fornecedor": "MEDFORN", "marca_fabricante": "Med", "nLote": f"LB{i}",
                                  "dVal": "01/01/2031", "quantidade": "1", "vUnCom": "100",
                                  "tipo_entrada": "consignado", "codigo_consignado": f"CONS-{aghu[-3:]}"}, "almox")
    r1 = fluxo.bipar(operacao="registrar_uso", codigo="7896000000100", usuario="sala1", id_atendimento=id_ae)
    conferir(r1["ok"] and "saldo 2 de 3" in r1.get("empenho", ""), "uso debita o empenho mais antigo", r1.get("empenho"))
    r2 = fluxo.bipar(operacao="registrar_uso", codigo="7896000000101", usuario="sala1", id_atendimento=id_ae)
    conferir("LIMITE DE SEGURANÇA" in r2.get("empenho", "") and r2["alertas"],
             "segundo código do mesmo empenho debita e avisa o limite de segurança", r2.get("empenho"))
    conferir(db.escalar("SELECT COUNT(*) FROM alertas WHERE titulo LIKE 'Comprar mais empenho%'") == 1,
             "alerta 'comprar mais empenho' criado uma vez")
    conferir(any(e["id_empenho"] == id_e1 for e in empenhos.no_limite()), "empenho aparece como no limite")
    painel = relatorios.painel()
    conferir(any(p["chave"] == "empenho_no_limite" for p in painel["pendencias"]),
             "painel mostra pendência de pedir mais empenho")
    r3 = fluxo.bipar(operacao="registrar_uso", codigo="7896000000102", usuario="sala1", id_atendimento=id_ae)
    conferir(empenhos.buscar(id_e1)["saldo"] == 0 and "E1" in r3.get("empenho", ""),
             "terceiro uso zera o primeiro empenho")
    r4 = fluxo.bipar(operacao="registrar_uso", codigo="7896000000103", usuario="sala1", id_atendimento=id_ae)
    conferir("Empenho E2" in r4.get("empenho", ""), "esgotado o primeiro, passa para o próximo empenho do AGHU",
             r4.get("empenho"))
    ok, _ = fluxo.excluir_bip(r4["item"]["id_unidade"], id_ae, "sala1", "Bipado em duplicidade")
    conferir(ok and empenhos.buscar(id_e2)["saldo"] == 2, "excluir o bip devolve o saldo ao empenho")
    ok, _ = fluxo.estornar_uso(r3["item"]["id_unidade"], "sala1", "bipado no paciente errado")
    conferir(ok and empenhos.buscar(id_e1)["saldo"] == 1, "estorno do uso devolve o saldo")
    empenhos.encerrar(id_e1, "almox"); empenhos.encerrar(id_e2, "almox")
    estoque.cadastrar_manual({"xProd": "BALAO", "codigo_barras": "7896000000109", "codigo_aghu": "500100",
                              "fornecedor": "MEDFORN", "marca_fabricante": "Med", "nLote": "LB9",
                              "dVal": "01/01/2031", "quantidade": "1", "vUnCom": "100",
                              "tipo_entrada": "consignado", "codigo_consignado": "CONS-9"}, "almox")
    r5 = fluxo.bipar(operacao="registrar_uso", codigo="7896000000109", usuario="sala1", id_atendimento=id_ae)
    conferir(r5["ok"] and "SEM SALDO" in r5.get("empenho", "") or "sem empenho" in r5.get("empenho", "").lower(),
             "sem empenho ativo: uso é registrado e avisa (fica pendente de vínculo)", r5.get("empenho"))

    print("== Etiqueta GS1/UDI: cadastro pelo cEAN da NF, leitura da etiqueta completa")
    from src.providers.implementations.opme import gs1
    conferir(gs1.gtin("763000726591") == gs1.gtin("00763000726591") == "00763000726591",
             "GTIN com e sem zeros à esquerda é o mesmo código")
    cadastrar("STENT BILIAR WALLFLEX", "08714729789802", "0039671573", "24/06/2028", qtd="2")
    cadastrar("STENT BILIAR WALLFLEX", "08714729789802", "0011111111", "01/01/2029", qtd="1")
    cadastrar("BALAO NC EUPHORA", "763000726591", "234004643", "09/06/2028", qtd="2")
    cadastrar("BALAO NC EUPHORA", "763000726591", "999000111", "01/01/2029", qtd="1")
    ok, id_gs = _abrir_at({"prontuario": "4441", "sala": "03", "especialidade": "GASTRO",
                                    "data_procedimento": hoje_iso()}, "sala1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="0108714729789802172806241039671573",
                    usuario="sala1", id_atendimento=id_gs)
    u = fluxo.buscar_unidade(r["item"]["id_unidade"]) if r.get("ok") else {}
    conferir(r["ok"] and u.get("nLote") == "0039671573",
             "etiqueta (01)(17)(10) acha o cadastro pelo GTIN e escolhe o lote certo sozinho", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="010076300072659117280609102340046432001",
                    usuario="sala1", id_atendimento=id_gs)
    u = fluxo.buscar_unidade(r["item"]["id_unidade"]) if r.get("ok") else {}
    conferir(r["ok"] and u.get("nLote") == "234004643",
             "cEAN de 12 dígitos na NF + etiqueta com (20) no fim, sem separador: lote certo", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="(01)00763000726591(17)280609(10)234004643(20)01",
                    usuario="sala1", id_atendimento=id_gs)
    conferir(r["ok"], "etiqueta digitada com parênteses também funciona", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="0108714729789802172901011077777777",
                    usuario="sala1", id_atendimento=id_gs)
    conferir(r.get("escolha") or (r.get("ok") and any("não confere" in a for a in r.get("alertas", []))),
             "lote da etiqueta que não está cadastrado: não escolhe calado", str(r)[:200])
    cadastrar("GUIA NUCLEO FIXO J 260CM", "6947358535812", "C08240A1", "07/03/2027", qtd="5")
    cadastrar("GUIA NUCLEO FIXO J 260CM", "6947358535812", "C09999B2", "01/01/2028", qtd="1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="17270307300510C08240A1", usuario="sala1", id_atendimento=id_gs)
    u = fluxo.buscar_unidade(r["item"]["id_unidade"]) if r.get("ok") else {}
    conferir(r["ok"] and u.get("nLote") == "C08240A1",
             "etiqueta secundária (17)(30)(10), sem GTIN: acha pelo lote", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="6947358535812", usuario="sala1", id_atendimento=id_gs)
    conferir(r.get("escolha") and len(r["opcoes"]) == 2, "só o EAN-13 com 2 lotes em estoque: pede para escolher o lote")
    cadastrar("CATETER MEDCOMP", "00884908184671", "MRGV810", "17/05/2027", qtd="1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="0100884908184671112405171727051710MRGV810",
                    usuario="sala1", id_atendimento=id_gs)
    conferir(r["ok"], "DataMatrix (01)(11)(17)(10) lido pelo leitor 2D", r.get("mensagem"))

    print("== NF: cEAN vira o código de barras e não pode ser trocado")
    db.executar("INSERT INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                ("NFTESTE1", "123", "Boston Scientific do Brasil Ltda", db.agora()))
    for idi, cean in (("ITC1", "08714729789802"), ("ITC2", "SEM GTIN")):
        db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total,
                       qtd_pendente, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (idi, "NFTESTE1", "STENT NF " + idi, cean, "0039671573", "2028-06-24", 2600, 1, 1, db.agora()))
    ok, msg = estoque.dar_entrada_item_nf({"id_item": "ITC1", "quantidade": "1", "codigo_aghu": "400097",
                                           "marca_fabricante": "Boston", "codigo_barras": ""}, "almox")
    conferir(ok and db.escalar("SELECT codigo_barras FROM unidades WHERE id_item_nf='ITC1'") == "08714729789802",
             "com cEAN na NF, o código de barras é o cEAN mesmo se o campo vier apagado", msg)
    ok, msg = estoque.dar_entrada_item_nf({"id_item": "ITC2", "quantidade": "1", "codigo_aghu": "400097",
                                           "marca_fabricante": "Boston", "codigo_barras": ""}, "almox")
    conferir(not ok, "NF 'SEM GTIN': exige bipar ou marcar sem código de barras", msg)

    print("== NF sem lote/validade: digitados na entrada")
    db.executar("INSERT INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                ("NFSEMLOTE", "555", "Bioporto", db.agora()))
    db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total,
                   qtd_pendente, criado_em) VALUES ('ITS1','NFSEMLOTE','KIT DELINEADOR','SEM GTIN','S','',8354,3,3,?)""",
                (db.agora(),))
    base_s = {"id_item": "ITS1", "codigo_aghu": "400097", "marca_fabricante": "Bhiosupply", "sem_codigo_barras": "1"}
    conferir(not estoque.lote_informado("S") and estoque.lote_informado("L2345"), "lote 'S' da NF não é lote de verdade")
    ok, msg = estoque.dar_entrada_item_nf(base_s | {"quantidade": "1"}, "almox")
    conferir(not ok and "lote" in msg, "NF sem lote: pede o lote da embalagem", msg)
    ok, msg = estoque.dar_entrada_item_nf(base_s | {"quantidade": "1", "nLote_manual": "BH2291"}, "almox")
    conferir(not ok and "validade" in msg, "NF sem validade: pede a validade", msg)
    ok, msg = estoque.dar_entrada_item_nf(base_s | {"quantidade": "2", "nLote_manual": "BH2291",
                                                     "dVal_manual": "2028-05-31"}, "almox")
    un = db.consultar_um("SELECT nLote, dVal FROM unidades WHERE id_item_nf='ITS1'")
    conferir(ok and un["nLote"] == "BH2291" and un["dVal"] == "2028-05-31",
             "lote e validade digitados ficam gravados na unidade", msg)
    # v18: validade obrigatória — "material sem validade" não é mais aceito.
    ok, msg = estoque.dar_entrada_item_nf(base_s | {"quantidade": "1", "nLote_manual": "BH3000",
                                                     "sem_validade": "1"}, "almox")
    conferir(not ok and "validade" in msg, "v18: sem validade é recusado", msg)
    ok, msg = estoque.dar_entrada_item_nf(base_s | {"quantidade": "1", "nLote_manual": "BH3000",
                                                     "dVal_manual": "2029-01-31"}, "almox")
    conferir(ok and db.escalar("SELECT COUNT(DISTINCT nLote) FROM unidades WHERE id_item_nf='ITS1'") == 2,
             "entrada em partes: outro lote", msg)

    print("== NF: excluir nota importada por engano")
    ok, msg = estoque.excluir_nota("NFTESTE1", "almox", "")
    conferir(not ok and "motivo" in msg, "excluir nota exige motivo")
    unid_nf = db.escalar("SELECT id_unidade FROM unidades WHERE chave_nf='NFTESTE1'")
    ok, msg = estoque.excluir_nota("NFTESTE1", "almox", "XML errado")
    conferir(ok and not estoque.nota("NFTESTE1") and fluxo.buscar_unidade(unid_nf)["status"] == "baixado"
             and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='nf_excluida'") == 1,
             "nota excluída: some da lista, unidade recebida sai do estoque, fica no histórico", msg)
    db.executar("INSERT INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                ("NFTESTE1", "123", "Boston Scientific do Brasil Ltda", db.agora()))
    for idi, cean in (("ITC1", "08714729789802"), ("ITC2", "SEM GTIN")):
        db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total,
                       qtd_pendente, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (idi, "NFTESTE1", "STENT NF " + idi, cean, "0039671573", "2028-06-24", 2600, 1, 1, db.agora()))
    db.executar("INSERT INTO notas_fiscais (chave_nf, numero_nf, fornecedor, data_importacao) VALUES (?,?,?,?)",
                ("NFUSADA", "999", "X", db.agora()))
    db.executar("""INSERT INTO nf_itens (id_item, chave_nf, xProd, cEAN, nLote, dVal, vUnCom, qtd_total,
                   qtd_pendente, criado_em) VALUES ('ITU1','NFUSADA','ITEM USADO','7890000009999','LU','2029-01-01',10,1,1,?)""",
                (db.agora(),))
    ok, _ = estoque.dar_entrada_item_nf({"id_item": "ITU1", "quantidade": "1", "codigo_aghu": "400097",
                                         "marca_fabricante": "X"}, "almox")
    ok_at, id_nfu = _abrir_at({"prontuario": "3331", "sala": "02", "especialidade": "X",
                                        "data_procedimento": hoje_iso()}, "sala1")
    fluxo.bipar(operacao="registrar_uso", codigo="7890000009999", usuario="sala1", id_atendimento=id_nfu)
    ok, msg = estoque.excluir_nota("NFUSADA", "almox", "teste")
    conferir(not ok and estoque.nota("NFUSADA"), "nota com item já usado não pode ser excluída", msg)

    print("== Empenho: dados da licitação e importação por planilha")
    from pathlib import Path as _P
    modelo = (RAIZ / "frontend" / "public" / "modelo_empenhos.xlsx").read_bytes()
    ok, msg, res = empenhos.importar_planilha(modelo, "modelo_empenhos.xlsx", "almox")
    conferir(ok and res["criados"] == 2 and not res["erros"], "planilha modelo: 2 empenhos cadastrados", msg + str(res.get("erros")))
    imp = [e for e in empenhos.listar(termo="ARP 130/2026")]
    conferir(len(imp) == 1 and imp[0]["numero_pregao"] == "51/2026" and imp[0]["vigencia_inicio"] == "2026-03-01"
             and imp[0]["vigencia_fim"] == "2027-02-28" and imp[0]["numero_processo"] == "23538.002222/2026-10"
             and imp[0]["quantidade_total"] == 50 and abs(imp[0]["valor_unitario"] - 220.5) < 0.001
             and imp[0]["codigos_aghu"] == ["400150", "400151"],
             "importação grava processo, pregão, registro, vigência, quantidade, valor e AGHUs", str(imp[:1]))
    ok, msg, res = empenhos.importar_planilha(modelo, "modelo_empenhos.xlsx", "almox")
    conferir(res["criados"] == 0 and res["repetidos"] == 2, "importar de novo não duplica", msg)
    csv_ruim = ("Fornecedor;Código consignado;Código AGHU;Quantidade licitada;Valor unitário;Número do pregão\n"
                "X;;400097;5;10,00;1/2026\nY;NOVO-77;;5;10,00;2/2026\n").encode("utf-8")
    ok, msg, res = empenhos.importar_planilha(csv_ruim, "e.csv", "almox")
    conferir(res["criados"] == 0 and len(res["erros"]) == 2 and "Código consignado" in res["erros"][0]["mensagem"]
             and "NOVO-77" in res["erros"][1]["mensagem"],
             "linha sem código consignado (ou sem AGHU associado) é listada como problema", str(res["erros"]))
    ok, id_so_reg = empenhos.cadastrar({"fornecedor": "VIGMED", "codigos_consignado": "C499001", "codigos_aghu": "499001", "quantidade_total": "5",
                                        "valor_unitario": "10,00", "numero_registro": "ARP 9/2025",
                                        "vigencia_inicio": "2025-01-01", "vigencia_fim": "2025-12-31"}, "almox")
    conferir(ok and empenhos.buscar(id_so_reg)["vigencia"] == "vencida"
             and empenhos.buscar(id_so_reg)["identificacao"] == "Registro ARP 9/2025",
             "cadastro manual só com o registro de licitação; vigência vencida é identificada", str(id_so_reg))
    conferir(empenhos.empenho_para_aghu("499001") is None, "empenho fora da vigência não recebe débito")
    ok, m = empenhos.cadastrar({"fornecedor": "X", "codigos_consignado": "C499002", "codigos_aghu": "499002", "quantidade_total": "5",
                                "valor_unitario": "10,00"}, "almox")
    conferir(not ok and "ao menos um número" in m, "sem nenhum número (empenho/processo/pregão/registro) é recusado")

    print("== Devolução de não utilizados: a sala bipa, a farmácia confirma com a senha")
    from src.providers.implementations.opme.services import devolucoes
    for nome, papel in (("farm1", "farmacia"),):
        db.executar("""INSERT INTO usuarios (username, senha_hash, nome, email, setor, papel, status, criado_em)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (nome, gerar_hash("Senha2026"), "Farmacêutica Um", "", "Farmácia", papel, "ativo", db.agora()))

    def confirmar_dev(id_at, nao=(), usuario_farmacia="farm1", senha="Senha2026"):
        dev = devolucoes.pendente_do_atendimento(id_at)
        nao_ids = [i["id_item"] for i in devolucoes.itens(dev["id_devolucao"], so_pendentes=True)
                   if (i["id_unidade"] in nao or i["id_caixa"] in nao)] if dev else []
        return devolucoes.confirmar(id_devolucao=dev["id_devolucao"] if dev else "", operador="sala1",
                                    usuario_farmacia=usuario_farmacia, senha=senha, nao_recebidos=nao_ids)

    DV = dict(operacao="devolver_nao_utilizado", usuario="sala1", devolvido_por="Enf. Ana Souza")
    conferir("devolver_nao_utilizado" in OPERACOES and not OPERACOES["devolver_nao_utilizado"].confirmacao_papel,
             "devolução: a sala bipa sem senha (a farmácia confirma depois)")
    ok, id_dv = _abrir_at({"prontuario": "9991", "sala": "06", "especialidade": "ORTOPEDIA",
                                    "data_procedimento": hoje_iso(), "opme_solicitado": "parafusos"}, "sala1")
    cadastrar("PARAFUSO DV", "7897777777777", "LDV", "01/01/2031", qtd="4")
    ru = fluxo.bipar(operacao="registrar_uso", codigo="7897777777777", usuario="sala1", id_atendimento=id_dv)
    rsem = fluxo.bipar(operacao="devolver_nao_utilizado", codigo="7897777777777", usuario="sala1", id_atendimento=id_dv)
    conferir(not rsem["ok"] and "quem está devolvendo" in rsem["mensagem"], "sem o nome de quem devolve, não registra", rsem.get("mensagem"))
    r1 = fluxo.bipar(**DV, codigo="7897777777777", id_atendimento=id_dv)
    conferir(any("NÃO foi dispensado" in x for x in r1.get("alertas", [])),
             "aviso na devolução: item que não foi dispensado pela farmácia", str(r1.get("alertas")))
    conferir(r1["ok"] and r1.get("pendente") and r1["devolucao"]["itens"] == 1,
             "sala bipa: fica pendente, aguardando a farmácia", r1.get("mensagem"))
    u1 = r1["item"]["id_unidade"]
    conferir(u1 != ru["item"]["id_unidade"], "o item usado não entra na devolução")
    conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='devolver_nao_utilizado' AND id_atendimento=?", (id_dv,)) == 0
             and atendimentos.resumo(id_dv)["devolucao_aguardando"] == 1,
             "antes da senha nada conta como devolvido")
    r2 = fluxo.bipar(**DV, codigo=u1, id_atendimento=id_dv)
    conferir(not r2["ok"] and "aguardando" in r2["mensagem"], "a mesma unidade não entra duas vezes", r2.get("mensagem"))
    ok_at, id_outro = _abrir_at({"prontuario": "9992", "sala": "06", "especialidade": "ORTOPEDIA",
                                          "data_procedimento": hoje_iso()}, "sala1")
    r = fluxo.bipar(operacao="registrar_uso", codigo=u1, usuario="sala1", id_atendimento=id_outro)
    conferir(not r["ok"] and "DEVOLVIDO" in r["mensagem"], "item aguardando a farmácia não pode ser usado", r.get("mensagem"))
    r3 = fluxo.bipar(**DV, codigo="7897777777777", id_atendimento=id_dv)
    r_err = fluxo.bipar(**DV, codigo="7897777777777", id_atendimento=id_dv)
    conferir(r3["ok"] and r_err["ok"] and r3["item"]["id_unidade"] != u1, "bipar o mesmo código entra com a próxima unidade")
    item_err = [i for i in devolucoes.pendentes_do_atendimento(id_dv) if i["id_unidade"] == r_err["item"]["id_unidade"]][0]
    ok, msg, _ = devolucoes.remover_item(item_err["id_item"], "sala1", "bipado por engano")
    conferir(ok and len(devolucoes.pendentes_do_atendimento(id_dv)) == 2, "a sala tira da devolução o que bipou por engano")
    r4 = fluxo.bipar(**DV, codigo=ru["item"]["id_unidade"], id_atendimento=id_dv)
    conferir(not r4["ok"] and "UTILIZADO" in r4["mensagem"], "item usado não pode ser devolvido (orienta excluir o bip)", r4.get("mensagem"))
    ok, msg = confirmar_dev(id_dv, senha="errada")
    conferir(not ok and devolucoes.pendente_do_atendimento(id_dv), "senha errada: nada é confirmado", msg)
    ok, msg = confirmar_dev(id_dv, usuario_farmacia="sala2")
    conferir(not ok, "quem não é da farmácia não confirma", msg)
    ok, msg = confirmar_dev(id_dv)
    conferir(ok and "2 item(ns) recebido(s)" in msg and not devolucoes.pendente_do_atendimento(id_dv),
             "farmácia confirma com a senha: devolução recebida", msg)
    ev = db.consultar_um("SELECT * FROM eventos WHERE tipo='devolver_nao_utilizado' AND id_unidade=?", (u1,))
    conf = db.consultar_um("SELECT * FROM eventos WHERE tipo='confirmar_devolver_nao_utilizado' AND id_unidade=?", (u1,))
    conferir(ev and ev["id_atendimento"] == id_dv and ev["usuario"] == "sala1" and conf and conf["usuario"] == "farm1",
             "evento registra atendimento, quem bipou e quem recebeu")
    conferir(ev["devolvido_por"] == "Enf. Ana Souza" and ev["recebido_por"] == "Farmacêutica Um"
             and conf["devolvido_por"] == "Enf. Ana Souza" and conf["recebido_por"] == "Farmacêutica Um",
             "auditoria: o evento grava quem devolveu e quem recebeu")
    u1d = fluxo.buscar_unidade(u1)
    conferir(u1d["status"] == EM_ESTOQUE_RECEBIMENTO and not u1d["id_atendimento"],
             "item devolvido segue no estoque, sem paciente")
    conferir(atendimentos.resumo(id_dv)["devolvidos"] == 2 and len(atendimentos.devolvidos(id_dv)) == 2
             and atendimentos.devolvidos(id_dv)[0]["recebido_por"] == "Farmacêutica Um"
             and atendimentos.devolvidos(id_dv)[0]["devolvido_por"] == "Enf. Ana Souza",
             "atendimento lista os devolvidos, quem devolveu e quem recebeu")
    r = fluxo.bipar(**DV, codigo=u1, id_atendimento=id_dv)
    conferir(not r["ok"] and "já foi devolvido" in r["mensagem"], "a mesma unidade não é devolvida duas vezes", r.get("mensagem"))
    atendimentos.encerrar(id_dv, "sala1")
    cadastrar("PARAFUSO DV2", "7897777777778", "LDW", "01/01/2031", qtd="2")
    r5 = fluxo.bipar(**DV, codigo="7897777777778", id_atendimento=id_dv)
    r6 = fluxo.bipar(**DV, codigo="7897777777778", id_atendimento=id_dv)
    conferir(r5["ok"] and r6["ok"], "devolução também é aceita depois de encerrado o atendimento", r5.get("mensagem"))
    conferir(any(d["id_atendimento"] == id_dv for d in devolucoes.listar_pendentes()),
             "aparece em Farmácia → Devoluções a confirmar")
    ok, msg = confirmar_dev(id_dv, nao=(r6["item"]["id_unidade"],))
    conferir(ok and fluxo.buscar_unidade(r6["item"]["id_unidade"])["status"] != DIVERGENCIA
             and fluxo.buscar_unidade(r5["item"]["id_unidade"])["status"] == EM_ESTOQUE_RECEBIMENTO,
             "farmácia desmarca o que não voltou: não vira divergência (a sala confere); o resto é recebido", msg)
    conferir(db.escalar("SELECT COUNT(*) FROM alertas WHERE modulo_destino='sala-procedimento' AND "
                        "titulo LIKE 'Conferir: material que a farmácia não recebeu%'") == 1,
             "item não recebido gera alerta para a sala conferir")
    conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='devolucao_nao_recebida' AND devolvido_por='Enf. Ana Souza' "
                        "AND recebido_por='Farmacêutica Um'") == 1, "o não recebido fica auditado com os dois nomes")

    print("== Caixa de consignado: uso por item, devolução pela caixa + quantidade")
    from src.providers.implementations.opme.services import caixas_consignado
    ok, msg, cx = caixas_consignado.criar({"nome": "ORTOPEDIA parafusos"}, "almox")
    conferir(ok and cx.startswith("CX-ORTO"), "almoxarifado cria a caixa (código pelo nome — v18.11.2)", cx)
    cadastrar("PARAFUSO CX", "7898888888888", "LCX", "01/01/2031", qtd="5", tipo_entrada="consignado")
    # v18.11.4: caixa na farmácia só recebe o estoque da farmácia (o unitário chega antes)
    db.executar("UPDATE unidades SET status = 'em_estoque_farmacia', farmacia = 'BLOCO CIRURGICO' WHERE nLote = 'LCX'")
    for _ in range(5):
        r = caixas.adicionar_item(cx, "7898888888888", "almox")
    conferir(caixas_consignado.esperado(cx) == 5, "5 itens bipados para dentro da caixa")
    ok, id_cx1 = _abrir_at({"prontuario": "7771", "sala": "07", "especialidade": "ORTOPEDIA",
                                     "data_procedimento": hoje_iso(), "opme_solicitado": "parafusos"}, "sala1")
    ru1 = fluxo.bipar(operacao="registrar_uso", codigo="7898888888888", usuario="sala1", caixa=cx, id_atendimento=id_cx1)
    ru2 = fluxo.bipar(operacao="registrar_uso", codigo="7898888888888", usuario="sala1", caixa=cx, id_atendimento=id_cx1)
    conferir(ru1["ok"] and ru2["ok"] and caixas_consignado.esperado(cx) == 3, "uso bipado por item sai da caixa")
    kw = dict(DV, codigo=cx, id_atendimento=id_cx1)
    r = fluxo.bipar(**kw)
    conferir(r.get("pede_quantidade") and r["caixa"]["id_caixa"] == cx, "bipar a caixa pede a quantidade")
    r = fluxo.bipar(**kw, quantidade="2")
    cxd = caixas_consignado.buscar(cx)
    conferir(not r["ok"] and r.get("divergencia") and cxd["bloqueada"], "contagem diferente: recusa e bloqueia a caixa", r.get("mensagem"))
    conferir(db.escalar("SELECT COUNT(*) FROM alertas WHERE titulo LIKE ?", (f"Caixa {cx} bloqueada%",)) == 1,
             "gera alerta da divergência")
    conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='devolver_nao_utilizado' AND id_atendimento=?", (id_cx1,)) == 0,
             "nada foi registrado como devolvido")
    ok, id_cx2 = _abrir_at({"prontuario": "7772", "sala": "08", "especialidade": "ORTOPEDIA",
                                     "data_procedimento": hoje_iso(), "opme_solicitado": "parafusos"}, "sala1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7898888888888", usuario="sala1", caixa=cx, id_atendimento=id_cx2)
    conferir(not r["ok"] and "BLOQUEADA" in r["mensagem"], "caixa bloqueada: outro atendimento não usa os itens", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="7898888888888", usuario="sala1", caixa=cx, id_atendimento=id_cx1)
    conferir(r["ok"], "no mesmo atendimento, a sala bipa o uso esquecido")
    r = fluxo.bipar(**kw, quantidade="2")
    conferir(r["ok"] and r.get("pendente") and r["caixa"]["total"] == 2,
             "devolve de novo com a contagem certa: caixa entra na devolução pendente", r.get("mensagem"))
    r = fluxo.bipar(**kw, quantidade="2")
    conferir(not r["ok"] and "aguardando" in r["mensagem"], "a mesma caixa não entra duas vezes na devolução", r.get("mensagem"))
    ok, msg = confirmar_dev(id_cx1)
    conferir(ok and "2 item(ns) recebido(s)" in msg, "farmácia confirma a caixa com a senha", msg)
    conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='devolver_nao_utilizado' AND id_atendimento=?", (id_cx1,)) == 2
             and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='confirmar_devolver_nao_utilizado' AND id_atendimento=?", (id_cx1,)) == 2,
             "cada item da caixa entra no histórico de devoluções, com quem recebeu")
    conferir(caixas_consignado.buscar(cx)["bloqueada"], "caixa continua bloqueada até a conferência")
    r = fluxo.bipar(**kw, quantidade="2")
    conferir(not r["ok"] and "já foi devolvida" in r["mensagem"], "a mesma caixa não é devolvida duas vezes no atendimento")
    itens_cx = caixas.conteudo(cx)
    ok, msg = caixas_consignado.conferir(cx, "almox", "contagem física: 1 item faltando", [itens_cx[0]["id_unidade"]])
    conferir(ok and not caixas_consignado.buscar(cx)["bloqueada"] and caixas_consignado.esperado(cx) == 1
             and fluxo.buscar_unidade(itens_cx[0]["id_unidade"])["status"] == DIVERGENCIA,
             "conferência libera a caixa; faltante vai para divergência", msg)
    r = fluxo.bipar(operacao="registrar_uso", codigo="7898888888888", usuario="sala1", caixa=cx, id_atendimento=id_cx2)
    conferir(r["ok"], "liberada: volta a ser usada em outro procedimento")
    ok, _ = fluxo.excluir_bip(r["item"]["id_unidade"], id_cx2, "sala1", "Bipado em duplicidade")
    conferir(ok and caixas_consignado.esperado(cx) == 1 and fluxo.buscar_unidade(r["item"]["id_unidade"])["id_caixa"] == cx,
             "bip de uso excluído: o item volta para dentro da caixa")

    print("== Histórico: devolução de caixa aparece como a caixa")
    linhas_cx = relatorios.movimentacoes(prontuario="7771", tipo="devolver_nao_utilizado")
    cx_linhas = [l for l in linhas_cx if l["tipo"] == "devolver_caixa"]
    conferir(len(cx_linhas) == 1 and cx_linhas[0]["caixa"] == cx and len(cx_linhas[0]["itens_caixa"]) == 2
             and not [l for l in linhas_cx if l["tipo"] == "devolver_nao_utilizado" and l["caixa"]],
             "devolução da caixa vira uma linha só, com os itens dentro", str(len(linhas_cx)))
    conferir(any(l["tipo"] == "devolucao_caixa_divergente" for l in linhas_cx), "devolução recusada aparece no histórico")
    conferir(cx_linhas[0]["recebido_por"] == "Farmacêutica Um", "linha da caixa mostra quem recebeu")
    conferir(cx_linhas[0]["devolvido_por"] == "Enf. Ana Souza"
             and all(i.get("devolvido_por", "Enf. Ana Souza") == "Enf. Ana Souza" for i in cx_linhas[0]["itens_caixa"]),
             "linha da caixa mostra quem devolveu")
    div = [l for l in linhas_cx if l["tipo"] == "devolucao_caixa_divergente"][0]
    conferir(div["devolvido_por"] == "Enf. Ana Souza",
             "tentativa recusada (contagem da sala) também registra quem devolveu")
    conferir(relatorios.movimentacoes(usuario="Ana Souza"), "filtro por pessoa acha quem devolveu")
    csv_aud = relatorios.movimentacoes_para_csv(linhas_cx)
    conferir("Devolvido por (sala)" in csv_aud and "Enf. Ana Souza" in csv_aud, "planilha tem as colunas de quem devolveu e quem recebeu")
    sit = caixas_consignado.situacao_no_momento(cx, cx_linhas[0]["id_evento"])
    # "naquele momento" é por horário (segundos); no teste tudo acontece no mesmo segundo.
    conferir(len(sit["devolvidos"]) == 2 and len(sit["usados_no_atendimento"]) == 3,
             "caixa no momento da devolução: devolvidos e usados no atendimento",
             f'{len(sit["naquele"])}/{len(sit["devolvidos"])}/{len(sit["usados_no_atendimento"])}')
    csv_cx = relatorios.movimentacoes_para_csv(relatorios.movimentacoes(prontuario="7771", tipo="devolver_nao_utilizado", agrupar_caixas=False))
    conferir(csv_cx.count(cx) >= 2, "planilha mantém um item por linha, com a coluna Caixa")

    print("== Caixa: revisão (AGHU, lote diferente, caixa x estoque solto)")
    ok, _, cx2 = caixas_consignado.criar({"nome": "Caixa revisão", "fornecedor": "CROMUS"}, "farm1")
    for lote, val in (("LA1", "01/01/2031"), ("LA2", "01/06/2031")):
        estoque.cadastrar_manual({"xProd": "PLACA CX2", "codigo_barras": "7899990000011", "codigo_aghu": "400999",
                                  "fornecedor": "CROMUS", "marca_fabricante": "Cromus", "nLote": lote,
                                  "dVal": val, "quantidade": "2", "vUnCom": "300"}, "almox")
    db.executar("UPDATE unidades SET status = 'em_estoque_farmacia', farmacia = 'BLOCO CIRURGICO' "
                "WHERE nLote IN ('LA1','LA2')")   # v18.11.4: caixa da farmácia ← estoque da farmácia
    conferir(not caixas_consignado.candidatos_para_caixa("400999", so_almoxarifado=True),
             "caixa do almoxarifado não vê o estoque da farmácia (v18.11.4)")
    grupos = caixas_consignado.candidatos_para_caixa("400999")
    conferir(len(grupos) == 2 and {g["nLote"] for g in grupos} == {"LA1", "LA2"} and grupos[0]["quantidade"] == 2,
             "digitar o AGHU acha o material solto, agrupado por lote (pede escolha)")
    conferir(len(caixas_consignado.candidatos_para_caixa("7899990000011")) == 2, "código de barras com 2 lotes também pede escolha")
    alvo = [g for g in grupos if g["nLote"] == "LA2"][0]["id_unidade"]
    r = caixas.adicionar_item(cx2, alvo, "farm1")
    conferir(r["ok"] and caixas_consignado.esperado(cx2) == 1, "item escolhido entra na caixa")
    ok, id_rv = _abrir_at({"prontuario": "6661", "sala": "09", "especialidade": "ORTOPEDIA",
                                    "data_procedimento": hoje_iso(), "opme_solicitado": "placa"}, "sala1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7899990000011", usuario="sala1", id_atendimento=id_rv)
    conferir(r.get("escolha") and not any(o["caixa"] for o in r["opcoes"]),
             "uso sem caixa ativa: só considera o estoque solto (a caixa não entra na escolha)")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7899990000011", usuario="sala1", id_atendimento=id_rv, caixa=cx2)
    conferir(r["ok"] and caixas_consignado.esperado(cx2) == 0, "com a caixa ativa, sai da caixa certa sem perguntar", r.get("mensagem"))

    print("== Uso de item de caixa: primeiro a caixa, depois o item")
    ok, _, cxa = caixas_consignado.criar({"nome": "Caixa joelho A", "fornecedor": "MEDSUL"}, "farm1")
    ok, _, cxb = caixas_consignado.criar({"nome": "Caixa joelho B", "fornecedor": "MEDSUL"}, "farm1")
    cadastrar("COMPONENTE JOELHO", "7890011223344", "LJ1", "01/01/2032", qtd="4", tipo_entrada="consignado")
    db.executar("UPDATE unidades SET status = 'em_estoque_farmacia', farmacia = 'BLOCO CIRURGICO' WHERE nLote = 'LJ1'")
    for destino in (cxa, cxa, cxb, cxb):
        caixas.adicionar_item(destino, "7890011223344", "farm1")
    conferir(caixas_consignado.esperado(cxa) == 2 and caixas_consignado.esperado(cxb) == 2,
             "mesmo material (mesmo lote) em duas caixas")
    ok, id_jo = _abrir_at({"prontuario": "5551", "sala": "10", "especialidade": "ORTOPEDIA",
                                    "data_procedimento": hoje_iso(), "opme_solicitado": "joelho"}, "sala1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7890011223344", usuario="sala1", id_atendimento=id_jo)
    conferir(not r["ok"] and "Bipe a CAIXA" in r["mensagem"] and cxa in r["mensagem"] and cxb in r["mensagem"],
             "mesmo material em DUAS caixas, sem caixa ativa: pede a caixa (v18.11.6)", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo=cxb, usuario="sala1", id_atendimento=id_jo)
    conferir(r["ok"] and r["caixa_ativa"]["id_caixa"] == cxb and r["caixa_ativa"]["total"] == 2,
             "bipar a caixa no uso só a seleciona (nada é gravado)", r.get("mensagem"))
    conferir(caixas_consignado.esperado(cxb) == 2, "selecionar a caixa não move material")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7890011223344", usuario="sala1", id_atendimento=id_jo, caixa=cxb)
    conferir(r["ok"] and caixas_consignado.esperado(cxb) == 1 and caixas_consignado.esperado(cxa) == 2,
             "o uso sai da caixa bipada (B), não da outra (A)", r.get("mensagem"))
    ev_uso = db.consultar_um("SELECT * FROM eventos WHERE tipo='registrar_uso' AND id_unidade=?", (r["item"]["id_unidade"],))
    conferir(f"[{cxb}]" in (ev_uso["observacao"] or ""), "o evento de uso registra de qual caixa o item saiu")
    cadastrar("OUTRO SOLTO", "7890011223355", "LJ2", "01/01/2032")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7890011223355", usuario="sala1", id_atendimento=id_jo, caixa=cxb)
    conferir(not r["ok"] and "NÃO está na caixa" in r["mensagem"] and "Sair da caixa" in r["mensagem"],
             "item solto com caixa ativa: recusa e orienta sair da caixa", r.get("mensagem"))
    ok, _, cxc = caixas_consignado.criar({"nome": "Caixa vazia", "fornecedor": "MEDSUL"}, "farm1")
    cadastrar("SO NA A", "7890011223366", "LJ3", "01/01/2032")
    db.executar("UPDATE unidades SET status = 'em_estoque_farmacia', farmacia = 'BLOCO CIRURGICO' WHERE nLote = 'LJ3'")
    caixas.adicionar_item(cxa, "7890011223366", "farm1")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7890011223366", usuario="sala1", id_atendimento=id_jo, caixa=cxb)
    conferir(not r["ok"] and cxa in r["mensagem"], "item de outra caixa: diz em qual caixa ele está", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo=cxc, usuario="sala1", id_atendimento=id_jo)
    conferir(not r["ok"] and "vazia" in r["mensagem"], "caixa vazia não é selecionada")
    r = fluxo.bipar(**DV, codigo=cxa, id_atendimento=id_jo, quantidade="3")
    conferir(r["ok"] and r.get("pendente"), "caixa A bipada na devolução", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo=cxa, usuario="sala1", id_atendimento=id_jo)
    conferir(not r["ok"] and "aguardando" in r["mensagem"], "caixa aguardando a farmácia não é aberta para uso", r.get("mensagem"))
    ok, msg = confirmar_dev(id_jo, nao=(cxa,))
    conferir(ok and not caixas_consignado.buscar(cxa)["bloqueada"]
             and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='devolver_caixa' AND id_atendimento=?", (id_jo,)) == 0,
             "caixa desmarcada pela farmácia: não é recebida e continua com o paciente (a sala confere)", msg)
    conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='registrar_uso'") > 0, "ok")

    print("== Dispensação farmácia → sala (senha da sala, sem bipar)")
    from src.providers.implementations.opme.services import dispensacoes
    from src.providers.implementations.opme.domain import TRANSITO_SALA as _TS, EM_SALA as _ES
    ok, id_p1 = _abrir_at({"prontuario": "8881", "sala": "05", "especialidade": "CARDIO",
                                    "data_procedimento": hoje_iso()}, "sala1")
    ok, id_p2 = _abrir_at({"prontuario": "8882", "sala": "05", "especialidade": "CARDIO",
                                    "data_procedimento": hoje_iso()}, "sala1")
    cadastrar("STENT DISP", "7893330000011", "LD1", "01/01/2031", qtd="4", farmacia="BLOCO CIRURGICO")
    cadastrar("BALAO NAO DISP", "7893330000028", "LD2", "01/01/2031", qtd="1")
    r = fluxo.bipar(operacao="dispensar_sala", codigo="7893330000011", usuario="farm1", id_atendimento=id_p1)
    u = fluxo.buscar_unidade(r["item"]["id_unidade"]) if r.get("ok") else {}
    conferir(r["ok"] and r.get("pendente") and u.get("status") == _TS and u.get("id_atendimento") == id_p1
             and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='dispensar_sala' AND id_unidade=?", (u["id_unidade"],)) == 1,
             "farmácia bipa: saída registrada, item reservado ao paciente aguardando a sala", r.get("mensagem"))
    u_disp = u["id_unidade"]
    disp = dispensacoes.pendente_do_atendimento(id_p1)
    ok, msg = dispensacoes.confirmar(id_dispensacao=disp["id_dispensacao"], usuario_sala="sala2", senha="errada")
    conferir(not ok and fluxo.buscar_unidade(u_disp)["status"] == _TS, "senha errada não confirma", msg)
    ok, msg = dispensacoes.confirmar(id_dispensacao=disp["id_dispensacao"], usuario_sala="farm1", senha="Senha2026")
    conferir(not ok, "quem não é da sala não confirma o recebimento", msg)
    ok, msg = dispensacoes.confirmar(id_dispensacao=disp["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
    ev = db.consultar_um("SELECT * FROM eventos WHERE tipo='confirmar_recebimento_sala' AND id_unidade=?", (u_disp,))
    conferir(ok and fluxo.buscar_unidade(u_disp)["status"] == _ES and ev and ev["usuario"] == "sala2"
             and ev["recebido_por"], "sala confirma só com a senha: item fica 'na sala'", msg)
    r = fluxo.bipar(operacao="registrar_uso", codigo="7893330000011", usuario="sala1", id_atendimento=id_p1)
    conferir(r["ok"] and r["item"]["id_unidade"] == u_disp
             and not db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='saida_sem_dispensacao' AND id_unidade=?", (u_disp,)),
             "no uso, a sala usa o item dispensado para o paciente", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="7893330000028", usuario="sala1", id_atendimento=id_p1)
    conferir(r["ok"] and any("não foi dispensado" in a for a in r.get("alertas", []))
             and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='saida_sem_dispensacao' AND id_unidade=?",
                            (r["item"]["id_unidade"],)) == 1,
             "uso sem dispensação: aceita, avisa e registra a saída da farmácia", r.get("mensagem"))
    from src.providers.implementations.opme.services import usos_sem_dispensacao as usd
    antes = usd.contar_pendentes()
    pend = [p for p in usd.pendentes() if p["prontuario"] == "8881" and p["xProd"] == "BALAO NAO DISP"]
    conferir(len(pend) == 1 and pend[0]["xProd"] == "BALAO NAO DISP", "uso sem dispensação fica pendente de ciência da farmácia", str([(p["xProd"], p["situacao"]) for p in pend]))
    ok, msg = usd.dar_ciencia([pend[0]["id"]], {"username": "farm1", "nome": "Farmacêutica Um"}, "urgência")
    conferir(ok and usd.contar_pendentes() == antes - 1 and usd.com_ciencia()[0]["ciente_nome"] == "Farmacêutica Um"
             and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='ciencia_uso_sem_dispensacao'") == 1,
             "farmácia dá ciência: registrado com nome e no histórico", msg)
    usd.dar_ciencia([p["id"] for p in usd.pendentes()], {"username": "farm1", "nome": "Farmacêutica Um"})
    from src.providers.implementations.opme.services import indicadores as _ind
    vals = _ind.calcular_valores(hoje_iso(), hoje_iso())
    conferir(vals["taxa_uso_sem_dispensacao"] is not None and vals["ciencia_uso_sem_dispensacao"] == 100.0,
             "indicadores: taxa de uso sem dispensação e ciência em até 24 h", str(vals.get("ciencia_uso_sem_dispensacao")))
    ok, _ = fluxo.excluir_bip(u_disp, id_p1, "sala1", "Bipado em duplicidade")
    conferir(ok and fluxo.buscar_unidade(u_disp)["status"] == _ES, "bip excluído de item dispensado volta para a sala, não para o estoque")
    r = fluxo.bipar(operacao="devolver_nao_utilizado", codigo="7893330000011", usuario="sala1",
                    devolvido_por="Enf. Ana Souza", id_atendimento=id_p1)
    conferir(r["ok"] and r["item"]["id_unidade"] == u_disp, "devolução pega o item dispensado para o paciente", r.get("mensagem"))
    conferir(any("dispensado pela farmácia para este paciente" in x for x in r.get("alertas", [])),
             "aviso na devolução: item dispensado para o paciente", str(r.get("alertas")))
    ok, msg = confirmar_dev(id_p1)
    conferir(ok and fluxo.buscar_unidade(u_disp)["status"] == "em_estoque_farmacia"
             and not fluxo.buscar_unidade(u_disp)["id_atendimento"],
             "sobra dispensada volta ao estoque DA FARMÁCIA pela devolução", msg)
    ok, id_p3 = _abrir_at({"prontuario": "8883", "sala": "05", "especialidade": "CARDIO",
                                    "data_procedimento": hoje_iso()}, "sala1")
    r = fluxo.bipar(operacao="dispensar_sala", codigo="7893330000011", usuario="farm1", id_atendimento=id_p3)
    ok, msg = atendimentos.encerrar(id_p3, "sala1")
    conferir(not ok and "dispensado" in msg, "não encerra com material dispensado sem uso nem devolução", msg)
    fluxo.bipar(operacao="devolver_nao_utilizado", codigo=r["item"]["id_unidade"], usuario="sala1",
                devolvido_por="Enf. Ana Souza", id_atendimento=id_p3)
    ok, msg = atendimentos.encerrar(id_p3, "sala1")
    conferir(ok, "bipada a devolução, o atendimento encerra (a farmácia confirma depois)", msg)
    r = fluxo.bipar(operacao="dispensar_sala", codigo="7893330000011", usuario="farm1", id_atendimento=id_p2)
    u_p2 = r["item"]["id_unidade"]
    r = fluxo.bipar(operacao="registrar_uso", codigo="7893330000028", usuario="sala1", id_atendimento=id_p1)
    conferir(not r.get("dispensacao_pendente"),
             "dispensação pendente de OUTRO prontuário da mesma sala não trava este", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="7893330000028", usuario="sala1", id_atendimento=id_p2)
    conferir(not r["ok"] and r.get("dispensacao_pendente"),
             "prontuário com dispensação aguardando a confirmação não bipa uso", r.get("mensagem"))
    r = fluxo.bipar(operacao="devolver_nao_utilizado", codigo="7893330000028", usuario="sala1",
                    devolvido_por="Enf. Ana Souza", id_atendimento=id_p1)
    conferir("aguardando a confirmação de recebimento" not in (r.get("mensagem") or ""),
             "a trava vale só para o registro de uso")
    ok, _ = dispensacoes.confirmar(id_dispensacao=dispensacoes.pendente_do_atendimento(id_p2)["id_dispensacao"],
                                   usuario_sala="sala2", senha="Senha2026")
    r = fluxo.bipar(operacao="registrar_uso", codigo=u_p2, usuario="sala1", id_atendimento=id_p1)
    conferir(r["ok"] and any("outro paciente" in a for a in r.get("alertas", [])),
             "item dispensado para outro paciente: usa, mas avisa", r.get("mensagem"))
    ok, _, cxd = caixas_consignado.criar({"nome": "Caixa disp", "fornecedor": "DISPMED"}, "farm1")
    cadastrar("PARAFUSO DISP", "7893330000035", "LD3", "01/01/2031", qtd="2", farmacia="BLOCO CIRURGICO")
    caixas.adicionar_item(cxd, "7893330000035", "farm1"); caixas.adicionar_item(cxd, "7893330000035", "farm1")
    r = fluxo.bipar(operacao="dispensar_sala", codigo=cxd, usuario="farm1", id_atendimento=id_p2)
    conferir(r["ok"] and r["caixa"]["total"] == 2 and caixas_consignado.esperado(cxd) == 2
             and db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status=?", (cxd, _TS)) == 2,
             "caixa de consignado é dispensada inteira", r.get("mensagem"))
    r = fluxo.bipar(operacao="dispensar_sala", codigo=cxd, usuario="farm1", id_atendimento=id_p2)
    conferir(not r["ok"] and "já foi dispensada" in r["mensagem"], "a mesma caixa não sai duas vezes")
    item_cx = [i for i in dispensacoes.pendentes_do_atendimento(id_p2) if i["id_caixa"] == cxd][0]
    ok, msg, _ = dispensacoes.remover_item(item_cx["id_item"], "farm1")
    conferir(ok and db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status=?", (cxd, "em_estoque_farmacia")) == 2,
             "tirar a caixa da dispensação devolve os itens ao estoque", msg)
    r = fluxo.bipar(operacao="dispensar_sala", codigo=cxd, usuario="farm1", id_atendimento=id_p2)
    dispensacoes.confirmar(id_dispensacao=dispensacoes.pendente_do_atendimento(id_p2)["id_dispensacao"],
                           usuario_sala="sala2", senha="Senha2026")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7893330000035", usuario="sala1", caixa=cxd, id_atendimento=id_p2)
    conferir(r["ok"] and caixas_consignado.esperado(cxd) == 1, "uso de item da caixa dispensada (caixa ativa)", r.get("mensagem"))
    r = fluxo.bipar(operacao="devolver_nao_utilizado", codigo=cxd, usuario="sala1", devolvido_por="Enf. Ana Souza",
                    id_atendimento=id_p2, quantidade="1")
    ok, msg = confirmar_dev(id_p2)
    conferir(r["ok"] and ok and db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status=?",
                                           (cxd, "em_estoque_farmacia")) == 1,
             "devolução da caixa dispensada: o que sobrou volta ao estoque", (r.get("mensagem") or "") + " / " + msg)

    conc = dispensacoes.conciliacao(hoje_iso(), hoje_iso(), "BLOCO CIRURGICO", "05")
    desf_u = [i["desfecho"] for i in conc["itens"] if i["id_unidade"] == u_disp]
    p1 = [l for l in conc["salas"] if l["prontuario"] == "8881"]
    conferir(len(conc["salas"]) >= 2 and p1 and p1[0]["sem_dispensacao"] >= 1 and desf_u and desf_u[0] == "devolvido",
             "conciliação separa por sala e prontuário (dispensado/usado/devolvido e sem dispensação)", str(conc["salas"][:2]))
    so_p2 = dispensacoes.conciliacao(hoje_iso(), hoje_iso(), prontuario="8882")
    conferir(so_p2["salas"] and all(l["prontuario"] == "8882" for l in so_p2["salas"]), "conciliação filtra por prontuário")

    print("== Histórico de movimentações")
    hist = relatorios.movimentacoes(prontuario="9991", tipo="devolver_nao_utilizado")
    conferir(len(hist) == 3 and all(h["recebido_por"] == "Farmacêutica Um" and h["sala"] == "06" for h in hist),
             "filtra devoluções por prontuário, com sala e quem recebeu", str(len(hist)))
    conferir(not any(h["tipo"].startswith("confirmar_") for h in relatorios.movimentacoes(prontuario="9991")),
             "confirmação da farmácia não aparece como linha separada")
    conferir(relatorios.movimentacoes(sala="06", tipo="registrar_uso")[0]["prontuario"] == "9991",
             "filtra por sala e tipo")
    ambos = relatorios.movimentacoes(prontuario="9991", tipo="uso_devolucao")
    conferir({h["tipo"] for h in ambos} == {"registrar_uso", "devolver_nao_utilizado"} and len(ambos) == 4,
             "filtro 'Uso e devolução' traz os dois juntos", str(len(ambos)))
    dv = relatorios.devolucoes_por_prontuario("9991")
    conferir(len(dv) == 3 and dv[0]["recebido_por"] == "Farmacêutica Um", "consulta por prontuário lista as devoluções")
    csv_txt = relatorios.movimentacoes_para_csv(hist)
    conferir("Recebido por (farmácia)" in csv_txt and "Farmacêutica Um" in csv_txt, "exporta CSV com quem recebeu")

    print("== Dispensação: mesmo AGHU + lote + validade é o mesmo produto")
    ok_c, id_pc = _abrir_at({"prontuario": "8884", "sala": "06", "especialidade": "CARDIO",
                                      "data_procedimento": hoje_iso()}, "sala1")
    cadastrar("FIO GUIA TEFLONADO", "7893339990001", "L08250A5", "07/12/2028", codigo_aghu="89846", farmacia="BLOCO CIRURGICO")
    cadastrar("FIO TEFLONADO", "7893339990001", "L08250A5", "07/12/2028", codigo_aghu="89846", farmacia="BLOCO CIRURGICO")
    cadastrar("FIO GUIA HIDROFILICO APT", "7893339990001", "L08250A5", "07/12/2028", codigo_aghu="89846", farmacia="BLOCO CIRURGICO")
    r = fluxo.bipar(operacao="dispensar_sala", codigo="7893339990001", usuario="farm1", id_atendimento=id_pc)
    lst = (r.get("devolucao") or {}).get("lista") or []
    conferir(r.get("ok") and not r.get("escolha") and lst and lst[0]["aghu"] == "89846"
             and lst[0]["validade"] == "07/12/2028",
             "nomes diferentes, mesmo AGHU/lote/validade: dispensa direto, sem perguntar", r.get("mensagem"))
    cadastrar("FIO TEFLONADO", "7893339990001", "L99999", "07/12/2028", codigo_aghu="89846", farmacia="BLOCO CIRURGICO")
    r = fluxo.bipar(operacao="dispensar_sala", codigo="7893339990001", usuario="farm1", id_atendimento=id_pc)
    conferir(r.get("escolha") and len(r.get("opcoes", [])) == 2,
             "lote diferente: continua pedindo a escolha (uma opção por lote)", str(len(r.get("opcoes", []))))
    pdf_bytes = dispensacoes.pdf(dispensacoes.pendente_do_atendimento(id_pc)["id_dispensacao"])
    conferir(pdf_bytes and pdf_bytes.startswith(b"%PDF"), "PDF da dispensação para a sala")

    print("== Fechamento: sala finaliza os utilizados, farmácia dá ciência e conclui")
    from src.providers.implementations.opme.services import fechamento
    farm = {"username": "farm1", "nome": "Farmacêutica Um", "papel": "farmacia"}
    enf = {"username": "sala1", "nome": "Enf. Ana Souza", "papel": "sala-procedimento"}
    cadastrar("ITEM FA", "7895550000011", "LFA", "01/01/2031", qtd="3", codigo_aghu="77001", farmacia="BLOCO CIRURGICO")
    cadastrar("ITEM FB", "7895550000028", "LFB", "01/01/2031", qtd="3", codigo_aghu="77002", farmacia="BLOCO CIRURGICO")
    def novo(pront, sala):
        return _abrir_at({"prontuario": pront, "sala": sala, "especialidade": "CARDIO",
                                   "data_procedimento": hoje_iso()}, "sala1")[1]
    def dispensa_e_confirma(at, *codigos):
        for c in codigos:
            fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1", id_atendimento=at)
        d = dispensacoes.pendente_do_atendimento(at)
        return dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
    a1, a2 = novo("6601", "10"), novo("6602", "10")
    fluxo.bipar(operacao="dispensar_sala", codigo="7895550000011", usuario="farm1", id_atendimento=a1)
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895550000028", usuario="sala1", id_atendimento=a2)
    conferir(r["ok"], "mesma sala: o outro prontuário bipa normalmente", r.get("mensagem"))
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895550000028", usuario="sala1", id_atendimento=a1)
    conferir(not r["ok"] and r.get("dispensacao_pendente"), "o prontuário com dispensação pendente fica travado", r.get("mensagem"))
    ok, msg, enc = fechamento.finalizar_uso(a1, enf)
    conferir(not ok and "Confirme o recebimento" in msg, "não finaliza com dispensação sem confirmação", msg)
    d = dispensacoes.pendente_do_atendimento(a1)
    dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
    fluxo.bipar(operacao="dispensar_sala", codigo="7895550000028", usuario="farm1", id_atendimento=a1)
    d = dispensacoes.pendente_do_atendimento(a1)
    dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895550000011", usuario="sala1", id_atendimento=a1)
    conferir(r["ok"], "confirmado o recebimento, o prontuário bipa o uso", r.get("mensagem"))
    ok, msg, enc = fechamento.finalizar_uso(a1, enf)
    dev = devolucoes.pendente_do_atendimento(a1)
    conferir(ok and not enc and dev and len(devolucoes.itens(dev["id_devolucao"], so_pendentes=True)) == 1,
             "finalizar os utilizados: o não usado vai sozinho para a lista da farmácia", msg)
    # v18.13: a sala continua bipando depois de finalizar (só fecha quando a farmácia conclui)
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895550000028", usuario="sala1", id_atendimento=a1)
    conferir(r["ok"], "depois de finalizar, a sala ainda bipa o uso (v18.13)", r.get("mensagem"))
    item_b = devolucoes.itens(dev["id_devolucao"], so_pendentes=True)[0]
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="farm1", responsavel=farm,
                                   nao_recebidos=[item_b["id_item"]])
    conferir(ok and atendimentos.buscar(a1)["status"] == "aberto" and fechamento.pendencias(a1)["total"] == 1
             and fluxo.buscar_unidade(item_b["id_unidade"])["status"] == _ES,
             "farmácia desmarca: item fica com o paciente como pendência; procedimento segue aberto", msg)
    conferir(any(l["id_atendimento"] == a1 for l in fechamento.pendencias_da_sala()), "a sala vê a pendência")
    ok, _ = fechamento.concluir(a1, farm)
    conferir(not ok, "com pendência, a farmácia ainda não conclui")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895550000028", usuario="sala1", id_atendimento=a1)
    conferir(r["ok"] and r["item"]["id_unidade"] == item_b["id_unidade"],
             "a sala confere e bipa o uso do item que não voltou", r.get("mensagem"))
    ok, msg = fechamento.concluir(a1, farm)
    conferir(ok and atendimentos.buscar(a1)["status"] == "encerrado", "a farmácia conclui o procedimento", msg)
    a3 = novo("6603", "11")
    dispensa_e_confirma(a3, "7895550000011")
    ok, msg, enc = fechamento.finalizar_uso(a3, enf)
    dev = devolucoes.pendente_do_atendimento(a3)
    ok, msg = devolucoes.confirmar(id_devolucao=dev["id_devolucao"], operador="farm1", responsavel=farm)
    conferir(ok and atendimentos.buscar(a3)["status"] == "encerrado" and "encerrado" in msg,
             "voltou tudo: a ciência da farmácia encerra o procedimento", msg)
    a4 = novo("6604", "12")
    r = fluxo.bipar(operacao="registrar_uso", codigo="7895550000028", usuario="sala1", id_atendimento=a4)
    ok, msg, enc = fechamento.finalizar_uso(a4, enf)
    # v18.18: finalizar não encerra mais sozinho — a sala fica aberta para
    # material extra e quem fecha é a farmácia.
    conferir(ok and not enc and atendimentos.buscar(a4)["status"] == "aberto",
             "sem material sobrando, finalizar deixa a sala aberta (v18.18)", msg)
    ok, msg = fechamento.concluir(a4, farm)
    conferir(ok and atendimentos.buscar(a4)["status"] == "encerrado",
             "e a farmácia conclui o procedimento (v18.18)", msg)

    print("== Seleção manual pelo código AGHU (não deu para bipar)")
    cadastrar("ITEM MANUAL", "7895550000035", "LM1", "01/01/2031", qtd="2", codigo_aghu="77003", farmacia="BLOCO CIRURGICO")
    cadastrar("ITEM MANUAL", "7895550000035", "LM2", "01/06/2031", qtd="1", codigo_aghu="77003", farmacia="BLOCO CIRURGICO")
    g = fluxo.selecao_manual("dispensar_sala", "77003")
    conferir(len(g) == 2 and {x["lote"] for x in g} == {"LM1", "LM2"} and sum(x["quantidade"] for x in g) == 3,
             "digita o AGHU: aparece um grupo por lote e validade", str([(x["lote"], x["quantidade"]) for x in g]))
    conferir(fluxo.selecao_manual("baixar", "77003") == [], "só vale para dispensar e registrar uso")

    print("== Material NÃO cadastrado usado na sala (exceção das exceções)")
    from src.providers.implementations.opme.services import nao_cadastrados as nc
    ok_n, a_nc = _abrir_at({"prontuario": "6620", "sala": "14", "especialidade": "CARDIO",
                                     "data_procedimento": hoje_iso()}, "sala1")
    base_nc = {"xProd": "PLACA NAO CADASTRADA", "nLote": "PNC1", "dVal": "01/01/2030", "fornecedor": "ORTOX",
               "quantidade": "1", "motivo": "Urgência / emergência", "etiqueta_no_prontuario": "1",
               "usuario_supervisao": "sup1", "senha_supervisao": "Senha2026"}
    ok, msg = nc.registrar(a_nc, base_nc | {"etiqueta_no_prontuario": ""}, {"username": "sala1", "nome": "Enf. Ana Souza"})
    conferir(not ok and "etiqueta" in msg, "exige confirmar que a etiqueta foi colada no prontuário", msg)
    # nov/2026: não exige mais a senha da supervisão.
    ok, msg = nc.registrar(a_nc, base_nc, {"username": "sala1", "nome": "Enf. Ana Souza"})
    reg = nc.listar("pendente")[0] if nc.listar("pendente") else {}
    u_nc = fluxo.buscar_unidade(reg.get("id_unidade", "")) or {}
    conferir(ok and u_nc.get("status") == UTILIZADO and u_nc.get("id_atendimento") == a_nc and u_nc.get("nLote") == "PNC1"
             and db.escalar("SELECT COUNT(*) FROM usos_sem_dispensacao WHERE id_unidade=? AND situacao='pendente'", (u_nc["id_unidade"],)) == 1
             and db.escalar("SELECT COUNT(*) FROM alertas WHERE modulo_destino='almoxarifado' AND titulo LIKE 'Material NÃO cadastrado%'") == 1,
             "registrado no prontuário (lote e validade), alerta ao almoxarifado e ciência da farmácia", msg)
    ok, msg = nc.regularizar(reg["id"], {"codigo_aghu": "88001", "numero_nf": "123", "tipo_entrada": "consignado"}, "almox")
    conferir(ok and nc.contar_pendentes() == 0 and fluxo.buscar_unidade(u_nc["id_unidade"])["codigo_aghu"] == "88001",
             "almoxarifado regulariza o cadastro", msg)
    from src.providers.implementations.opme.services import indicadores as _ind3
    conferir(_ind3.calcular_valores(hoje_iso(), hoje_iso())["materiais_nao_cadastrados"] == 1,
             "indicador: material usado sem cadastro")

    print("== Telas (servidor web)")
    try:
        from fastapi.testclient import TestClient
    except Exception:
        print("  (fastapi/httpx não instalados — parte web pulada)")
        return _fim()
    from src.main import app
    from src.providers.implementations.opme.security import MODULOS, PAPEIS
    # v18.1: + "monitoramento" (Central das salas).
    conferir("farmacia" in MODULOS and PAPEIS["farmacia"][1] == ["painel", "procedimentos", "farmacia", "monitoramento", "consultas", "inventario"],
             "módulo Farmácia v17: caixas de consignado e confirmação de devoluções")
    from tests.opme.legado import ClienteLegado
    with TestClient(app) as _http:
        cliente = ClienteLegado(_http)
        r = cliente.post("/login", data={"username": "admin", "senha": "admin"},
                         follow_redirects=False)
        conferir(r.status_code in (200, 303), "login do admin")
        paginas = ["/", "/almoxarifado", "/almoxarifado/manual", "/almoxarifado/nf",
                   "/sala-procedimento",
                   "/sala-procedimento/atendimentos", f"/sala-procedimento/atendimento/{id_at}",
                   "/sala-procedimento/estorno",
                   "/bipagem/devolver_fornecedor", "/bipagem/baixar",
                   "/consultas", "/consultas/itens", "/consultas/utilizados",
                   f"/consultas/prontuario?numero=21472063",
                   "/inventario", "/consignados", "/indicadores", "/indicadores/fluxo",
                   "/indicadores/desperdicio", "/indicadores/financeiro",
                   "/indicadores/qualidade", "/indicadores/metas", "/admin",
                   "/admin/entrega-paciente", "/consignados/empenhos", "/consignados/empenhos/novo",
                   f"/consignados/empenhos/{id_e1}", f"/sala-procedimento/atendimento/{id_dv}",
                   "/sala-procedimento/atendimentos?operacao=devolver_nao_utilizado",
                   "/consultas/eventos", "/consultas/eventos?prontuario=9991&tipo=devolver_nao_utilizado",
                   "/consultas/eventos?sala=06&unidade=BLOCO%20CIRURGICO",
                   "/consultas/eventos?prontuario=9991&tipo=uso_devolucao",
                   "/consultas/prontuario?numero=9991", "/consultas/prontuario?numero=9991&data=todas",
                   "/farmacia", "/farmacia/caixas-consignado", f"/farmacia/caixas-consignado/{cx}",
                   f"/farmacia/caixas-consignado/{cx}/etiqueta", f"/consultas/caixa/{cx}",
                   f"/consultas/caixa/{cx}?evento=" + str(db.escalar("SELECT MAX(id_evento) FROM eventos WHERE tipo='devolver_caixa'")),
                   "/consultas/eventos?prontuario=7771&tipo=devolver_nao_utilizado",
                   "/farmacia/devolucoes", "/consultas/eventos?tipo=devolucao_etapas",
                   "/devolucoes/" + db.escalar("SELECT id_devolucao FROM devolucoes ORDER BY criado_em LIMIT 1")]
        for p in paginas:
            resp = cliente.get(p, follow_redirects=False)
            conferir(resp.status_code == 200 and len(resp.text) < 300_000
                     and resp.text.count('<main>') == 1,
                     f"GET {p} → 200, página íntegra", f"(veio {resp.status_code}, {len(resp.text)} bytes)")
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={id_at}", follow_redirects=False)
        conferir(resp.status_code == 303 and "/sala-procedimento/atendimento/" in resp.headers["location"],
                 "bipagem de atendimento encerrado leva à ficha (reabertura)")
        ok, _ = atendimentos.reabrir(id_at, "admin", "sup1", "Senha2026", "teste de tela")
        for p in (f"/sala-procedimento/atendimento/{id_at}/concluir",
                  f"/bipagem/registrar_uso?atendimento={id_at}"):
            resp = cliente.get(p, follow_redirects=False)
            conferir(resp.status_code == 200, f"GET {p} → 200", f"(veio {resp.status_code})")
        conferir("alerta-entrega" in resp.text and "Finalizar materiais utilizados" in resp.text,
                 "tela de uso tem o aviso vermelho e o botão Finalizar materiais utilizados")
        resp = cliente.post("/consignados/empenhos/importar",
                            files={"arquivo": ("modelo_empenhos.xlsx", modelo,
                                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        conferir(resp.status_code == 200 and "Resultado da importação" in resp.text and "já existiam" in resp.text,
                 "tela de importação de empenhos mostra o resultado")
        db.executar("UPDATE nf_itens SET qtd_pendente = 1 WHERE id_item IN ('ITC1','ITC2')")
        resp = cliente.get("/almoxarifado/nf/NFTESTE1")
        conferir(resp.status_code == 200 and "veio da NF" in resp.text and "readonly" in resp.text
                 and "A NF não trouxe o código de barras" in resp.text and "Excluir esta nota" in resp.text,
                 "tela da NF: cEAN travado; sem cEAN, campo aberto para bipar", str(resp.status_code))
        db.executar("UPDATE nf_itens SET qtd_pendente = 1 WHERE id_item = 'ITS1'")
        resp = cliente.get("/almoxarifado/nf/NFSEMLOTE")
        conferir(resp.status_code == 200 and "não informado na NF" in resp.text and 'name="nLote_manual"' in resp.text
                 and 'name="dVal_manual"' in resp.text, "tela da NF sem lote/validade abre os campos para digitar")
        resp = cliente.get(f"/consignados/empenhos/{id_e1}?inicio={hoje_iso()}&fim={hoje_iso()}")
        conferir(resp.status_code == 200 and "Baixar PDF" in resp.text and "material(is) vinculado(s) de" in resp.text
                 and "Especialidade" in resp.text and "Validade" in resp.text and "Nº série" in resp.text,
                 "empenho: filtro por período e botão de PDF")
        resp = cliente.get(f"/consignados/empenhos/{id_e1}/pdf?inicio={hoje_iso()}&fim={hoje_iso()}")
        conferir(resp.status_code == 200 and resp.content.startswith(b"%PDF")
                 and "attachment" in resp.headers.get("content-disposition", ""),
                 "PDF dos materiais vinculados é baixado", str(resp.status_code))
        vv = empenhos.vinculos_do_empenho(id_e1)
        conferir(vv and all(v["status"] == "ativo" for v in vv) and all(v["descricao_aghu"] for v in vv)
                 and all(v["unidade_rotulo"] for v in vv), "empenho: só vinculados, com descrição AGHU e unidade")
        conferir(len(empenhos.vinculos_do_empenho(id_e1, inicio="2000-01-01", fim="2000-01-02")) == 0
                 and len(empenhos.vinculos_do_empenho(id_e1)) > 0, "filtro por período restringe os vínculos")
        for pg in ("/farmacia/atendimentos", "/farmacia/dispensacoes", f"/bipagem/dispensar_sala?atendimento={id_p2}",
                   f"/sala-procedimento/atendimento/{id_p1}", "/farmacia", "/consultas/eventos?tipo=dispensacao",
                   "/dispensacoes/" + db.escalar("SELECT id_dispensacao FROM dispensacoes ORDER BY criado_em LIMIT 1")):
            resp = cliente.get(pg)
            conferir(resp.status_code == 200 and resp.text.count("<main>") == 1, f"GET {pg} → 200", str(resp.status_code))
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_p1}")
        conferir("Dispensado pela farmácia" in resp.text, "ficha do atendimento mostra o que foi dispensado")
        resp = cliente.get("/farmacia")
        conferir("Para qual unidade a farmácia está trabalhando?" in resp.text and 'action="/farmacia/unidade"' in resp.text,
                 "Farmácia tem a escolha Bloco / Hemodinâmica")
        cliente.post("/farmacia/unidade", data={"unidade": "HEMODINAMICA - PDT", "proximo": "/farmacia/atendimentos"})
        resp = cliente.get("/farmacia/atendimentos")
        conferir("Você está em" in resp.text and "Hemodinâmica</strong>" in resp.text and "8881" not in resp.text,
                 "escolhida Hemodinâmica, a farmácia lista só os procedimentos dela")
        cliente.post("/farmacia/unidade", data={"unidade": "BLOCO CIRURGICO"})
        resp = cliente.get(f"/farmacia/conciliacao?inicio={hoje_iso()}&fim={hoje_iso()}&unidade=")
        conferir(resp.status_code == 200 and "Conciliação por sala e prontuário" in resp.text and "sala 05" in resp.text
                 and "8881" in resp.text and "8882" in resp.text,
                 "Farmácia → Conciliação por sala")
        resp = cliente.get(f"/farmacia/conciliacao?inicio={hoje_iso()}&fim={hoje_iso()}&unidade=BLOCO%20CIRURGICO&sala=05")
        conferir("Itens —" in resp.text and ("Usado no paciente" in resp.text or "Devolvido ao estoque" in resp.text),
                 "conciliação: detalhe dos itens da sala com o desfecho")
        resp = cliente.get(f"/farmacia/conciliacao?inicio={hoje_iso()}&fim={hoje_iso()}&unidade=&formato=csv")
        conferir(resp.status_code == 200 and "Desfecho" in resp.text, "conciliação exporta planilha")
        resp = cliente.get("/farmacia/usos-sem-dispensacao")
        conferir(resp.status_code == 200 and "Ciências recentes" in resp.text and "Farmacêutica Um" in resp.text,
                 "tela de ciência dos usos sem dispensação")
        resp = cliente.get("/indicadores")
        conferir("Uso sem dispensação da farmácia" in resp.text, "indicador aparece em Indicadores")
        ok_x, id_px = _abrir_at({"prontuario": "8889", "sala": "07", "especialidade": "CARDIO",
                                          "data_procedimento": "2026-01-02"}, "sala1")
        r_px = fluxo.bipar(operacao="dispensar_sala", codigo="7893330000011", usuario="farm1", id_atendimento=id_px)
        lst = (r_px.get("devolucao") or {}).get("lista") or []
        conferir(r_px.get("ok") and len(lst) == 1 and lst[0]["remover"].startswith("/dispensacoes/item/")
                 and lst[0]["descricao"] == "STENT DISP",
                 "bip da dispensação devolve a lista para a tela atualizar sozinha", str(lst))
        resp = cliente.get(f"/sala-procedimento/atendimentos?data={hoje_iso()}")
        conferir("aguardando sua confirmação" in resp.text and "8889" in resp.text and "Confirmar recebimento" in resp.text,
                 "sala vê a dispensação pendente mesmo com outra data no filtro (não some)")
        resp = cliente.get("/sala-procedimento/atendimentos?data=2026-01-02")
        conferir("dispensado — aguardando confirmação" in resp.text, "a linha do procedimento mostra 'aguardando confirmação'")
        resp = cliente.get("/sala-procedimento")
        conferir("Confirmar recebimento da farmácia" in resp.text, "início da Sala avisa da dispensação pendente")
        resp = cliente.get(f"/bipagem/dispensar_sala?atendimento={id_px}")
        conferir("Entregar à sala" not in resp.text and 'id="pendente-lista"' in resp.text
                 and "não precisa bipar de novo" not in resp.text and "Na entrega" not in resp.text,
                 "dispensar: sem botão de senha e sem textos extras; lista com id para atualizar")
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={id_px}")
        conferir("BIPAGEM BLOQUEADA" in resp.text and "ainda não usado(s)" not in resp.text,
                 "registro de uso: só a faixa vermelha (sem a amarela repetida)")
        id_dpx = dispensacoes.pendente_do_atendimento(id_px)["id_dispensacao"]
        resp = cliente.get(f"/dispensacoes/{id_dpx}")
        conferir("usuário logado" in resp.text and 'name="senha"' not in resp.text and 'name="usuario_sala"' not in resp.text,
                 "confirmar na sala: só 'Dar ciência', sem escolher operador nem senha")
        _abrir_sala_da_disp(id_dpx)
        resp = cliente.post(f"/dispensacoes/{id_dpx}/confirmar", data={}, follow_redirects=False)
        ev_x = db.consultar_um("""SELECT e.usuario FROM eventos e JOIN dispensacao_itens i ON i.id_unidade = e.id_unidade
                                  WHERE i.id_dispensacao = ? AND e.tipo = 'confirmar_recebimento_sala'""", (id_dpx,))
        conferir(ev_x and ev_x["usuario"] == "admin", "ciência registrada no login de quem está logado", ev_x)
        conferir(resp.status_code == 303 and resp.headers["location"] == f"/bipagem/registrar_uso?atendimento={id_px}",
                 "confirmou o recebimento → vai direto para o registro de uso", resp.headers.get("location"))
        resp = cliente.get(f"/dispensacoes/atendimento/{id_px}/pdf", follow_redirects=True)
        conferir(resp.status_code == 200 and resp.content.startswith(b"%PDF")
                 and "attachment" in resp.headers.get("content-disposition", ""), "baixa o PDF da dispensação")
        resp = cliente.get(f"/dispensacoes/atendimento/{id_px}/finalizada", follow_redirects=True)
        conferir(resp.status_code == 200 and "Dispensa finalizada" in resp.text and "Baixar PDF para a sala" in resp.text
                 and "Dispensar outro paciente" in resp.text, "Finalizar dispensa mostra o resumo com o PDF")
        resp = cliente.get(f"/bipagem/dispensar_sala?atendimento={id_pc}")
        conferir("Finalizar dispensa" in resp.text and "AGHU 89846" in resp.text and "val. 07/12/2028" in resp.text
                 and resp.text.index('id="codigo"') < resp.text.index('id="pendente-lista"')
                 and 'id="ultimo-nao-registrado"' in resp.text,
                 "dispensar: campo de leitura em cima, lista com AGHU, lote e validade, botão Finalizar")
        ok_m, a_man = _abrir_at({"prontuario": "6610", "sala": "13", "especialidade": "CARDIO",
                                          "data_procedimento": hoje_iso()}, "sala1")
        resp = cliente.get(f"/bipagem/dispensar_sala?atendimento={a_man}")
        conferir('id="selecao-manual"' in resp.text and "Selecionar pelo código AGHU" in resp.text,
                 "dispensar: opção de selecionar pelo AGHU (exceção)")
        grupos = cliente.get(f"/api/selecao-manual?operacao=dispensar_sala&aghu=77003&atendimento={a_man}").json()["grupos"]
        escolha = next(x for x in grupos if x["lote"] == "LM2")
        corpo = {"operacao": "dispensar_sala", "codigo": escolha["id_unidade"], "id_unidade": escolha["id_unidade"],
                 "atendimento": a_man, "selecao_manual": ""}
        r = cliente.post("/api/bipar", json=corpo | {"selecao_manual": "qualquer"}).json()
        conferir(not r["ok"], "seleção manual exige um motivo válido")
        r = cliente.post("/api/bipar", json=corpo | {"selecao_manual": "Leitor não lê o código"}).json()
        # nov/2026: LM2 vence depois do LM1 da mesma farmácia → pede ciência antes (não trava).
        conferir(not r["ok"] and r.get("aviso_validade") and r["mais_proximo"]["lote"] == "LM1"
                 and not db.escalar("SELECT COUNT(*) FROM dispensacao_itens WHERE id_unidade=?", (escolha["id_unidade"],)),
                 "lote com validade mais próxima: avisa e não grava nada antes da ciência", r.get("mensagem"))
        r = cliente.post("/api/bipar", json=corpo | {"selecao_manual": "Leitor não lê o código",
                                                    "ciencia_validade": True}).json()
        conferir(db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='ciencia_validade' AND id_unidade=?",
                            (escolha["id_unidade"],)) == 1, "com a ciência, dispensa e registra a ciência no histórico")
        ev = db.consultar_um("SELECT * FROM eventos WHERE tipo='selecao_manual' AND id_unidade=?", (escolha["id_unidade"],))
        conferir(r["ok"] and r["item"]["lote"] == "LM2" and ev and ev["motivo"] == "Leitor não lê o código",
                 "escolhe o lote e dispensa; fica registrado com o motivo", r.get("mensagem"))
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={a_man}")
        conferir('id="selecao-manual"' in resp.text, "registro de uso: mesma opção")
        conferir("/nao-cadastrado" in resp.text, "tela de uso tem o acesso ao material não cadastrado")
        resp = cliente.get(f"/sala-procedimento/atendimento/{a_man}/nao-cadastrado")
        conferir(resp.status_code == 200 and "etiqueta_no_prontuario" in resp.text and "senha_supervisao" in resp.text,
                 "tela de material não cadastrado (etiqueta no prontuário + supervisão)")
        resp = cliente.get("/almoxarifado/nao-cadastrados")
        conferir(resp.status_code == 200 and "Regularizados recentemente" in resp.text, "almoxarifado: tela de regularização")
        from src.providers.implementations.opme.services import indicadores as _ind2
        v = _ind2.calcular_valores(hoje_iso(), hoje_iso())
        ut = _ind2.utilizacao_dispensado(hoje_iso(), hoje_iso())
        pc = _ind2.pendentes_ciencia_farmacia()
        conferir(v["taxa_selecao_manual"] and v["taxa_selecao_manual"] > 0
                 and v["procedimentos_cancelados"] >= 1 and v["procedimentos_criados"] is not None
                 and ut["dispensados"] > 0 and v["taxa_utilizacao_dispensado"] == round(100 * ut["usados"] / ut["dispensados"], 1)
                 and v["pendentes_ciencia_farmacia"] == pc["total"],
                 "indicadores novos: seleção manual, criados/cancelados, utilização do dispensado, ciência pendente",
                 str({k: v[k] for k in ("taxa_selecao_manual", "procedimentos_cancelados", "procedimentos_criados",
                                        "taxa_utilizacao_dispensado", "pendentes_ciencia_farmacia")}))
        resp = cliente.get("/indicadores")
        conferir(all(t in resp.text for t in ("Seleção manual pelo AGHU", "Utilização do material dispensado",
                                              "Itens aguardando a ciência da farmácia", "Procedimentos cancelados",
                                              "Procedimentos abertos fora da agenda")),
                 "os novos indicadores aparecem em Indicadores")
        resp = cliente.get("/sala-procedimento")
        conferir("Falta concluir a bipagem" not in resp.text, "início da Sala: sem o card de concluir (fica só o de confirmar recebimento)")
        resp = cliente.get("/sala-procedimento/atendimentos")
        conferir('id="a-concluir"' in resp.text and "8889" in resp.text, "lista de atendimentos a concluir (qualquer data)")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_px}/concluir")
        conferir("Devolver os não utilizados à farmácia (1)" in resp.text and "/finalizar-uso" in resp.text,
                 "finalizar mostra os não utilizados que vão para a farmácia")
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_px}/finalizar-uso")
        conferir(resp.status_code == 200 and "lista de não utilizados está com a farmácia" in resp.text,
                 "finalizou os utilizados: a lista vai sozinha para a farmácia", resp.text[:0])
        resp = cliente.get(f"/bipagem/devolver_nao_utilizado?atendimento={id_px}", follow_redirects=False)
        conferir(resp.status_code == 303, "a tela de bipar a devolução saiu (redireciona para a ficha)")
        resp = cliente.get("/farmacia/procedimentos-a-concluir")
        conferir(resp.status_code == 200 and "8889" in resp.text and "dar ciência" in resp.text,
                 "farmácia: procedimentos a concluir")
        resp = cliente.get(f"/devolucoes/atendimento/{id_px}")
        conferir("Dar ciência da devolução" in resp.text and 'name="senha"' not in resp.text,
                 "farmácia dá ciência com o usuário logado, sem senha")
        resp = cliente.post(resp.url.path + "/confirmar", data={}, follow_redirects=True)
        conferir(resp.status_code == 200 and "Não voltou para a farmácia (1)" in resp.text and "Recebi de volta" in resp.text,
                 "desmarcado (nada marcado): fica como pendência com 'Recebi de volta'", str(resp.status_code))
        resp = cliente.get("/sala-procedimento/atendimentos")
        conferir('id="nao-recebidos"' in resp.text and "8889" in resp.text, "sala recebe o alerta para conferir")
        u_px = db.escalar("SELECT id_unidade FROM unidades WHERE id_atendimento=? AND status='em_sala'", (id_px,))
        resp = cliente.post(f"/farmacia/procedimento/{id_px}/receber", data={"id_unidade": u_px}, follow_redirects=True)
        conferir("Tudo certo" in resp.text and fluxo.buscar_unidade(u_px)["status"] == "em_estoque_farmacia",
                 "farmácia marca 'Recebi de volta': item volta ao estoque",
                 (resp.text.split('class="aviso')[1][:300] if 'class="aviso' in resp.text else str(u_px)))
        resp = cliente.post(f"/farmacia/procedimento/{id_px}/concluir", follow_redirects=True)
        conferir(atendimentos.buscar(id_px)["status"] == "encerrado", "farmácia conclui o procedimento")
        resp = cliente.get("/consignados/empenhos/novo")
        conferir("Número do pregão" in resp.text and "Fim da vigência" in resp.text and "Baixar modelo" in resp.text,
                 "cadastro manual tem os campos da licitação")
        conferir(cliente.get("/static/modelo_empenhos.xlsx").status_code == 200, "modelo da planilha para baixar")
        resp = cliente.get("/consignados/empenhos")
        conferir("vigência vencida" in resp.text and "Pregão 51/2026" in resp.text, "lista mostra vigência e pregão")
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={id_at}")
        conferir('id="caixa-ativa"' in resp.text and "Sair da caixa" in resp.text,
                 "tela de uso tem o destaque da caixa ativa")
        fluxo.bipar(operacao="devolver_nao_utilizado", codigo="7897777777777", usuario="sala1",
                    devolvido_por="Enf. Ana Souza", id_atendimento=id_dv)
        resp = cliente.get(f"/devolucoes/atendimento/{id_dv}")
        conferir(resp.status_code == 200 and "Dar ciência da devolução" in resp.text and 'name="recebido"' in resp.text,
                 "lista de não utilizados abre para a farmácia conferir")
        conferir('value="bipando"' in resp.text and 'id="bip-devolucao"' in resp.text,
                 "ciência da farmácia: opção de conferir pela lista ou bipando")
        from src.providers.implementations.opme.services import devolucoes as _dv
        dv_pend = _dv.pendente_do_atendimento(id_dv)
        r_id = cliente.get(f"/devolucoes/{dv_pend['id_devolucao']}/identificar", params={"codigo": "7897777777777"}).json()
        r_no = cliente.get(f"/devolucoes/{dv_pend['id_devolucao']}/identificar", params={"codigo": "0000000000000"}).json()
        conferir(r_id["ok"] and r_id["itens"] and not r_no["ok"] and "não está nesta lista" in r_no["mensagem"],
                 "bip na conferência acha o item da lista e recusa o que não está nela")
        # Bloco x Hemodinâmica
        resp = cliente.get("/sala-procedimento")
        conferir("Onde é o procedimento?" in resp.text, "sem unidade escolhida, a Sala pergunta onde é")
        _abrir_at({"prontuario": "5550555", "unidade": "HEMODINAMICA - PDT", "sala": "01",
                            "especialidade": "CARDIOLOGIA", "data_procedimento": hoje_iso(),
                            "opme_solicitado": "stent"}, "sala1")
        cliente.post("/sala-procedimento/unidade", data={"unidade": "HEMODINAMICA - PDT"})
        resp = cliente.get("/sala-procedimento/atendimentos")
        conferir("5550555" in resp.text and "21472063" not in resp.text,
                 "escolhida Hemodinâmica: lista só atendimentos dela")
        conferir('/procedimentos#novo' in resp.text and 'name="prontuario" required' not in resp.text,
                 "abrir procedimento saiu da Sala: a tela aponta para Procedimentos")
        cliente.post("/sala-procedimento/unidade", data={"unidade": "BLOCO CIRURGICO"})
        resp = cliente.get("/sala-procedimento/atendimentos")
        conferir("5550555" not in resp.text, "trocou para Bloco: a lista acompanha")
        resp = cliente.get("/indicadores/fluxo")
        conferir("Cancelamento de procedimentos" in resp.text and "Falta de leito" in resp.text,
                 "indicador e detalhe aparecem em Indicadores → Fluxo")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_c1}")
        conferir("Procedimento cancelado" in resp.text, "ficha mostra o cancelamento e o motivo")
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_c2}/cancelar",
                            data={"motivo": "Falta de leito / UTI"}, follow_redirects=False)
        conferir(resp.status_code == 303, "rota de cancelamento responde")
        resp = cliente.get("/consultas/eventos?prontuario=9991&tipo=devolver_nao_utilizado&formato=csv")
        conferir(resp.status_code == 200 and "text/csv" in resp.headers.get("content-type", "")
                 and "Farmacêutica Um" in resp.text, "botão de planilha baixa o CSV filtrado")
        resp = cliente.get("/consultas/prontuario?numero=9991&data=todas")
        conferir("devolvido(s) sem uso" in resp.text and "Farmacêutica Um" in resp.text and "Enf. Ana Souza" in resp.text,
                 "tela do prontuário mostra usos e devoluções")
        resp = cliente.post(f"/farmacia/caixas-consignado/{cx2}/adicionar", data={"codigo": "400999"})
        conferir(resp.status_code == 200 and "ATENÇÃO! Escolha o item" in resp.text and "LA1" in resp.text,
                 "tela da caixa: AGHU com 2 lotes mostra a escolha")
        resp = cliente.post("/api/ciencia-entrega", json={"id_unidade": "nao-existe"})
        conferir(resp.json()["ok"] is False, "API de ciência recusa item inválido")
        # nov/2026: /almoxarifado/caixas voltou (caixas de consignado montadas no almoxarifado).
        for p in ("/almoxarifado/reposicao", "/caixas", "/almoxarifado/caixas-consignado"):
            resp = cliente.get(p, follow_redirects=False)
            conferir(resp.status_code == 404, f"{p} não existe mais (caixas removidas)")
        resp = cliente.get("/farmacia/kit/x", follow_redirects=False)
        conferir(resp.status_code == 404, "telas antigas da farmácia (kit) não existem mais")
        resp = cliente.get("/bipagem/enviar_farmacia", follow_redirects=False)
        conferir(resp.status_code in (303, 307), "tela de envio à farmácia redireciona")
        resp = cliente.post("/procedimentos", data={
            "prontuario": "999", "local": "BLOCO CIRURGICO|03", "especialidade": "VASCULAR",
            "data_procedimento": hoje_iso(), "seguir": "uso"}, follow_redirects=False)
        conferir(resp.status_code == 303 and "/bipagem/registrar_uso" in resp.headers["location"],
                 "Procedimentos: abre e vai direto para a bipagem do uso")
        resp = cliente.post("/procedimentos", data={
            "prontuario": "998", "local": "BLOCO CIRURGICO|04", "especialidade": "VASCULAR",
            "data_procedimento": hoje_iso(), "seguir": "dispensar"}, follow_redirects=False)
        conferir(resp.status_code == 303 and "/bipagem/dispensar_sala" in resp.headers["location"],
                 "Procedimentos: abre e vai direto para a dispensação")
        resp = cliente.get(f"/procedimentos?data={hoje_iso()}&so_opme=0")
        conferir(resp.status_code == 200 and "Abrir procedimento" in resp.text and "998" in resp.text
                 and "Dispensar" in resp.text and "Registrar uso" in resp.text,
                 "Procedimentos: lista geral com dispensar (farmácia) e registrar uso (sala)")

        print("== Fase 2: especialidades padronizadas")
        from src.providers.implementations.opme.utils import padronizar_especialidade as _pe
        conferir(_pe("cir geral") == "CIRURGIA GERAL" and _pe("Cir. Geral") == "CIRURGIA GERAL"
                 and _pe("CARDIO") == "CARDIOLOGIA" and _pe("Cardiologia") == "CARDIOLOGIA"
                 and _pe("GINECO") == "GINECOLOGIA" and _pe("CIR ONCOLOGICA") == "CIRURGIA ONCOLOGICA"
                 and _pe("ORTOPEDIA") == "ORTOPEDIA E TRAUMATOLOGIA" and _pe("NEURO") == "NEUROLOGIA",
                 "abreviações viram o nome padronizado (cir geral = cirurgia geral, cardio = cardiologia)")
        ok_e, id_e = _abrir_at({"prontuario": "7070", "sala": "21", "especialidade": "cir geral",
                                         "data_procedimento": hoje_iso()}, "sala1")
        conferir(ok_e and atendimentos.buscar(id_e)["especialidade"] == "CIRURGIA GERAL",
                 "abrir procedimento grava o nome padronizado")
        with db.transacao() as conn:
            conn.execute("UPDATE atendimentos SET especialidade = 'CIR GERAL' WHERE id_atendimento = ?", (id_e,))
            db._padronizar_especialidades(conn)
        conferir(atendimentos.buscar(id_e)["especialidade"] == "CIRURGIA GERAL"
                 and "CARDIO" not in atendimentos.especialidades()
                 and "CIRURGIA GERAL" in atendimentos.especialidades(),
                 "registros antigos são regravados com o nome padronizado", str(atendimentos.especialidades()))
        resp = cliente.get("/procedimentos")
        conferir("Ortopedia e Traumatologia" in resp.text and "Eletrofisiologia" in resp.text
                 and "Endoscopia Ginecológica" in resp.text and ">Bucomaxilofacial<" not in resp.text,
                 "Abrir procedimento lista as especialidades do hospital")
        conferir(not db.escalar("SELECT COUNT(*) FROM atendimentos WHERE especialidade IN ('CARDIO','CIR GERAL')"),
                 "nenhum atendimento ficou com o nome abreviado")

        print("== Fase 2: registro de uso mostra o que já foi bipado, com excluir")
        cadastrar("FIO F2", "7896660000011", "LF2", "01/01/2031", qtd="3", codigo_aghu="88001")
        cadastrar("CLIP F2", "7896660000028", "LC2", "01/01/2031", qtd="2", codigo_aghu="88002")
        ok_u, id_u = _abrir_at({"prontuario": "7071", "sala": "22", "especialidade": "CARDIO",
                                         "data_procedimento": hoje_iso()}, "sala1")
        resp = cliente.post("/api/bipar", json={"operacao": "registrar_uso", "codigo": "7896660000011",
                                                 "atendimento": id_u})
        d1 = resp.json()
        resp = cliente.post("/api/bipar", json={"operacao": "registrar_uso", "codigo": "7896660000028",
                                                 "atendimento": id_u})
        d2 = resp.json()
        conferir(d1.get("ok") and d2.get("ok") and len(d2["uso"]["lista"]) == 2
                 and d2["uso"]["lista"][0]["id_unidade"] == d2["item"]["id_unidade"]
                 and d2["uso"]["pode_excluir"],
                 "cada leitura devolve a lista do paciente, o último bipado em cima", str(d2.get("uso"))[:300])
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={id_u}")
        t = resp.text
        conferir('id="uso-lista"' in t and "CLIP F2" in t and "data-excluir-uso" in t
                 and t.index('id="uso-lista"') < t.index('id="contador-lidos"'),
                 "tela de uso: lista aparece logo abaixo do campo, com 'excluir'")
        resp = cliente.post("/api/excluir-uso", json={"atendimento": id_u,
                                                      "id_unidade": d1["item"]["id_unidade"], "motivo": ""})
        conferir(resp.json()["ok"] is False, "excluir na tela de uso exige o motivo")
        resp = cliente.post("/api/excluir-uso", json={"atendimento": id_u,
                                                      "id_unidade": d1["item"]["id_unidade"],
                                                      "motivo": "Bipado em duplicidade"})
        dx = resp.json()
        conferir(dx["ok"] and len(dx["uso"]["lista"]) == 1
                 and fluxo.buscar_unidade(d1["item"]["id_unidade"])["status"] == EM_ESTOQUE_RECEBIMENTO
                 and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='excluir_bip' AND id_unidade=?",
                                (d1["item"]["id_unidade"],)) == 1,
                 "excluir na tela de uso: item sai da lista, volta ao estoque e fica no histórico", dx.get("mensagem"))

        print("== Fase 2: procedimento cancelado devolve o material direto para a farmácia")
        from src.providers.implementations.opme.services import dispensacoes as _disp
        from src.providers.implementations.opme.domain import EM_SALA as _ES2, TRANSITO_SALA as _TS2
        cadastrar("STENT F2", "7896660000035", "LS2", "01/01/2031", qtd="3", codigo_aghu="88003", farmacia="BLOCO CIRURGICO")
        ok_k, id_k = _abrir_at({"prontuario": "7072", "sala": "23", "especialidade": "CARDIO",
                                         "data_procedimento": hoje_iso()}, "sala1")
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000035", usuario="farm1", id_atendimento=id_k)
        u_k = r["item"]["id_unidade"]
        resp = cliente.get(f"/bipagem/dispensar_sala?atendimento={id_k}")
        conferir(f'/farmacia/atendimento/{id_k}/cancelar' in resp.text and "voltam <strong>direto para o estoque" in resp.text,
                 "tela da farmácia tem 'Procedimento cancelado' com a devolução direta")
        resp = cliente.get("/farmacia/atendimentos")
        conferir(f"dispensar_sala?atendimento={id_k}#cancelar" in resp.text, "lista da farmácia tem o botão Cancelado")
        resp = cliente.post(f"/farmacia/atendimento/{id_k}/cancelar", data={"motivo": ""}, follow_redirects=False)
        conferir(resp.status_code == 303 and atendimentos.buscar(id_k)["status"] == "aberto",
                 "sem motivo não cancela")
        resp = cliente.post(f"/farmacia/atendimento/{id_k}/cancelar",
                            data={"motivo": "Falta de leito / UTI"}, follow_redirects=False)
        uk = fluxo.buscar_unidade(u_k)
        conferir(resp.status_code == 303 and atendimentos.buscar(id_k)["status"] == "cancelado"
                 and uk["status"] == "em_estoque_farmacia" and not uk["id_atendimento"]
                 and not _disp.pendente_do_atendimento(id_k)
                 and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='devolvido_por_cancelamento' AND id_unidade=?", (u_k,)) == 1,
                 "farmácia cancela: o dispensado volta direto ao estoque, sem paciente, com histórico", str(dict(uk)))
        from src.providers.implementations.opme.services import solicitacoes as _sol9
        ok_c9, id_c9 = _abrir_at({"prontuario": "7099", "sala": "30", "especialidade": "ORTOPEDIA",
                                           "data_procedimento": hoje_iso()}, "sala1")
        _sol9.adicionar_avulso(id_c9, "88060", "1", "ANCORA", "sala1")
        abertos_antes = _sol9.contar_em_aberto()
        atendimentos.cancelar(id_c9, "sala1", "Falta de leito / UTI")
        conferir(_sol9.situacao(id_c9)["cancelada_em"] and _sol9.contar_em_aberto() == abertos_antes - 1,
                 "procedimento cancelado cancela a solicitação de OPME (sai do alerta da farmácia)")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_k}")
        conferir("não foi para a sala" in resp.text and "voltou ao estoque da farmácia" in resp.text
                 and "aguardando a confirmação" not in resp.text,
                 "ficha do cancelado: dispensado aparece como 'não foi para a sala' e 'voltou ao estoque'")
        # Sala já recebeu: a farmácia não cancela, a sala sim.
        ok_k2, id_k2 = _abrir_at({"prontuario": "7073", "sala": "24", "especialidade": "CARDIO",
                                           "data_procedimento": hoje_iso()}, "sala1")
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000035", usuario="farm1", id_atendimento=id_k2)
        u_k2 = r["item"]["id_unidade"]
        dd = _disp.pendente_do_atendimento(id_k2)
        _disp.confirmar(id_dispensacao=dd["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
        # Material chegou na sala e ainda sem ciência: a tela de confirmar oferece cancelar.
        ok_k4, id_k4 = _abrir_at({"prontuario": "7075", "sala": "28", "especialidade": "CARDIO",
                                           "data_procedimento": hoje_iso()}, "sala1")
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000035", usuario="farm1", id_atendimento=id_k4)
        u_k4 = r["item"]["id_unidade"]
        d4 = _disp.pendente_do_atendimento(id_k4)
        resp = cliente.get(f"/dispensacoes/{d4['id_dispensacao']}")
        conferir("Confirmar recebimento na sala" in resp.text
                 and f'/sala-procedimento/atendimento/{id_k4}/cancelar' in resp.text,
                 "tela de ciência da sala oferece 'procedimento cancelado' no lugar de confirmar")
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={id_k4}")
        conferir("BIPAGEM BLOQUEADA" in resp.text and f"/sala-procedimento/atendimento/{id_k4}#cancelar" in resp.text,
                 "aviso de bloqueio na tela de uso também oferece cancelar")
        cliente.post(f"/sala-procedimento/atendimento/{id_k4}/cancelar", data={"motivo": "Falta de leito / UTI"})
        resp = cliente.get(f"/dispensacoes/{d4['id_dispensacao']}")
        conferir(atendimentos.buscar(id_k4)["status"] == "cancelado"
                 and fluxo.buscar_unidade(u_k4)["status"] == "em_estoque_farmacia"
                 and "voltou à farmácia (cancelado)" in resp.text,
                 "sala cancela sem dar ciência: todo o material volta à farmácia")
        ok, msg = atendimentos.cancelar(id_k2, "farm1", "Falta de leito / UTI", pela="farmacia")
        conferir(not ok and fluxo.buscar_unidade(u_k2)["status"] == _ES2,
                 "material já recebido pela sala: a farmácia não cancela (a sala cancela)", msg)
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_k2}")
        conferir(f'/sala-procedimento/atendimento/{id_k2}/cancelar' in resp.text and "1 item(ns)" in resp.text,
                 "ficha da sala mostra o cancelamento com o material a devolver")
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_k2}/cancelar",
                            data={"motivo": "Paciente sem condição clínica"}, follow_redirects=False)
        from src.providers.implementations.opme.services import devolucoes as _dvk
        dvk = _dvk.pendente_do_atendimento(id_k2)
        conferir(atendimentos.buscar(id_k2)["status"] == "cancelado"
                 and fluxo.buscar_unidade(u_k2)["status"] == "em_sala" and dvk,
                 "v18: sala cancela depois da ciência: material aguarda a ciência da farmácia")
        ok, msg = _dvk.confirmar(id_devolucao=dvk["id_devolucao"], operador="farm1",
                                 responsavel={"username": "farm1", "nome": "Farm", "papel": "farmacia"})
        conferir(ok and fluxo.buscar_unidade(u_k2)["status"] == "em_estoque_farmacia",
                 "v18: depois da ciência o material está no estoque da farmácia", msg)
        ok_k3, id_k3 = _abrir_at({"prontuario": "7074", "sala": "25", "especialidade": "CARDIO",
                                           "data_procedimento": hoje_iso()}, "sala1")
        fluxo.bipar(operacao="registrar_uso", codigo="7896660000035", usuario="sala1", id_atendimento=id_k3)
        ok, msg = atendimentos.cancelar(id_k3, "sala1", "Falta de leito / UTI")
        conferir(not ok and atendimentos.buscar(id_k3)["status"] == "aberto",
                 "com material utilizado não cancela", msg)

        print("== Solicitação de OPME (sala) × dispensação (farmácia)")
        from src.providers.implementations.opme.services import solicitacoes as _sol
        from src.providers.implementations.opme.formularios_opme import FORMULARIOS as _F, linhas as _lin
        conferir(all(len(f["linhas"]) for f in _F.values()) and len(_F) == 7,
                 "os 7 formulários de papel estão no sistema")
        cadastrar("INTRODUTOR FEMORAL 6F", "7896660000042", "LI6", "01/01/2031", qtd="3", codigo_aghu="23265", farmacia="HEMODINAMICA - PDT")
        cadastrar("INTRODUTOR FEMORAL 7F", "7896660000059", "LI7", "01/01/2031", qtd="3", codigo_aghu="23276", farmacia="HEMODINAMICA - PDT")
        cadastrar("FIO GUIA J LONGO", "7896660000066", "LFJ", "01/01/2031", qtd="3", codigo_aghu="402587", farmacia="HEMODINAMICA - PDT")
        ok_s, id_s = _abrir_at({"prontuario": "7080", "unidade": "HEMODINAMICA - PDT", "sala": "01",
                                         "especialidade": "CARD INTERV", "data_procedimento": hoje_iso()}, "sala1")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_s}/solicitacao")
        conferir(resp.status_code == 200 and "INTRODUTOR FEMORAL Nº 6,0" in resp.text and "(sugerido)" in resp.text,
                 "Hemodinâmica: a sala abre o formulário sugerido")
        lin = {l["descricao"]: l["linha"] for l in _lin("hemodinamica")}
        n_cat = next(l["linha"] for l in _lin("hemodinamica") if l["descricao"].startswith("CATETER DIAGNÓSTICO"))
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_s}/solicitacao", data={
            "formulario": "hemodinamica", f"qtd_{lin['INTRODUTOR FEMORAL Nº 6,0']}": "1",
            f"qtd_{lin['FIO GUIA J TEFLONADO 0,35 LONGO']}": "2", f"qtd_{n_cat}": "1"}, follow_redirects=True)
        conferir("Escreva o tipo/tamanho" in resp.text and not _sol.situacao(id_s)["existe"],
                 "linha sem código exige o tipo/tamanho")
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_s}/solicitacao", data={
            "formulario": "hemodinamica", f"qtd_{lin['INTRODUTOR FEMORAL Nº 6,0']}": "1",
            f"qtd_{lin['FIO GUIA J TEFLONADO 0,35 LONGO']}": "2", f"qtd_{n_cat}": "1",
            f"espec_{n_cat}": "JR4 5F", "observacao": "urgente"}, follow_redirects=True)
        st = _sol.situacao(id_s)
        conferir(st["existe"] and st["qtd_linhas"] == 3 and st["qtd_faltando"] == 3 and st["observacao"] == "urgente",
                 "sala grava a solicitação: 3 itens, todos faltando", str(st["linhas"])[:200])
        rb = cliente.get("/sala-procedimento/solicitacao/buscar", params={"q": "grampeador linear 45", "formulario": "hemodinamica"}).json()
        conferir(any(i["codigos"] == "95225" and "Lapsus" in i["origem"] for i in rb["itens"]),
                 "busca na solicitação acha item de OUTRO formulário", str(rb)[:200])
        rb2 = cliente.get("/sala-procedimento/solicitacao/buscar", params={"q": "introdutor femoral 7f", "formulario": "ortopedia"}).json()
        conferir(any(i["origem"] == "formulário Hemodinâmica — Núcleo Integrado de Dispensação Imagem" or i["codigos"] == "23276"
                     for i in rb2["itens"]), "busca acha também no cadastro / estoque", str(rb2)[:200])
        ri = cliente.post(f"/sala-procedimento/atendimento/{id_s}/solicitacao/incluir",
                          json={"codigo": "95225", "descricao": "GRAMPEADOR ENDOSCÓPICO LINEAR 45MM", "quantidade": 1}).json()
        n_antes = _sol.situacao(id_s)["qtd_linhas"]
        conferir(ri["ok"] and any(l["codigos"] == "95225" for l in _sol.situacao(id_s)["linhas"]),
                 "incluir da busca entra na solicitação sem trocar de formulário")
        it_g = next(l for l in _sol.situacao(id_s)["linhas"] if l["codigos"] == "95225")
        _sol.remover_item(id_s, it_g["id_item"], "sala1")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_s}/solicitacao/painel")
        conferir(resp.status_code == 200 and "Solicitado até agora" in resp.text, "quadro do solicitado se atualiza sem recarregar")
        ok, msg = _sol.adicionar_avulso(id_s, "88129", "1", "CONECTOR Y", "sala1")
        conferir(ok and _sol.situacao(id_s)["qtd_linhas"] == 4, "item fora do formulário pelo código AGHU", msg)
        cliente.post("/farmacia/unidade", data={"unidade": "HEMODINAMICA - PDT"})
        resp = cliente.get("/farmacia")
        conferir("alerta-pedido-opme" in resp.text and "solicitação(ões) de OPME em aberto" in resp.text,
                 "farmácia recebe o alerta piscando de pedido em aberto")
        resp = cliente.get("/farmacia/solicitacoes")
        conferir("7080" in resp.text and "Atender" in resp.text, "lista de solicitações em aberto")
        cliente.post("/farmacia/unidade", data={"unidade": "BLOCO CIRURGICO"})
        r_bl = cliente.get("/farmacia/solicitacoes").text
        cliente.post("/farmacia/unidade", data={"unidade": "HEMODINAMICA - PDT"})
        r_hd = cliente.get("/farmacia/solicitacoes").text
        conferir("7080" not in r_bl and "7080" in r_hd and "— Hemodinâmica" in r_hd,
                 "alerta e lista só da unidade que a farmácia atende (Bloco não vê pedido da Hemodinâmica)")
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_s}/solicitacao",
                            data={"formulario": "hemodinamica", f"qtd_{lin['INTRODUTOR FEMORAL Nº 6,0']}": "1",
                                  f"qtd_{lin['FIO GUIA J TEFLONADO 0,35 LONGO']}": "2", f"qtd_{n_cat}": "1",
                                  f"espec_{n_cat}": "JR4 5F", "observacao": "urgente", "seguir": "concluir"},
                            follow_redirects=False)
        conferir(resp.headers["location"].endswith(f"/sala-procedimento/atendimento/{id_s}#solicitacao"),
                 "Concluir solicitação grava e volta para a ficha")
        resp = cliente.get(f"/bipagem/dispensar_sala?atendimento={id_s}")
        conferir('id="painel-solicitacao"' in resp.text and "JR4 5F" in resp.text and "aguardando farmácia" in resp.text,
                 "farmácia vê a solicitação na tela de dispensar")
        r1 = cliente.post("/api/bipar", json={"operacao": "dispensar_sala", "codigo": "7896660000042",
                                               "atendimento": id_s}).json()
        st = _sol.situacao(id_s)
        l6 = next(l for l in st["linhas"] if l["codigos"] == "23265")
        conferir(r1["ok"] and not r1.get("nao_solicitado") and l6["status"] == "atendido",
                 "bip do material pedido dá o check na linha", str(r1.get("alertas")))
        r2 = cliente.post("/api/bipar", json={"operacao": "dispensar_sala", "codigo": "7896660000059",
                                               "atendimento": id_s}).json()
        st = _sol.situacao(id_s)
        conferir(r2["ok"] and r2.get("nao_solicitado") and "NÃO SOLICITADO" in " ".join(r2.get("alertas", []))
                 and len(st["nao_solicitados"]) == 1 and st["nao_solicitados"][0]["aghu"] == "23276",
                 "bip de material diferente: aceito e sinalizado como não solicitado", str(r2.get("alertas")))
        r3 = cliente.post("/api/bipar", json={"operacao": "dispensar_sala", "codigo": "7896660000042",
                                               "atendimento": id_s}).json()
        conferir(r3["ok"] and "além da quantidade" in " ".join(r3.get("alertas", [])),
                 "bip além da quantidade pedida também é sinalizado")
        r4 = cliente.post("/api/bipar", json={"operacao": "dispensar_sala", "codigo": "7896660000066",
                                               "atendimento": id_s}).json()
        st = _sol.situacao(id_s)
        fio = next(l for l in st["linhas"] if l["codigos"] == "402587")
        conferir(fio["status"] == "parcial" and fio["dispensado"] == 1, "pedido 2, bipado 1: fica parcial")
        resp = cliente.get(f"/farmacia/atendimento/{id_s}/solicitacao/painel")
        conferir(resp.status_code == 200 and "sem estar na solicitação" in resp.text and "parcial" in resp.text,
                 "painel redesenhado a cada bip mostra checks e o não solicitado")
        # Item COM código atendido por material bipado com outro código (código mudou).
        resp = cliente.get(f"/farmacia/atendimento/{id_s}/solicitacao/painel")
        conferir("foi atendido com outro código AGHU" in resp.text, "linha com código oferece 'atendido com outro código'")
        conector = next(l for l in st["linhas"] if l["codigos"] == "88129")
        g7 = next(g for g in st["nao_solicitados"] if g["aghu"] == "23276")
        resp = cliente.post(f"/farmacia/atendimento/{id_s}/solicitacao/outro-codigo/{conector['id_item']}",
                            data={"unidades": ",".join(g7["ids"]), "motivo": ""}, follow_redirects=True)
        conferir(next(l for l in _sol.situacao(id_s)["linhas"] if l["codigos"] == "88129")["status"] != "atendido",
                 "outro código exige o motivo")
        cliente.post(f"/farmacia/atendimento/{id_s}/solicitacao/outro-codigo/{conector['id_item']}",
                     data={"unidades": ",".join(g7["ids"]), "motivo": "Código AGHU do material mudou"})
        st2 = _sol.situacao(id_s)
        lc = next(l for l in st2["linhas"] if l["codigos"] == "88129")
        conferir(lc["status"] == "atendido" and lc["vinculos"] and lc["vinculos"][0]["aghu"] == "23276"
                 and all(g["aghu"] != "23276" for g in st2["nao_solicitados"]),
                 "vinculado: a linha fica atendida e o material sai de 'não solicitado'", str(lc))
        cliente.post(f"/farmacia/atendimento/{id_s}/solicitacao/outro-codigo/{conector['id_item']}", data={"desfazer": "1"})
        st3 = _sol.situacao(id_s)
        conferir(next(l for l in st3["linhas"] if l["codigos"] == "88129")["status"] == "faltando"
                 and any(g["aghu"] == "23276" for g in st3["nao_solicitados"]),
                 "desfazer o vínculo volta ao que era")
        cat = next(l for l in st["linhas"] if l["sem_codigo"])
        cliente.post(f"/farmacia/atendimento/{id_s}/solicitacao/manual/{cat['id_item']}", data={"atendido": "1"})
        conferir(next(l for l in _sol.situacao(id_s)["linhas"] if l["sem_codigo"])["status"] == "atendido",
                 "linha sem código: a farmácia marca atendido à mão")
        resp = cliente.post(f"/farmacia/atendimento/{id_s}/finalizar-dispensa", data={}, follow_redirects=False)
        conferir(resp.status_code == 303 and resp.headers["location"].endswith("#finalizar"),
                 "finalizar dispensa com item faltando pede o motivo")
        resp = cliente.post(f"/farmacia/atendimento/{id_s}/finalizar-dispensa",
                            data={"motivo": "Sem estoque na farmácia"}, follow_redirects=False)
        st = _sol.situacao(id_s)
        conferir(resp.status_code == 303 and "/finalizada" in resp.headers["location"]
                 and st["motivo_faltas"] == "Sem estoque na farmácia"
                 and db.escalar("SELECT COUNT(*) FROM eventos WHERE tipo='solicitacao_divergente' AND id_atendimento=?", (id_s,)) == 1,
                 "com motivo, finaliza e registra a divergência")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_s}")
        conferir('id="solicitacao"' in resp.text and "Sem estoque na farmácia" in resp.text and "parcial" in resp.text,
                 "a sala vê na ficha o que não veio e o motivo")
        u_extra = r2["item"]["id_unidade"]
        it = db.consultar_um("SELECT id_item FROM dispensacao_itens WHERE id_unidade=? AND situacao='pendente'", (u_extra,))
        cliente.post(f"/dispensacoes/item/{it['id_item']}/remover")
        conferir(not _sol.situacao(id_s)["nao_solicitados"] or all(g["aghu"] != "23276" for g in _sol.situacao(id_s)["nao_solicitados"]),
                 "tirar o item da dispensação tira também o aviso de não solicitado")
        resp = cliente.get("/farmacia/atendimentos", params={"unidade": "HEMODINAMICA - PDT", "prontuario": "7080"})
        conferir("atendido(s)" in resp.text, "lista da farmácia mostra o andamento da solicitação")
        ok_s2, id_s2 = _abrir_at({"prontuario": "7081", "sala": "26", "especialidade": "ORTOPEDIA",
                                           "data_procedimento": hoje_iso()}, "sala1")
        resp = cliente.post(f"/farmacia/atendimento/{id_s2}/finalizar-dispensa", data={}, follow_redirects=False)
        conferir("/finalizada" in resp.headers["location"], "sem solicitação, o finalizar segue como antes")
        resp = cliente.get(f"/procedimentos?data={hoje_iso()}&unidade=HEMODINAMICA - PDT&so_opme=1")
        conferir(f"/sala-procedimento/atendimento/{id_s}/solicitacao" in resp.text and "solicitação: " in resp.text,
                 "Procedimentos: botão Solicitar OPME e andamento da solicitação na lista")
        resp = cliente.post("/procedimentos", data={
            "prontuario": "997", "local": "BLOCO CIRURGICO|05", "especialidade": "UROLOGIA",
            "data_procedimento": hoje_iso(), "seguir": "solicitar"}, follow_redirects=False)
        conferir(resp.status_code == 303 and resp.headers["location"].endswith("/solicitacao"),
                 "Procedimentos: abrir e ir direto para a solicitação")

        print("== Sala já aberta: material dispensado depois não trava; ciência ao finalizar")
        from src.providers.implementations.opme.services import dispensacoes as _d3, fechamento as _f3
        from src.providers.implementations.opme.domain import EM_SALA as _ES3
        cadastrar("COMPL A", "7896660000073", "LCA", "01/01/2031", qtd="2", codigo_aghu="88010", farmacia="BLOCO CIRURGICO")
        cadastrar("COMPL B", "7896660000080", "LCB", "01/01/2031", qtd="2", codigo_aghu="88011", farmacia="BLOCO CIRURGICO")
        ok_c3, id_c3 = _abrir_at({"prontuario": "7090", "sala": "27", "especialidade": "ORTOPEDIA",
                                           "data_procedimento": hoje_iso()}, "sala1")
        fluxo.bipar(operacao="dispensar_sala", codigo="7896660000073", usuario="farm1", id_atendimento=id_c3)
        r = fluxo.bipar(operacao="registrar_uso", codigo="7896660000073", usuario="sala1", id_atendimento=id_c3)
        conferir(not r["ok"] and r.get("dispensacao_pendente"), "1ª entrega ainda trava até a sala receber")
        dd = _d3.pendente_do_atendimento(id_c3)
        _d3.confirmar(id_dispensacao=dd["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
        fluxo.bipar(operacao="dispensar_sala", codigo="7896660000080", usuario="farm1", id_atendimento=id_c3)
        r = fluxo.bipar(operacao="registrar_uso", codigo="7896660000073", usuario="sala1", id_atendimento=id_c3)
        conferir(r["ok"] and len(_d3.complemento_pendente(id_c3)) == 1,
                 "sala já aberta: material pedido a mais não trava a bipagem", r.get("mensagem"))
        resp = cliente.get(f"/bipagem/registrar_uso?atendimento={id_c3}")
        conferir("BIPAGEM BLOQUEADA" not in resp.text and "dispensou mais 1 item" in resp.text,
                 "tela de uso avisa do complemento sem bloquear")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_c3}/concluir")
        conferir('name="ciencia_complemento"' in resp.text and "COMPL B" in resp.text,
                 "concluir mostra os itens a dar ciência")
        enf3 = {"username": "sala1", "nome": "Enf. Ana Souza", "papel": "sala-procedimento"}
        ok, msg, _ = _f3.finalizar_uso(id_c3, enf3)
        conferir(not ok and "ciência" in msg, "finalizar sem a ciência é recusado", msg)
        ok, msg, _ = _f3.finalizar_uso(id_c3, enf3, ciencia_complemento=True)
        u_b = db.escalar("SELECT id_unidade FROM unidades WHERE codigo_barras='7896660000080' AND id_atendimento=?", (id_c3,))
        ev = db.consultar_um("SELECT * FROM eventos WHERE tipo='confirmar_recebimento_sala' AND id_unidade=?", (u_b,))
        conferir(ok and not _d3.pendente_do_atendimento(id_c3) and ev and ev["usuario"] == "sala1"
                 and "Ciência" in (ev["observacao"] or ""),
                 "com a ciência: itens recebidos pelo usuário logado e utilizados finalizados", msg)

        print("== Não utilizados: a sala pode bipar o que está devolvendo")
        cadastrar("SOBRA A", "7896660000097", "LSA", "01/01/2031", qtd="1", codigo_aghu="88020", farmacia="BLOCO CIRURGICO")
        cadastrar("SOBRA B", "7896660000103", "LSB", "01/01/2031", qtd="1", codigo_aghu="88021", farmacia="BLOCO CIRURGICO")
        ok_sb, id_sb = _abrir_at({"prontuario": "7095", "sala": "29", "especialidade": "ORTOPEDIA",
                                           "data_procedimento": hoje_iso()}, "sala1")
        for c in ("7896660000097", "7896660000103"):
            fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1", id_atendimento=id_sb)
        dsb = _d3.pendente_do_atendimento(id_sb)
        _d3.confirmar(id_dispensacao=dsb["id_dispensacao"], usuario_sala="sala2", senha="Senha2026")
        resp = cliente.get(f"/sala-procedimento/atendimento/{id_sb}/concluir")
        conferir('value="bipando"' in resp.text and 'id="bip-sobras"' in resp.text,
                 "finalizar: opção de devolver pela lista ou bipando")
        r_ok = cliente.get(f"/sala-procedimento/atendimento/{id_sb}/sobras/identificar", params={"codigo": "7896660000097"}).json()
        r_no = cliente.get(f"/sala-procedimento/atendimento/{id_sb}/sobras/identificar", params={"codigo": "123"}).json()
        conferir(r_ok["ok"] and r_ok["chaves"][0].startswith("u:") and not r_no["ok"],
                 "bip acha o não utilizado e recusa o que não é deste paciente")
        resp = cliente.post(f"/sala-procedimento/atendimento/{id_sb}/finalizar-uso",
                            data={"modo_sobras": "bipando", "devolver": r_ok["chaves"][0]}, follow_redirects=True)
        from src.providers.implementations.opme.services import devolucoes as _dv2
        dvb = _dv2.pendente_do_atendimento(id_sb)
        itens_dv = _dv2.itens(dvb["id_devolucao"], so_pendentes=True) if dvb else []
        conferir(len(itens_dv) == 1 and itens_dv[0]["xProd"] == "SOBRA A"
                 and _f3.sobras(id_sb)["total"] == 1 and "não foram devolvidos" in resp.text,
                 "só o bipado vai para a farmácia; o não bipado fica com o paciente (pendência)")

        print("== Envio do almoxarifado para a farmácia (lista ou bipando)")
        from src.providers.implementations.opme.services import remessas as _rm
        cadastrar("ENVIO A", "7896660000110", "LEA1", "01/01/2031", qtd="3", codigo_aghu="88030")
        cadastrar("ENVIO A", "7896660000110", "LEA2", "01/06/2031", qtd="1", codigo_aghu="88030")
        cadastrar("ENVIO B", "7896660000127", "LEB", "01/01/2031", qtd="2", codigo_aghu="88031")
        ok_e, id_ae = _abrir_at({"prontuario": "7100", "unidade": "HEMODINAMICA - PDT", "sala": "02",
                                          "especialidade": "CARDIO", "data_procedimento": hoje_iso()}, "sala1")
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000127", usuario="farm1", id_atendimento=id_ae,
                        farmacia="HEMODINAMICA - PDT")
        conferir(not r["ok"] and "ALMOXARIFADO" in r["mensagem"], "farmácia não dispensa o que está no almoxarifado", r.get("mensagem"))
        resp = cliente.post("/almoxarifado/envios/novo", data={"farmacia": "HEMODINAMICA - PDT"}, follow_redirects=False)
        id_rem = resp.headers["location"].rsplit("/", 1)[1]
        r = cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7896660000110", "quantidade": 2}).json()
        conferir(not r["ok"] and r.get("escolher") and len(r["opcoes"]) == 2, "envio: mesmo código com 2 lotes pede a escolha")
        g1 = next(o["grupo"] for o in r["opcoes"] if o["lote"] == "LEA1")
        r = cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7896660000110", "quantidade": 2, "grupo": g1}).json()
        r2 = cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7896660000127", "quantidade": 2}).json()
        conferir(r["ok"] and r2["ok"] and r2["total"] == 4
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE status='transito_farmacia' AND farmacia='HEMODINAMICA - PDT'") == 4,
                 "envio: bipado sai do almoxarifado e fica em trânsito para a farmácia escolhida")
        r3 = cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7896660000127", "quantidade": 1}).json()
        conferir(not r3["ok"], "não envia mais do que há no estoque do almoxarifado", r3.get("mensagem"))
        conferir(r2.get("lista") and r2["item"]["aghu"] == "88031", "bip do envio devolve a lista atualizada e o item lido")
        rx = cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7890000099999", "quantidade": 1}).json()
        conferir(not rx["ok"] and rx.get("nao_cadastrado") and "não está cadastrado" in rx["mensagem"],
                 "envio: código desconhecido avisa MATERIAL NÃO CADASTRADO", rx.get("mensagem"))
        resp = cliente.get(f"/almoxarifado/envio/{id_rem}")
        conferir('id="codigo"' in resp.text and "Consultar antes de bipar" in resp.text and "data-tirar" in resp.text,
                 "tela do envio igual à dispensação (campo grande, lista ao vivo, consulta)")
        resp = cliente.get(f"/almoxarifado/envio/{id_rem}", params={"busca": "ENVIO A"})
        conferir("LEA2" in resp.text, "consulta mostra o que há no almoxarifado")
        it_rm = _rm.buscar(id_rem)["pendentes"][0]
        rt = cliente.post(f"/almoxarifado/envio/item/{it_rm['id_item']}/tirar").json()
        conferir(rt["ok"] and len(rt["lista"]) >= 1, "tirar pela tela devolve a lista")
        it_rm = _rm.buscar(id_rem)["pendentes"][0]
        cliente.post(f"/almoxarifado/envio/item/{it_rm['id_item']}/remover")
        conferir(len(_rm.buscar(id_rem)["pendentes"]) == 2 and fluxo.buscar_unidade(it_rm["id_unidade"])["status"] == EM_ESTOQUE_RECEBIMENTO,
                 "tirar do envio devolve ao almoxarifado")
        cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7896660000127", "quantidade": 1})
        cliente.post(f"/almoxarifado/envio/{id_rem}/bipar", json={"codigo": "7896660000127", "quantidade": 1})
        cliente.post(f"/almoxarifado/envio/{id_rem}/finalizar", data={"observacao": "reposição"})
        conferir(_rm.buscar(id_rem)["status"] == "enviada" and _rm.contar_a_receber("HEMODINAMICA - PDT") >= 1,
                 "envio finalizado aparece para a farmácia conferir")
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000127", usuario="farm1", id_atendimento=id_ae,
                        farmacia="HEMODINAMICA - PDT")
        conferir(not r["ok"] and "ciência" in r["mensagem"], "antes da ciência a farmácia não dispensa", r.get("mensagem"))
        cliente.post("/farmacia/unidade", data={"unidade": "HEMODINAMICA - PDT"})
        resp = cliente.get("/farmacia/recebimentos")
        conferir(id_rem in resp.text and "Conferir e dar ciência" in resp.text, "farmácia vê o envio para conferir")
        resp = cliente.get(f"/farmacia/recebimento/{id_rem}")
        conferir('value="bipando"' in resp.text and 'name="recebido"' in resp.text, "conferência: pela lista ou bipando")
        pend = _rm.buscar(id_rem)["pendentes"]
        nao = pend[0]
        recebidos = [str(i["id_item"]) for i in pend if i["id_item"] != nao["id_item"]]
        cliente.post(f"/farmacia/recebimento/{id_rem}/conferir", data={"modo": "lista", "recebido": recebidos})
        rem = _rm.buscar(id_rem)
        conferir(rem["status"] == "conferida"
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE status='em_estoque_farmacia' AND farmacia='HEMODINAMICA - PDT' AND codigo_aghu IN ('88030','88031')") == 3
                 and len(_rm.pendencias("HEMODINAMICA - PDT")) == 1,
                 "ciência pela lista: recebidos entram no estoque da farmácia; desmarcado vira pendência")
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000110", usuario="farm1", id_atendimento=id_ae,
                        farmacia="BLOCO CIRURGICO")
        conferir(not r["ok"], "a farmácia do Bloco não dispensa o estoque da Hemodinâmica", r.get("mensagem"))
        r = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000110", usuario="farm1", id_atendimento=id_ae,
                        farmacia="HEMODINAMICA - PDT")
        conferir(r["ok"], "a farmácia da Hemodinâmica dispensa do estoque dela", r.get("mensagem"))
        resp = cliente.get("/almoxarifado/envios")
        conferir("Não recebidos pela farmácia — tratar" in resp.text, "almoxarifado vê a pendência para tratar")
        resp = cliente.post(f"/almoxarifado/envio/item/{_rm.pendencias()[0]['id_item']}/tratar",
                            data={"acao": "divergencia", "motivo": ""}, follow_redirects=True)
        conferir(len(_rm.pendencias()) == 1, "divergência exige motivo")
        cliente.post(f"/farmacia/recebimento/item/{_rm.pendencias()[0]['id_item']}/recebi")
        conferir(not _rm.pendencias() and fluxo.buscar_unidade(nao["id_unidade"])["status"] == "em_estoque_farmacia",
                 "farmácia marca 'recebi' depois: entra no estoque dela")
        print("== Sala confere a dispensação: lista ou bipando")
        from src.providers.implementations.opme.services import dispensacoes as _dp
        for _ in range(2):
            rr = fluxo.bipar(operacao="dispensar_sala", codigo="7896660000110", usuario="farm1", id_atendimento=id_ae,
                             farmacia="HEMODINAMICA - PDT")
        dpe = _dp.pendente_do_atendimento(id_ae)
        pend_e = _dp.itens(dpe["id_dispensacao"], so_pendentes=True)
        resp = cliente.get(f"/dispensacoes/{dpe['id_dispensacao']}")
        conferir('value="bipando"' in resp.text and 'name="recebido"' in resp.text and "Dar ciência do recebimento" in resp.text,
                 "confirmar na sala: conferir pela lista ou bipando, igual ao envio do almoxarifado")
        idf = cliente.get(f"/dispensacoes/{dpe['id_dispensacao']}/identificar", params={"codigo": "7896660000110"}).json()
        conferir(idf["ok"] and len(idf["itens"]) == len(pend_e), "bip na conferência acha o item da dispensação")
        falta = pend_e[0]
        recebe = [str(i["id_item"]) for i in pend_e[1:]]
        _abrir_sala_da_disp(dpe['id_dispensacao'])
        resp = cliente.post(f"/dispensacoes/{dpe['id_dispensacao']}/confirmar",
                            data={"modo": "lista", "recebido": recebe, "usuario_sala": "sala2", "senha": "Senha2026"},
                            follow_redirects=True)
        # v18.4.3: o não recebido fica "aguardando conferência da farmácia" (fora do
        # estoque disponível) até a farmácia localizar; localizado, volta ao estoque.
        conferir(fluxo.buscar_unidade(falta["id_unidade"])["status"] == "nao_recebido_conferir"
                 and all(fluxo.buscar_unidade(i["id_unidade"])["status"] == "em_sala" for i in pend_e[1:])
                 and db.escalar("SELECT situacao FROM dispensacao_itens WHERE id_item = ?", (falta["id_item"],)) == "nao_recebido",
                 "desmarcado não entra na sala: fica aguardando a conferência da farmácia")
        from src.providers.implementations.opme.services import dispensacoes as _disp
        _r_nr = _disp.tratar_nao_recebido(falta["id_unidade"], "localizado", "admin", farmacia=fluxo.buscar_unidade(falta["id_unidade"])["farmacia"])
        conferir(_r_nr[0]
                 and fluxo.buscar_unidade(falta["id_unidade"])["status"] == "em_estoque_farmacia",
                 "farmácia localiza o não recebido: volta ao estoque")

        # 2º envio, conferido bipando
        cadastrar("ENVIO C", "7896660000134", "LEC", "01/01/2031", qtd="2", codigo_aghu="88032")
        ok, id_rem2 = _rm.abrir("BLOCO CIRURGICO", "almox")
        _rm.bipar(id_rem2, "7896660000134", "almox", 2)
        _rm.finalizar_envio(id_rem2, "almox")
        idf = cliente.get(f"/farmacia/recebimento/{id_rem2}/identificar", params={"codigo": "7896660000134"}).json()
        cliente.post(f"/farmacia/recebimento/{id_rem2}/conferir", data={"modo": "bipando", "bipado": [str(idf["itens"][0])],
                                                                         "recebido": [str(i["id_item"]) for i in _rm.buscar(id_rem2)["pendentes"]]})
        conferir(idf["ok"] and len(_rm.pendencias("BLOCO CIRURGICO")) == 1
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_aghu='88032' AND status='em_estoque_farmacia' AND farmacia='BLOCO CIRURGICO'") == 1,
                 "ciência bipando: só o bipado entra; o não bipado vira pendência")
        pid = _rm.pendencias("BLOCO CIRURGICO")[0]["id_item"]
        cliente.post(f"/almoxarifado/envio/item/{pid}/tratar", data={"acao": "voltou_almoxarifado"})
        conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_aghu='88032' AND status='em_estoque_recebimento' AND farmacia IS NULL") == 1,
                 "almoxarifado registra 'voltou ao almoxarifado'")

        print("== Indicadores retirados: completude do cadastro e rastreabilidade do implante")
        from src.providers.implementations.opme.indicadores import CATALOGO as _CAT
        textos_ind = "".join(cliente.get(pg).text for pg in ("/indicadores", "/indicadores/qualidade", "/indicadores/metas"))
        conferir("completude_cadastro" not in _CAT and "rastreabilidade_uso" not in _CAT
                 and "Completude do cadastro" not in textos_ind and "Rastreabilidade do implante" not in textos_ind,
                 "indicadores retirados não aparecem nas telas nem nas metas")

        print("== Caixa de consignado na SALA pelo dia")
        from src.providers.implementations.opme.services import caixas_sala as _cs, caixas_consignado as _cc, alertas as _al
        SALA_U = {"username": "sala1", "nome": "Sala Um", "papel": "sala-procedimento"}
        FARM_U = {"username": "farm1", "nome": "Farmacêutica Um", "papel": "farmacia"}
        ok, _, cxt = _cc.criar({"nome": "Caixa do dia", "fornecedor": "TURNOMED"}, "farm1")
        cadastrar("STENT TURNO", "7897770000011", "LT1", "01/01/2031", qtd="3", farmacia="HEMODINAMICA - PDT")
        for _ in range(3):
            caixas.adicionar_item(cxt, "7897770000011", "farm1")
        def _at(pront, unidade, sala):
            ok, ida = _abrir_at({"prontuario": pront, "unidade": unidade, "sala": sala,
                                          "especialidade": "CARDIO", "data_procedimento": hoje_iso()}, "sala1")
            return ida
        at_a, at_b = _at("9301", "HEMODINAMICA - PDT", "01"), _at("9302", "HEMODINAMICA - PDT", "01")
        at_c = _at("9303", "BLOCO CIRURGICO", "02")
        ok, msg, idt = _cs.enviar(cxt, "HEMODINAMICA - PDT", "01", "farm1")
        conferir(ok and db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status='transito_sala' AND id_atendimento IS NULL", (cxt,)) == 3,
                 "farmácia envia a caixa para a sala (sem paciente)", msg)
        ok2, msg2, _ = _cs.enviar(cxt, "BLOCO CIRURGICO", "02", "farm1")
        conferir(not ok2 and "voltar à farmácia" in msg2, "caixa fora da farmácia não vai para outra sala", msg2)
        r = fluxo.bipar(operacao="registrar_uso", codigo=cxt, usuario="sala1", id_atendimento=at_a)
        conferir(not r["ok"] and "ciência" in r["mensagem"], "antes da ciência a caixa não é usada", r.get("mensagem"))
        ok, msg = _cs.receber([idt], FARM_U)
        conferir(not ok, "farmácia não dá ciência pela sala")
        ok, msg = _cs.receber([idt], SALA_U)
        conferir(ok and _cs.buscar(idt)["status"] == "na_sala"
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status='em_sala'", (cxt,)) == 3,
                 "sala dá ciência da CAIXA (não item a item)", msg)
        r1 = fluxo.bipar(operacao="registrar_uso", codigo="7897770000011", usuario="sala1", caixa=cxt, id_atendimento=at_a)
        r2 = fluxo.bipar(operacao="registrar_uso", codigo="7897770000011", usuario="sala1", caixa=cxt, id_atendimento=at_b)
        conferir(r1["ok"] and r2["ok"] and not any("outro paciente" in x for x in r1.get("alertas", []))
                 and _cs.buscar(idt)["usados"] == 2 and _cs.buscar(idt)["restam"] == 1,
                 "a caixa serve vários procedimentos da mesma sala no dia", (r1.get("mensagem"), r2.get("mensagem")))
        ok_x, msg_x = fluxo.excluir_bip(r2["item"]["id_unidade"], at_b, "sala1", "Bipado em duplicidade")
        u_x = fluxo.buscar_unidade(r2["item"]["id_unidade"])
        conferir(ok_x and u_x["status"] == "em_sala" and not u_x["id_atendimento"] and u_x["id_caixa"] == cxt
                 and _cs.buscar(idt)["restam"] == 2, "bip excluído: o item volta para a caixa na sala, sem paciente", msg_x)
        r2 = fluxo.bipar(operacao="registrar_uso", codigo="7897770000011", usuario="sala1", caixa=cxt, id_atendimento=at_b)
        r = fluxo.bipar(operacao="registrar_uso", codigo=cxt, usuario="sala1", id_atendimento=at_c)
        conferir(not r["ok"] and "Só pode ser usada" in r["mensagem"], "outra sala não usa a caixa", r.get("mensagem"))
        r = _cc.devolver(id_caixa=cxt, id_atendimento=at_a, quantidade="1", usuario="sala1")
        conferir(not r["ok"] and "pelo dia" in r["mensagem"], "caixa do dia não é devolvida pelo paciente")
        r = caixas.adicionar_item(cxt, "7897770000011", "farm1")
        conferir(not r["ok"], "não se põe item na caixa enquanto ela está na sala")
        cliente.post("/sala-procedimento/unidade", data={"unidade": "HEMODINAMICA - PDT"})
        resp = cliente.get("/sala-procedimento/caixas")
        conferir(resp.status_code == 200 and cxt in resp.text and "Devolver à farmácia" in resp.text, "tela Caixas na sala")
        cliente.post(f"/sala-procedimento/caixas/{idt}/devolver")
        conferir(_cs.buscar(idt)["status"] == "devolvida", "sala devolve a caixa à farmácia")
        r = fluxo.bipar(operacao="registrar_uso", codigo=cxt, usuario="sala1", id_atendimento=at_a)
        conferir(not r["ok"] and "devolvida" in r["mensagem"], "caixa devolvida não é mais usada")
        resp = cliente.get(f"/farmacia/caixas-sala/{idt}")
        conferir("Conferir a caixa" in resp.text and "Confere — voltaram os 1" in resp.text, "farmácia vê quantos devem voltar")
        cliente.post(f"/farmacia/caixas-sala/{idt}/conferir", data={"modo": "confere"})
        tt = _cs.buscar(idt)
        conferir(tt["status"] == "conferida" and tt["qtd_voltou"] == 1 and tt["qtd_usada"] == 2
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status='em_estoque_farmacia'", (cxt,)) == 1,
                 "conferência da caixa num clique: o que voltou entra no estoque da farmácia")
        cadastrar("STENT TURNO", "7897770000011", "LT1", "01/01/2031", qtd="1", farmacia="HEMODINAMICA - PDT")
        r = caixas.adicionar_item(cxt, "7897770000011", "farm1")
        conferir(r["ok"] and _cc.esperado(cxt) == 2, "depois da conferência a farmácia reabastece a caixa")
        ok, _, idt2 = _cs.enviar(cxt, "HEMODINAMICA - PDT", "01", "farm1")
        _cs.receber([idt2], SALA_U); _cs.devolver(idt2, SALA_U)
        um = [i["id_unidade"] for i in _cs.itens(idt2)][:1]
        ok, msg = _cs.conferir(idt2, FARM_U, set(um))
        conferir(ok and _cs.buscar(idt2)["status"] == "divergente" and _cc.buscar(cxt)["bloqueada"]
                 and _cs.buscar(idt2)["faltaram"] == 1, "faltou item no retorno: caixa bloqueada com pendência", msg)
        r = fluxo.bipar(operacao="registrar_uso", codigo=cxt, usuario="sala1", id_atendimento=at_c)
        conferir(not r["ok"], "pendência: outra sala continua sem usar")
        r = fluxo.bipar(operacao="registrar_uso", codigo="7897770000011", usuario="sala1", caixa=cxt, id_atendimento=at_b)
        conferir(r["ok"] and _cs.buscar(idt2)["faltaram"] == 0, "a sala bipa o uso esquecido no paciente certo", r.get("mensagem"))
        ok, msg = _cc.conferir(cxt, "farm1", "pendência resolvida: uso bipado", [])
        conferir(ok and not _cc.buscar(cxt)["bloqueada"] and _cs.buscar(idt2)["status"] == "conferida",
                 "farmácia confere e libera: pendência encerrada")
        # Confirmar recebimento (por paciente): a caixa aparece como UMA linha
        ok, _, cxp = _cc.criar({"nome": "Caixa paciente", "fornecedor": "PACMED"}, "farm1")
        cadastrar("PARAFUSO PAC", "7897770000028", "LP1", "01/01/2031", qtd="2", farmacia="HEMODINAMICA - PDT")
        caixas.adicionar_item(cxp, "7897770000028", "farm1"); caixas.adicionar_item(cxp, "7897770000028", "farm1")
        at_p = _at("9304", "HEMODINAMICA - PDT", "01")
        fluxo.bipar(operacao="dispensar_sala", codigo=cxp, usuario="farm1", id_atendimento=at_p, farmacia="HEMODINAMICA - PDT")
        dpp = dispensacoes.pendente_do_atendimento(at_p)["id_dispensacao"]
        resp = cliente.get(f"/dispensacoes/{dpp}")
        conferir(f"Caixa {cxp}" in resp.text and resp.text.count('name="recebido" value=') == 1,
                 "confirmar recebimento: a caixa é uma linha só")
        ids_p = [str(i["id_item"]) for i in dispensacoes.pendentes_do_atendimento(at_p)]
        _abrir_sala_da_disp(dpp)
        cliente.post(f"/dispensacoes/{dpp}/confirmar", data={"modo": "lista", "recebido": ",".join(ids_p)})
        conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE id_caixa=? AND status='em_sala'", (cxp,)) == 2,
                 "ciência da caixa marca todos os itens dela")

        print("== Relatório de movimentações de dispensa")
        from src.providers.implementations.opme.services import rel_dispensas as _rd
        todas_m = _rd.movimentacoes(hoje_iso(), hoje_iso())
        env_h = _rd.movimentacoes(hoje_iso(), hoje_iso(), "envios", "HEMODINAMICA - PDT")
        disp_m = _rd.movimentacoes(hoje_iso(), hoje_iso(), "dispensacoes")
        conferir(env_h and all(l["tipo"].startswith("Almox") and "Hemodinâmica" in l["destino"] for l in env_h)
                 and disp_m and all(l["tipo"].startswith("Farm") for l in disp_m)
                 and len(todas_m) == len(_rd.movimentacoes(hoje_iso(), hoje_iso(), "envios")) + len(disp_m),
                 "relatório junta envios do almoxarifado e dispensações das farmácias, com filtros")
        conferir(any(l["situacao"] == "retirado do envio" and not l["conta"] for l in env_h)
                 and _rd.resumo(todas_m)["total"] == sum(1 for l in todas_m if l["conta"]),
                 "item retirado aparece mas não conta no total")
        conferir(not _rd.movimentacoes("2000-01-01", "2000-01-02"), "período sem movimentação: vazio")
        conferir(any(l["tipo"].startswith("Farmácia → Sala (caixa") for l in todas_m), "relatório inclui a caixa do dia")
        resp = cliente.get("/consultas/dispensas", params={"inicio": hoje_iso(), "fim": hoje_iso()})
        conferir(resp.status_code == 200 and "Movimentações de dispensa" in resp.text and "Por material (código AGHU)" in resp.text,
                 "tela do relatório de dispensas")
        resp = cliente.get("/consultas/dispensas", params={"inicio": hoje_iso(), "fim": hoje_iso(), "exportar": "csv"})
        conferir(resp.status_code == 200 and "Descrição AGHU" in resp.content.decode("utf-8-sig"), "exporta planilha")
        resp = cliente.get("/consultas/dispensas", params={"inicio": hoje_iso(), "fim": hoje_iso(), "exportar": "pdf"})
        conferir(resp.status_code == 200 and resp.content.startswith(b"%PDF"), "baixa PDF")
        conferir("/consultas/dispensas" in cliente.get("/almoxarifado").text
                 and "/consultas/dispensas" in cliente.get("/farmacia").text, "atalho no almoxarifado e na farmácia")

        print("== Estoque das farmácias e inventário por local")
        resp = cliente.get("/farmacia/estoque", params={"farmacia": "HEMODINAMICA - PDT"})
        conferir(resp.status_code == 200 and "ENVIO A" in resp.text and "Farmácia do Bloco Cirúrgico (" in resp.text,
                 "farmácia vê o próprio estoque e alterna entre Bloco e Hemodinâmica")
        resp = cliente.get("/farmacia")
        conferir("Estoque da farmácia" in resp.text, "hub da farmácia tem o card do estoque")
        resp = cliente.get("/consultas/itens", params={"status": "em_estoque_farmacia:HEMODINAMICA - PDT"})
        conferir("ENVIO A" in resp.text and "Farmácia da Hemodinâmica" in resp.text and "ENVIO C" not in resp.text,
                 "consulta filtra o estoque de uma farmácia e mostra onde está")
        resp = cliente.get("/")
        conferir("Em estoque (Farmácia do Bloco Cirúrgico)" in resp.text and "Em estoque (Farmácia da Hemodinâmica)" in resp.text,
                 "painel separa o estoque das duas farmácias")
        from src.providers.implementations.opme.services import inventario as _inv
        resp = cliente.get("/inventario")
        conferir(set(_inv.locais()) == {"almoxarifado", "BLOCO CIRURGICO", "HEMODINAMICA - PDT"}
                 and "Farmácia da Hemodinâmica —" in resp.text, "inventário: almoxarifado e cada farmácia")
        ok_i, _m, id_inv = _inv.abrir("HEMODINAMICA - PDT", "farm1")
        r_i = _inv.bipar(id_inv, "7896660000110", "farm1")
        r_j = _inv.bipar(id_inv, "7896660000134", "farm1")
        conferir(ok_i and r_i.get("situacao") == "confere" and r_j.get("situacao") == "local_divergente",
                 "contagem da farmácia confere o estoque dela e aponta o que é de outro local", (r_i.get("situacao"), r_j.get("situacao")))
        _inv.encerrar(id_inv, "farm1")

        print("== Planilha de lotes do AGHU: pendente até bipar")
        from src.providers.implementations.opme.services import carga_planilha as _cp
        csv_txt = ("\ufeffalmoxarifado;cod_material;material;fornecedor;marca_comercial;lote;serie;data_validade;"
                   "qtde_disponivel_lote;qtde_disponivel_total;extraido_em\r\n"
                   "OPME - UACE;97941;LAMINA SHAVER TESTE;FORNECEDOR NACIONAL EM GERAL;VOLMED;00022531;;28/05/2027;3;100;x\r\n"
                   "OPME - UACE;97941;LAMINA SHAVER TESTE;FORNECEDOR NACIONAL EM GERAL;RAZEK;000529;;07/01/2029;2;100;x\r\n"
                   "OPME - UACE;88047;CIMENTO TESTE;FORNECEDOR NACIONAL EM GERAL;BIOMET;C77;;01/01/3000;1;1;x\r\n"
                   "OPME - UACE;88047;CIMENTO TESTE;FORNECEDOR NACIONAL EM GERAL;BIOMET;C77;;01/01/3000;1;1;y\r\n")
        antes_est = db.escalar("SELECT COUNT(*) FROM unidades WHERE origem='planilha'")
        resp = cliente.post("/almoxarifado/planilha", files={"arquivo": ("lotes.csv", csv_txt.encode("utf-8"), "text/csv")},
                            follow_redirects=True)
        conferir("3 lote(s), 6 unidade(s) pendentes" in resp.text and _cp.total_pendente() == 6
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE origem='planilha'") == antes_est,
                 "importa a planilha: tudo pendente, nada entra no estoque antes do bip")
        resp = cliente.post("/almoxarifado/planilha", files={"arquivo": ("lotes.csv", csv_txt.encode("utf-8"), "text/csv")},
                            follow_redirects=True)
        conferir(_cp.total_pendente() == 6 and "já tinham sido importadas" in resp.text, "reimportar não duplica")
        conferir("data-bipar=" in resp.text and "MATERIAL ESCOLHIDO" in resp.text,
                 "tela: escolhe o material (Bipar) e depois bipa, com quantidade")
        linhas_p = {(l["codigo_aghu"], l["lote"]): l for l in _cp.pendentes()}
        conferir(linhas_p[("88047", "C77")]["dVal"] is None and linhas_p[("97941", "00022531")]["marca"] == "VOLMED",
                 "01/01/3000 = sem validade; fornecedor/marca = marca comercial")
        r = cliente.post("/almoxarifado/planilha/bipar", json={"codigo": "7899990000011"}).json()
        conferir(not r["ok"] and r.get("codigo_novo"), "código desconhecido: pede para escolher a linha")
        l_vol = linhas_p[("97941", "00022531")]
        r = cliente.post("/almoxarifado/planilha/bipar", json={"codigo": "7899990000011", "id_item": l_vol["id_item"]}).json()
        u = db.consultar_um("SELECT * FROM unidades WHERE origem='planilha' AND nLote='00022531'")
        conferir(r["ok"] and r["restante"] == 2 and u and u["codigo_barras"] == "7899990000011"
                 and u["fornecedor"] == "VOLMED" and u["xProd"] == "LAMINA SHAVER TESTE" and u["status"] == EM_ESTOQUE_RECEBIMENTO,
                 "escolhida a linha, o bip dá entrada com o código lido, descrição = material, fornecedor = marca", str(r))
        conferir(u["tipo_entrada"] == "aquisicao_propria", "planilha: sem escolher, entra como aquisição própria")
        r = cliente.post("/almoxarifado/planilha/bipar", json={"codigo": "7899990000011", "quantidade": 2,
                                                               "tipo_entrada": "consignado"}).json()
        conferir(db.escalar("SELECT COUNT(*) FROM unidades WHERE origem='planilha' AND nLote='00022531' AND tipo_entrada='consignado'") == 2,
                 "planilha: pode escolher consignado/doação na entrada")
        conferir(r["ok"] and r["restante"] == 0 and r["quantidade"] == 2
                 and db.escalar("SELECT situacao FROM carga_itens WHERE id_item=?", (l_vol["id_item"],)) == "concluido",
                 "mesmo código de novo vai sozinho para o lote; com quantidade, completa o lote e sai do pendente")
        r = cliente.post("/almoxarifado/planilha/bipar", json={"codigo": "(01)07899990000028(17)290107(10)000529"}).json()
        conferir(r["ok"] and r["item"]["lote"] == "000529", "etiqueta GS1: acha a linha pelo lote", str(r))
        l_cim = linhas_p[("88047", "C77")]
        resp = cliente.post(f"/almoxarifado/planilha/{l_cim['id_item']}/sem-codigo", data={"quantidade": "1"}, follow_redirects=False)
        resp_etq = cliente.get(resp.headers["location"])
        conferir("tam-pequena" in resp_etq.text and "sem_legenda=1" in resp_etq.text and "Pequena (5 × 2,5 cm)" in resp_etq.text,
                 "etiqueta pequena (5 × 2,5 cm) por padrão, com opção média")
        conferir(resp.status_code == 303 and "/almoxarifado/etiquetas" in resp.headers["location"]
                 and db.escalar("SELECT COUNT(*) FROM unidades WHERE origem='planilha' AND codigo_aghu='88047'") == 1,
                 "sem código de barras: entra com código interno e vai para a etiqueta")
        l_raz = linhas_p[("97941", "000529")]
        resp = cliente.post(f"/almoxarifado/planilha/{l_raz['id_item']}/retirar", data={"motivo": "não encontrado"}, follow_redirects=True)
        conferir(_cp.total_pendente() == 0, "linha retirada sai dos pendentes")
        resp = cliente.get("/almoxarifado")
        conferir("Planilha de lotes do AGHU" in resp.text, "Almoxarifado tem o atalho para a planilha")
    return _fim()


def _fim() -> int:
    print("=" * 60)
    if FALHAS:
        print(f"  {len(FALHAS)} de {TOTAL} verificações FALHARAM:")
        for f in FALHAS:
            print(f"   - {f}")
        return 1
    print(f"  Todas as {TOTAL} verificações passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
