# tests/test_v18_43_3_bateria_de_etiquetas.py
"""v18.43.3: bateria de bipagem com etiquetas de formatos diferentes.

Camila (20/11/2026): "faça diferentes testes com diferentes etiquetas bipadas:
(01)7898716350358(17)300126(10)260126(21)561193(11)260126 /
010789933020454617291119300121S0000019783 / 78987057600380 e várias outras."

Cada caso percorre a vida do material: cadastro no almoxarifado → envio para a
farmácia → recebimento → dispensação para o paciente → registro de uso. Em
todas as etapas se bipa o MESMO texto, e o que se cobra é sempre o mesmo: achar
a unidade certa, sem pedir para escolher lote.

Casos (todos tirados do banco do HC-UFPE):
  1. GS1 com parênteses, com nº de série   (prótese valvular Braile)
  2. GS1 sem parênteses, com nº de série   (a mesma, noutro leitor)
  3. GS1 cru com (30) e série alfanumérica (etiqueta que a Camila mandou)
  4. GTIN-14 de 14 dígitos começando com 7 (tela de polipropileno)
  5. GTIN-13                                (o sistema completa com zero)
  6. GTIN-14 de caixa, começando com 1      (fio guia)
  7. Etiqueta secundária: validade + lote   (carga de grampeador)
  8. Código com caractere do leitor         (set de mangueiras, "10706;26")
  9. Código interno AGHU(LOTE)              ("sem código de barras")
 10. QR do manual do fabricante             (PERMACATH kffmed)
 11. Etiqueta inteira gravada como código   (cadastro antigo das próteses)
 12. GS1 com lote alfanumérico e validade   (clip de ligadura)
"""
import pytest

from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import (
    EM_ESTOQUE_FARMACIA, EM_SALA, TRANSITO_FARMACIA, UTILIZADO)
from src.providers.implementations.opme.services import (
    atendimentos, dispensacoes, estoque, fluxo, remessas)
from src.providers.implementations.opme.utils import hoje_iso

FARM = "HEMODINAMICA - PDT"

# (apelido, código cadastrado, o que se bipa, aghu, lote, validade, série)
CASOS = [
    ("GS1 com parênteses + série",
     "07898716359931", "(01)7898716359931(17)300126(10)260126(21)931001193(11)260126",
     "931001", "260126", "2030-01-26", "561193"),
    ("GS1 sem parênteses + série",
     "07898716350327", "010789871635032717300401100104262156255011260402",
     "931002", "010426", "2030-04-01", "562550"),
    ("GS1 cru com (30) e série alfanumérica",
     "07899330204546", "010789933020454617291119300121S0000019783",
     "931003", "S0000019783", "2029-11-19", "S0000019783"),
    ("GTIN-14 de 14 dígitos",
     "78987057600380", "78987057600380", "931004", "11002022", "2031-06-30", ""),
    ("GTIN-13 (sistema completa com zero)",
     "07898705760038", "7898705760038", "931005", "11002023", "2031-06-30", ""),
    ("GTIN-14 de caixa (começa com 1)",
     "16949450423790", "16949450423790", "931006", "SP1024120503", "2029-12-05", ""),
    ("etiqueta secundária: validade + lote",
     "1727101810MK19A1", "1727101810MK19A1", "931007", "MK19A1", "2027-10-18", ""),
    ("código com caractere do leitor",
     "10716;26", "10716;26", "931008", "1071626", "2028-06-30", ""),
    ("código interno AGHU(LOTE)",
     "931009(BLDP-14528)", "931009(BLDP-14528)", "931009", "BLDP-14528", "2027-09-30", ""),
    ("QR do manual do fabricante",
     "httpsÇ;;kffmed.com;docu;IDU-INNOVALD-Esp.Port..pdf",
     "httpsÇ;;kffmed.com;docu;IDU-INNOVALD-Esp.Port..pdf",
     "931010", "BLDP14528B13092024", "2027-09-30", ""),
    ("etiqueta inteira gravada como código",
     "(01)7908952474272(17)291019(10)00027492", "(01)7908952474272(17)291019(10)00027492",
     "931011", "00027492", "2029-10-19", ""),
    ("GS1 com lote alfanumérico",
     "04026704725325", "(01)04026704725325(10)73H2501032(17)300907",
     "931012", "73H2501032", "2030-09-07", ""),
]
APELIDOS = [c[0] for c in CASOS]


def _cadastrar(caso, quantidade=2):
    apelido, codigo, _bipa, aghu, lote, val, serie = caso
    ok, m = estoque.cadastrar_manual({
        "xProd": f"MATERIAL DE TESTE — {apelido}", "codigo_barras": codigo,
        "codigo_aghu": aghu, "fornecedor": "F", "marca_fabricante": "M",
        "nLote": lote, "dVal": val, "numero_serie": serie,
        "quantidade": str(quantidade), "tipo_entrada": "aquisicao_propria"}, "almox")
    assert ok, f"{apelido}: {m}"
    # o cadastro normaliza o código (a 18.40 extrai o GTIN da etiqueta); aqui se
    # força o estado real do banco dela, inclusive os cadastros antigos
    db.executar("UPDATE unidades SET codigo_barras = ? WHERE codigo_aghu = ?", (codigo, aghu))
    return aghu


@pytest.mark.parametrize("caso", CASOS, ids=APELIDOS)
def test_a_vida_inteira_do_material(client, caso):
    apelido, _codigo, bipa, aghu, lote, _val, _serie = caso
    _cadastrar(caso)

    # 1) almoxarifado → farmácia
    ok, id_rem = remessas.abrir(FARM, "almox")
    assert ok, id_rem
    r = remessas.bipar(id_rem, bipa, "almox", ciencia_validade=True)
    assert r["ok"], f"{apelido} — envio: {r.get('titulo') or r.get('mensagem')}"
    assert not r.get("escolher"), f"{apelido} — envio pediu para escolher lote"
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_aghu = ? AND status = ?",
                      (aghu, TRANSITO_FARMACIA)) == 1

    ok, msg = remessas.finalizar_envio(id_rem, "almox")
    assert ok, msg
    pendentes = {str(i["id_item"]) for i in remessas.buscar(id_rem)["pendentes"]}
    ok, msg = remessas.conferir(id_rem, pendentes, {"username": "farm1", "nome": "Farmácia"})
    assert ok, f"{apelido} — recebimento: {msg}"
    assert db.escalar("SELECT COUNT(*) FROM unidades WHERE codigo_aghu = ? AND status = ?",
                      (aghu, EM_ESTOQUE_FARMACIA)) == 1

    # 2) farmácia → sala
    ok, ida = atendimentos.abrir({"prontuario": f"93{aghu[-4:]}", "paciente": "PACIENTE DA BATERIA",
                                  "unidade": "HEMODINAMICA - PDT", "sala": aghu[-3:],
                                  "especialidade": "HEMODINAMICA",
                                  "data_procedimento": hoje_iso()}, "admin")
    assert ok, ida
    r = fluxo.bipar(operacao="dispensar_sala", codigo=bipa, usuario="farm1",
                    id_atendimento=ida, farmacia=FARM, ciencia_validade=True)
    assert r["ok"], f"{apelido} — dispensação: {r.get('mensagem')}"
    unidade = db.consultar_um("SELECT * FROM unidades WHERE id_atendimento = ?", (ida,))
    assert unidade and unidade["codigo_aghu"] == aghu, f"{apelido} — pegou outro material"
    assert unidade["nLote"] == lote, f"{apelido} — pegou outro lote"
    assert unidade["status"] in (EM_SALA, "transito_sala")

    # 3) a sala dá ciência do que recebeu e registra o uso
    for d in dispensacoes.pendentes_do_atendimento(ida):
        ok, msg = dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"],
                                         logado={"username": "sala1", "nome": "Sala", "papel": "sala-procedimento"})
        assert ok, f"{apelido} — ciência da sala: {msg}"
    ok, msg = atendimentos.abrir_sala(ida, "sala1")
    assert ok, f"{apelido} — abrir sala: {msg}"
    r = fluxo.bipar(operacao="registrar_uso", codigo=bipa, usuario="sala1",
                    id_atendimento=ida, farmacia=FARM)
    assert r["ok"], f"{apelido} — uso: {r.get('mensagem')}"
    assert db.escalar("SELECT status FROM unidades WHERE id_unidade = ?",
                      (unidade["id_unidade"],)) == UTILIZADO


@pytest.mark.parametrize("caso", CASOS, ids=APELIDOS)
def test_a_busca_acha_pelo_que_foi_bipado(client, caso):
    apelido, codigo, bipa, aghu, lote, val, serie = caso
    aghu = aghu + "9"          # AGHU próprio: não conta as unidades do teste de cima
    caso = (apelido, codigo, bipa, aghu, lote, val, serie)
    _cadastrar(caso, quantidade=3)
    achadas = [u for u in estoque.buscar_unidades(bipa, "ativos") if u["codigo_aghu"] == aghu]
    assert len(achadas) == 3, f"{apelido}: achou {len(achadas)} de 3"
