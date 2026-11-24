"""Cenário da Camila: 10 + ciência, depois mais 2 sem ciência (1 usado, 1 não)."""
from src.providers.implementations.opme import db
from src.providers.implementations.opme.domain import EM_ESTOQUE_FARMACIA
from src.providers.implementations.opme.services import (atendimentos, dispensacoes, estoque,
                                                         fechamento, fluxo)
from src.providers.implementations.opme.utils import hoje_iso
SALA = {"username": "admin", "nome": "Administrador", "papel": "admin"}

def _cad(cod, lote):
    ok, m = estoque.cadastrar_manual({"xProd": f"MAT {lote}", "codigo_barras": cod, "codigo_aghu": "9600",
        "fornecedor": "F", "marca_fabricante": "M", "nLote": lote, "dVal": "2031-01-01",
        "quantidade": "1", "tipo_entrada": "aquisicao_propria"}, "admin"); assert ok, m
    db.executar("UPDATE unidades SET status=?, farmacia='BLOCO CIRURGICO' WHERE nLote=?", (EM_ESTOQUE_FARMACIA, lote))

def test_cenario(client):
    codigos = [f"789112000{n:04d}" for n in range(1, 13)]
    for n, c in enumerate(codigos, 1): _cad(c, f"CEN{n}")
    ok, ida = atendimentos.abrir({"prontuario":"9920100","unidade":"BLOCO CIRURGICO","sala":"47",
        "especialidade":"ORTOPEDIA","data_procedimento":hoje_iso()}, "admin"); assert ok
    assert atendimentos.abrir_sala(ida,"admin")[0]
    for c in codigos[:10]:
        assert fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1",
                           id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]
    d = dispensacoes.pendente_do_atendimento(ida)
    print("1) ciência dos 10:", dispensacoes.confirmar(id_dispensacao=d["id_dispensacao"], logado=SALA))
    for c in codigos[:6]:
        assert fluxo.bipar(operacao="registrar_uso", codigo=c, usuario="sala1", id_atendimento=ida)["ok"]
    # chegam mais 2, SEM ciência
    for c in codigos[10:]:
        assert fluxo.bipar(operacao="dispensar_sala", codigo=c, usuario="farm1",
                           id_atendimento=ida, farmacia="BLOCO CIRURGICO")["ok"]
    r = fluxo.bipar(operacao="registrar_uso", codigo=codigos[10], usuario="sala1", id_atendimento=ida)
    print("2) bipar o extra sem ciência:", r["ok"], r.get("mensagem","")[:90])
    comp = dispensacoes.complemento_pendente(ida)
    print("3) pendências de ciência ao finalizar:", len(comp),
          [(i.get("nLote"), i.get("situacao")) for i in comp])
    sob = fechamento.sobras(ida)
    print("4) sobras (voltam para a farmácia):", sob["total"], sorted(i["nLote"] for i in sob["itens"]))
    print("5) finalizar sem ciência:", fechamento.finalizar_uso(ida, SALA)[:2])
