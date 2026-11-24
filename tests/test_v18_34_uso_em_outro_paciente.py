# tests/test_v18_34_uso_em_outro_paciente.py
"""v18.34: material de um paciente bipado no prontuário de outro deixa rastro.

Achado na bateria do fechamento (18/11/2026): a farmácia dispensa para o
paciente A, a sala dá ciência e depois bipa o uso no prontuário B. O bip avisa
na tela — e está certo em não travar, porque na sala isso acontece —, mas
depois disso:
  - o item sumia da ficha de A (materiais(A) == []);
  - A finalizava com "nada ficou sobrando" e encerrava;
  - o histórico do item não dizia de onde ele tinha vindo.
Quem conferisse depois não tinha como saber o que foi feito do material
dispensado para A.
"""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA, UTILIZADO
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque,
                                                         fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso

SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}
FARM = "BLOCO CIRURGICO"
_n = [0]


def _material():
    _n[0] += 1
    cod, lote = f"78997{_n[0]:09d}", f"TRF{_n[0]}"
    ok, m = estoque.cadastrar_manual({
        "xProd": f"MATERIAL TRF {_n[0]}", "codigo_barras": cod, "codigo_aghu": "90119",
        "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
        "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = ? WHERE nLote = ?",
                (EM_ESTOQUE_FARMACIA, FARM, lote))
    return cod, lote


def _atendimento():
    _n[0] += 1
    ok, ida = atendimentos.abrir({"prontuario": f"88{_n[0]:05d}", "unidade": FARM,
                                  "sala": str(400 + _n[0]), "especialidade": "ORTOPEDIA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    assert atendimentos.abrir_sala(ida, "admin")[0]
    return ida


def _dispensar_com_ciencia(ida, cod):
    assert fluxo.bipar(operacao="dispensar_sala", codigo=cod, usuario="farm1",
                       id_atendimento=ida, farmacia=FARM)["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    assert dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA)[0]


def _transferir():
    """Dispensa para A, bipa o uso em B. Devolve (A, B, lote)."""
    a, b = _atendimento(), _atendimento()
    cod, lote = _material()
    _dispensar_com_ciencia(a, cod)
    r = fluxo.bipar(operacao="registrar_uso", codigo=cod, usuario="sala1", id_atendimento=b)
    assert r["ok"], r.get("mensagem")
    return a, b, lote, r


def test_o_bip_continua_funcionando_e_avisando(client):
    a, b, lote, r = _transferir()
    assert db.escalar("SELECT status FROM unidades WHERE nLote = ?", (lote,)) == UTILIZADO
    assert any("outro paciente" in al for al in r["alertas"]), r["alertas"]


def test_o_historico_diz_para_onde_foi_e_de_onde_veio(client):
    a, b, lote, _r = _transferir()
    eventos = db.consultar(
        """SELECT tipo, id_atendimento, COALESCE(observacao,'') obs FROM eventos
           WHERE id_unidade = (SELECT id_unidade FROM unidades WHERE nLote = ?)
           ORDER BY id_evento""", (lote,))
    saida = [e for e in eventos if e["tipo"] == "uso_em_outro_paciente"]
    assert saida, [e["tipo"] for e in eventos]
    assert saida[0]["id_atendimento"] == a            # registrado na origem
    assert atendimentos.buscar(b)["prontuario"] in saida[0]["obs"]

    uso = [e for e in eventos if e["tipo"] == "registrar_uso"][-1]
    assert uso["id_atendimento"] == b
    assert atendimentos.buscar(a)["prontuario"] in uso["obs"]


def test_a_ficha_do_paciente_de_origem_mostra_o_material(client, admin_headers):
    a, b, lote, _r = _transferir()
    linhas = atendimentos.materiais_usados_em_outro(a)
    assert [l["nLote"] for l in linhas] == [lote]
    assert linhas[0]["prontuario_destino"] == atendimentos.buscar(b)["prontuario"]
    assert linhas[0]["destino"] == b

    r = client.get(f"/api/sala-procedimento/atendimento/{a}", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()["dados"]
    assert [m["nLote"] for m in d["usados_em_outro"]] == [lote]


def test_o_paciente_de_destino_nao_mostra_nada_disso(client):
    a, b, lote, _r = _transferir()
    assert atendimentos.materiais_usados_em_outro(b) == []
    assert [m["nLote"] for m in atendimentos.materiais(b)] == [lote]


def test_a_origem_ainda_fecha_normalmente(client):
    """Não trava o fechamento: só deixa de ser um fechamento cego."""
    a, b, lote, _r = _transferir()
    ok, msg, _ = fechamento.finalizar_uso(a, SALA)
    assert ok, msg
    assert fechamento.concluir(a, SALA)[0]


def test_uso_normal_nao_gera_o_registro(client):
    ida = _atendimento()
    cod, lote = _material()
    _dispensar_com_ciencia(ida, cod)
    assert fluxo.bipar(operacao="registrar_uso", codigo=cod, usuario="sala1",
                       id_atendimento=ida)["ok"]
    assert atendimentos.materiais_usados_em_outro(ida) == []
    obs = db.escalar("""SELECT COALESCE(observacao,'') FROM eventos
                        WHERE id_unidade = (SELECT id_unidade FROM unidades WHERE nLote = ?)
                          AND tipo = 'registrar_uso'""", (lote,))
    assert "dispensado para o prontuário" not in obs
