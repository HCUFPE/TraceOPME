# tests/test_v18_29_tag_opme_solicitado.py
"""v18.29: a lista da sala mostra quais procedimentos já têm OPME solicitado.

Pedido da Camila (18/11/2026): na tela "Atendimentos" da sala de procedimento,
uma etiqueta dizendo que aquele procedimento tem OPME solicitado — a coluna
"OPME pedido" só trazia o texto que vem do AGHU e ficava "—" mesmo com pedido
feito no TraceOPME.
"""
from src.providers.implementations.opme.services import atendimentos, solicitacoes
from src.providers.implementations.opme.utils import hoje_iso


def _atendimento(prontuario, sala):
    ok, ida = atendimentos.abrir({"prontuario": prontuario, "unidade": "BLOCO CIRURGICO", "sala": sala,
                                  "especialidade": "ORTOPEDIA", "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    return ida


def _lista(client, headers):
    r = client.get("/api/sala-procedimento/atendimentos",
                   params={"data": hoje_iso(), "unidade": "BLOCO CIRURGICO", "so_opme": 0},
                   headers=headers)
    assert r.status_code == 200
    return r.json()["dados"]


def test_a_lista_diz_quem_tem_pedido_e_quanto_falta(client, admin_headers):
    com_pedido = _atendimento("9940100", "91")
    sem_pedido = _atendimento("9940200", "92")
    ok, msg = solicitacoes.adicionar_avulso(com_pedido, "87994", 3,
                                            "COIL EMBOLIZANTE TAM. 10mm", "sala1")
    assert ok, msg

    d = _lista(client, admin_headers)
    resumo = d["solicitacoes"]
    assert com_pedido in resumo
    assert resumo[com_pedido]["linhas"] == 1
    assert resumo[com_pedido]["atendidas"] == 0
    assert resumo[com_pedido]["faltando"] == 1
    assert sem_pedido not in resumo          # sem pedido, nada de etiqueta


def test_o_resumo_acompanha_o_que_a_farmacia_ja_atendeu(client, admin_headers):
    from src.providers.implementations.opme import db
    from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
    from src.providers.implementations.opme.services import estoque, fluxo
    ida = _atendimento("9940300", "93")
    assert solicitacoes.adicionar_avulso(ida, "87994", 1, "COIL EMBOLIZANTE", "sala1")[0]
    ok, m = estoque.cadastrar_manual({"xProd": "COIL EMBOLIZANTE", "codigo_barras": "7891190000015",
                                      "codigo_aghu": "87994", "fornecedor": "F", "marca_fabricante": "M",
                                      "nLote": "TAG1", "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = 'TAG1'",
                (EM_ESTOQUE_FARMACIA,))
    assert atendimentos.abrir_sala(ida, "admin")[0]
    assert fluxo.bipar(operacao="dispensar_sala", codigo="7891190000015", usuario="farm1",
                       id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]

    resumo = _lista(client, admin_headers)["solicitacoes"][ida]
    assert resumo["atendidas"] == 1 and resumo["faltando"] == 0


def test_a_tela_usa_o_resumo(client):
    tela = open("frontend/src/views/opme/SalaAtendimentos.vue", encoding="utf-8").read()
    assert "OPME solicitado" in tela
    assert "d.solicitacoes?.[a.id_atendimento]" in tela


# ------------------------------------------------------------------ v18.30
def _lista_mostrar(client, headers, mostrar):
    r = client.get("/api/sala-procedimento/atendimentos",
                   params={"data": hoje_iso(), "unidade": "BLOCO CIRURGICO", "mostrar": mostrar},
                   headers=headers)
    assert r.status_code == 200
    return r.json()["dados"]


def test_filtro_so_com_pedido_pendente(client, admin_headers):
    from src.providers.implementations.opme import db
    from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
    from src.providers.implementations.opme.services import estoque, fluxo
    pendente = _atendimento("9941100", "94")
    atendido = _atendimento("9941200", "95")
    sem_pedido = _atendimento("9941300", "96")
    assert solicitacoes.adicionar_avulso(pendente, "87994", 2, "COIL PENDENTE", "sala1")[0]
    assert solicitacoes.adicionar_avulso(atendido, "87994", 1, "COIL ATENDIDO", "sala1")[0]

    ok, m = estoque.cadastrar_manual({"xProd": "COIL ATENDIDO", "codigo_barras": "7891190000022",
                                      "codigo_aghu": "87994", "fornecedor": "F", "marca_fabricante": "M",
                                      "nLote": "TAG2", "dVal": "2031-01-01", "quantidade": "1",
                                      "tipo_entrada": "aquisicao_propria"}, "admin")
    assert ok, m
    db.executar("UPDATE unidades SET status = ?, farmacia = 'BLOCO CIRURGICO' WHERE nLote = 'TAG2'",
                (EM_ESTOQUE_FARMACIA,))
    assert atendimentos.abrir_sala(atendido, "admin")[0]
    assert fluxo.bipar(operacao="dispensar_sala", codigo="7891190000022", usuario="farm1",
                       id_atendimento=atendido, farmacia="BLOCO CIRURGICO")["ok"]

    d = _lista_mostrar(client, admin_headers, "pendente")
    ids = {a["id_atendimento"] for a in d["atendimentos"]}
    assert pendente in ids                    # ainda espera material
    assert atendido not in ids                # pedido já atendido
    assert sem_pedido not in ids              # nem pedido tem
    assert d["mostrar"] == "pendente"

    todas = {a["id_atendimento"] for a in _lista_mostrar(client, admin_headers, "todas")["atendimentos"]}
    assert {pendente, atendido, sem_pedido} <= todas


def test_links_antigos_continuam_valendo(client, admin_headers):
    """Sem 'mostrar' na URL, o so_opme de antes ainda manda."""
    r = client.get("/api/sala-procedimento/atendimentos",
                   params={"data": hoje_iso(), "unidade": "BLOCO CIRURGICO", "so_opme": 0},
                   headers=admin_headers)
    assert r.json()["dados"]["mostrar"] == "todas"
    r = client.get("/api/sala-procedimento/atendimentos",
                   params={"data": hoje_iso(), "unidade": "BLOCO CIRURGICO", "so_opme": 1},
                   headers=admin_headers)
    assert r.json()["dados"]["mostrar"] == "opme"
