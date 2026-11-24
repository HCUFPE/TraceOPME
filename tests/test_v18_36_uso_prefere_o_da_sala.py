# tests/test_v18_36_uso_prefere_o_da_sala.py
"""v18.36: ao bipar o uso, vale o material que já está na sala do paciente.

Caso real no banco do HC-UFPE (19/11/2026), prontuários 22280721 e 22176440:
a farmácia dispensou uma unidade do lote SP1024120503, a sala deu ciência e,
minutos depois, ao bipar o uso o sistema consumiu OUTRA unidade do mesmo lote —
uma parada no estoque do Bloco Cirúrgico, outra ainda no almoxarifado —,
gravando "saída sem dispensação". A unidade que estava na sala ficou presa em
`em_sala` e virou "1 para voltar" na devolução.

Lá a causa foi um cadastro com o GTIN da caixa (começa com 1) em vez do da peça
(começa com 0), que tirava a unidade certa da lista de candidatas. Mas a ordem
de preferência também estava errada: entre unidades elegíveis, a que está na
sala daquele paciente tem de vir na frente.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import (EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO,
                                                       EM_SALA, UTILIZADO)
from src.providers.implementations.opme.services import atendimentos, dispensacoes, estoque, fluxo
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
FARM = "BLOCO CIRURGICO"
COD = "06949450423790"
LOTE = "SP1024120503"


def _cad(quantidade):
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA HIDROFILICO DE 0,35", "codigo_barras": COD, "codigo_aghu": "92529",
        "fornecedor": "APT", "marca_fabricante": "APT", "nLote": LOTE, "dVal": "2027-12-04",
        "quantidade": str(quantidade), "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m


def _cenario():
    """1 unidade dispensada e com ciência na sala + outras paradas em estoques."""
    _cad(3)
    ids = [r["id_unidade"] for r in db.consultar(
        "SELECT id_unidade FROM unidades WHERE nLote = ? ORDER BY id_unidade", (LOTE,))][-3:]
    # a mais nova fica na farmácia (será a dispensada), as outras em outros estoques
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE id_unidade = ?",
                (EM_ESTOQUE_FARMACIA, FARM, ids[0]))
    db.executar("UPDATE unidades SET status = ?, farmacia = 'HEMODINAMICA - PDT' WHERE id_unidade = ?",
                (EM_ESTOQUE_FARMACIA, ids[1]))
    db.executar("UPDATE unidades SET status = ?, farmacia = NULL WHERE id_unidade = ?",
                (EM_ESTOQUE_RECEBIMENTO, ids[2]))
    ok, ida = atendimentos.abrir({"prontuario": "2228072", "unidade": FARM, "sala": "501",
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert atendimentos.abrir_sala(ida, "admin")[0]
    assert fluxo.bipar(operacao="dispensar_sala", codigo=COD, usuario="farm1",
                       id_atendimento=ida, farmacia=FARM)["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]
    na_sala = db.escalar("SELECT id_unidade FROM unidades WHERE nLote = ? AND status = ? "
                         "AND id_atendimento = ?", (LOTE, EM_SALA, ida))
    assert na_sala
    return ida, na_sala, ids


def test_o_bipe_usa_a_unidade_que_esta_na_sala(client):
    ida, na_sala, _ids = _cenario()
    r = fluxo.bipar(operacao="registrar_uso", codigo=COD, usuario="sala1", id_atendimento=ida)
    assert r["ok"], r.get("mensagem")
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?", (na_sala,)) == UTILIZADO


def test_nao_sobra_pendencia_de_devolucao(client):
    """Era isto que virava "1 para voltar" com o material já usado no paciente."""
    ida, na_sala, _ids = _cenario()
    assert fluxo.bipar(operacao="registrar_uso", codigo=COD, usuario="sala1",
                       id_atendimento=ida)["ok"]
    from src.providers.implementations.opme.services import fechamento
    assert fechamento.sobras(ida)["total"] == 0


def test_nao_grava_saida_sem_dispensacao(client):
    ida, na_sala, _ids = _cenario()
    assert fluxo.bipar(operacao="registrar_uso", codigo=COD, usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert db.escalar("""SELECT COUNT(*) FROM eventos WHERE id_atendimento = ?
                         AND tipo = 'saida_sem_dispensacao'""", (ida,)) == 0


def test_sem_material_na_sala_o_uso_direto_continua_valendo(client):
    """A sala ainda pode bipar material que não passou por dispensação."""
    cod_proprio = "06949450423799"
    ok, m = estoque.cadastrar_manual({
        "xProd": "FIO GUIA SO DESTE TESTE", "codigo_barras": cod_proprio, "codigo_aghu": "92528",
        "fornecedor": "APT", "marca_fabricante": "APT", "nLote": "SP-SO-DESTE-TESTE",
        "dVal": "2027-12-04", "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    ok, ida = atendimentos.abrir({"prontuario": "2228099", "unidade": FARM, "sala": "502",
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    db.executar("UPDATE atendimentos SET sala_aberta_em = NULL WHERE unidade = ? AND sala = '501'",
                (FARM,))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    r = fluxo.bipar(operacao="registrar_uso", codigo=cod_proprio, usuario="sala1",
                    id_atendimento=ida)
    assert r["ok"], r.get("mensagem")
    assert db.escalar("""SELECT COUNT(*) FROM eventos WHERE id_atendimento = ?
                         AND tipo = 'saida_sem_dispensacao'""", (ida,)) == 1
