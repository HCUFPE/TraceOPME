"""v17 (out/2026) — fechamento do procedimento em duas mãos.

1. A SALA, dentro da sala, clica em "Finalizar registro de uso e devoluções". O que a
   farmácia dispensou para o paciente e não foi usado vira, sozinho, a lista de
   não utilizados — ninguém bipa a devolução.
2. A FARMÁCIA confere a lista, desmarca o que não voltou e dá ciência (usuário
   logado). Voltou tudo → o procedimento encerra.
3. O que a farmácia desmarcou continua com o paciente e a sala recebe um alerta
   para conferir: se foi usado, bipa no prontuário; se está na sala, devolve.
   A farmácia marca "Recebi de volta" e é ela quem conclui o procedimento.
"""

from __future__ import annotations

from .. import busca, db
from ..erros import ErroDeNegocio
from ..config import UNIDADES_ATIVAS
from ..domain import EM_SALA, TRANSITO_SALA, UTILIZADO
from ..utils import texto
from . import atendimentos, caixas_consignado, devolucoes, dispensacoes, entrega_paciente


def _na_devolucao_pendente() -> str:
    return """EXISTS (SELECT 1 FROM devolucao_itens di JOIN devolucoes dv ON dv.id_devolucao = di.id_devolucao
                     WHERE di.situacao = 'pendente' AND dv.status = 'pendente'
                       AND (di.id_unidade = u.id_unidade
                            OR (di.tipo = 'caixa' AND UPPER(di.id_caixa) = UPPER(COALESCE(u.id_caixa,''))
                                AND dv.id_atendimento = u.id_atendimento)))"""


def sobras(id_atendimento: str) -> dict:
    """O que foi dispensado para o paciente, não foi usado e não está numa lista
    de não utilizados aguardando a farmácia. Itens soltos e caixas (pela caixa)."""
    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                   u.id_caixa, u.status, u.codigo_barras, u.numero_serie
            FROM unidades u
            WHERE u.id_atendimento = ? AND u.status IN ('{TRANSITO_SALA}', '{EM_SALA}')
              AND NOT {_na_devolucao_pendente()}
            ORDER BY u.id_caixa, u.xProd""", (texto(id_atendimento),))
    itens = [l for l in linhas if not texto(l["id_caixa"])]
    caixas: dict[str, dict] = {}
    for l in linhas:
        if texto(l["id_caixa"]):
            c = caixas.setdefault(l["id_caixa"], {"id_caixa": l["id_caixa"], "qtd": 0, "itens": []})
            c["qtd"] += 1
            c["itens"].append(l)
    for c in caixas.values():
        info = caixas_consignado.buscar(c["id_caixa"]) or {}
        c["nome"] = info.get("nome") or ""
    return {"itens": itens, "caixas": list(caixas.values()),
            "total": len(itens) + sum(c["qtd"] for c in caixas.values())}


def identificar_sobra(id_atendimento: str, codigo: str) -> dict:
    """Sala conferindo bipando: quais não utilizados o código lido atende
    (código de barras/etiqueta GS1, nº de série, ID da unidade ou código da caixa)."""
    from .. import gs1
    from ..utils import normalizar_codigo
    bruto = texto(codigo)
    if not bruto:
        return {"ok": False, "mensagem": "Código vazio."}
    lido = {bruto.upper(), texto(normalizar_codigo(bruto)).upper()}
    etiqueta = busca.interpretar(bruto)
    resto = sobras(id_atendimento)
    chaves = [f"c:{c['id_caixa'].upper()}" for c in resto["caixas"] if c["id_caixa"].upper() in lido]
    candidatos = []
    for i in resto["itens"]:
        cods = {texto(i["codigo_barras"]).upper(), texto(normalizar_codigo(i["codigo_barras"] or "")).upper(),
                texto(i["numero_serie"]).upper(), texto(i["id_unidade"]).upper()} - {""}
        if cods & lido:
            candidatos.append(i)
    # Etiqueta GS1 com lote: prefere a unidade daquele lote.
    if etiqueta and etiqueta.get("lote") and candidatos:
        do_lote = [i for i in candidatos if gs1._confere(i["nLote"], etiqueta["lote"], etiqueta.get("lote_ate_o_fim"))]
        candidatos = do_lote or candidatos
    chaves += [f"u:{i['id_unidade']}" for i in candidatos]
    if not chaves:
        return {"ok": False, "mensagem": f"O código {bruto} não está entre os não utilizados deste paciente."}
    return {"ok": True, "chaves": chaves}


def finalizado(atendimento: dict | None) -> bool:
    return bool(atendimento and texto(atendimento.get("uso_finalizado_em")))


def finalizar_uso(id_atendimento: str, usuario: dict,
                  ciencia_complemento: bool = False,
                  devolver: set | None = None) -> tuple[bool, str, bool]:
    """`devolver`: conferência bipando na sala — só o que foi bipado ("u:<id_unidade>"
    ou "c:<id_caixa>") vai para a lista da farmácia; o resto fica com o paciente
    (pendência da sala). Sem `devolver` (pela lista), vai tudo, como antes."""
    """A sala finaliza os materiais utilizados. Devolve (ok, mensagem, encerrado)."""
    at = atendimentos.buscar(id_atendimento)
    if not at:
        return False, "Atendimento não encontrado.", False
    if at["status"] != "aberto":
        return False, "Este atendimento já está encerrado.", False
    if finalizado(at):
        # v18.18: finalizar de novo quando chegou material DEPOIS da finalização
        # (pedido extra no meio do procedimento). Sem isso a sala ficava sem
        # caminho nenhum: não finalizava, e a ciência do que acabou de chegar
        # — que é parte da finalização — não tinha como ser dada.
        if not dispensacoes.complemento_pendente(id_atendimento) and not sobras(id_atendimento)["total"]:
            return False, ("Os materiais utilizados deste prontuário já foram finalizados e não há "
                           "material novo para fechar."), False
    complemento = dispensacoes.complemento_pendente(id_atendimento)
    if complemento:
        if not ciencia_complemento:
            return False, (f"A farmácia dispensou mais {len(complemento)} item(ns) para este paciente depois "
                           "que a sala já estava aberta. Marque a ciência desses itens para finalizar."), False
        ok_c, msg_c = dispensacoes.dar_ciencia_complemento(id_atendimento, usuario)
        if not ok_c:
            return False, msg_c, False
    travas = dispensacoes.bloqueio_do_prontuario(id_atendimento)
    if travas:
        qtd = sum(t["qtd"] for t in travas)
        return False, (f"A farmácia dispensou {qtd} item(ns) para este paciente e o recebimento "
                       "ainda não foi confirmado. Confirme o recebimento antes de finalizar."), False
    sem_ciencia = entrega_paciente.pendentes_de_ciencia(id_atendimento)
    if sem_ciencia:
        return False, ("Antes de finalizar, dê ciência da entrega da caixa ao paciente: "
                       + ", ".join(f"{i['xProd']} (AGHU {i['codigo_aghu']})" for i in sem_ciencia)
                       + "."), False
    resto = sobras(id_atendimento)
    nao_bipados = 0
    if devolver is not None:
        todos = resto["total"]
        resto = {"itens": [i for i in resto["itens"] if f"u:{i['id_unidade']}" in devolver],
                 "caixas": [c for c in resto["caixas"] if f"c:{c['id_caixa'].upper()}" in devolver]}
        resto["total"] = len(resto["itens"]) + sum(c["qtd"] for c in resto["caixas"])
        nao_bipados = todos - resto["total"]
    nome = usuario.get("nome") or usuario["username"]
    agora = db.agora()
    try:
        _gravar_finalizacao(id_atendimento, usuario, nome, agora, resto, devolver, refazendo=finalizado(at))
    except ErroDeNegocio as recusa:
        return False, str(recusa), False
    if nao_bipados:
        return True, (f"Sala liberada — aguardando conferência da farmácia. {resto['total']} material(is) "
                      f"registrado(s) como pendente(s) de devolução: encaminhe-os fisicamente à farmácia. "
                      f"{nao_bipados} material(is) não foram devolvidos e continuam com o paciente: "
                      "confira (se foi usado, bipe o uso; se está na sala, leve à farmácia)."), False
    if resto["total"]:
        return True, (f"Sala liberada — aguardando conferência da farmácia. {resto['total']} material(is) "
                      "registrado(s) como pendente(s) de devolução: encaminhe-os fisicamente à farmácia para "
                      "conferência e confirmação do recebimento."), False
    # v18.18: a finalização NÃO encerra mais o atendimento, mesmo sem nada sobrando.
    # Quem fecha é a farmácia (regra da v18.13). Encerrar aqui travava o caso
    # mais comum do dia: o médico pede um material extra logo depois de a sala
    # finalizar — com o atendimento fechado, a farmácia não conseguia nem
    # dispensar, nem a sala dar ciência ou bipar.
    return True, ("Registro de uso finalizado. Nada ficou sobrando — a farmácia conclui o "
                  "procedimento. Se chegar material extra, pode receber e bipar normalmente: "
                  "a sala só fecha quando a farmácia concluir."), False


def _gravar_finalizacao(id_atendimento, usuario, nome, agora, resto, devolver, refazendo=False) -> None:
    """v18.4.1: grava a finalização numa transação só, e só se ninguém finalizou antes.

    Duas finalizações ao mesmo tempo (duplo clique, duas abas) liam "não
    finalizado" fora da transação e as duas gravavam — devolução duplicada. Agora
    o UPDATE só vale se o atendimento ainda não foi finalizado; a segunda recusa."""
    with db.transacao() as conn:
        # v18.18: refinalizar é permitido quando chegou material depois (`refazendo`),
        # mas a trava contra duplo clique continua valendo para a 1ª finalização.
        if refazendo:
            cur = conn.execute("UPDATE atendimentos SET uso_finalizado_em = ?, uso_finalizado_por = ? "
                               "WHERE id_atendimento = ? AND status = 'aberto'",
                               (agora, usuario["username"], id_atendimento))
        else:
            cur = conn.execute("UPDATE atendimentos SET uso_finalizado_em = ?, uso_finalizado_por = ? "
                               "WHERE id_atendimento = ? AND status = 'aberto' "
                               "AND COALESCE(uso_finalizado_em, '') = ''",
                               (agora, usuario["username"], id_atendimento))
        if cur.rowcount != 1:
            raise ErroDeNegocio("Os materiais utilizados deste prontuário já foram finalizados.")

        usados = conn.execute("SELECT COUNT(*) FROM unidades WHERE id_atendimento = ? AND status = ?",
                              (id_atendimento, UTILIZADO)).fetchone()[0]
        db.registrar_evento(
            conn, tipo="uso_finalizado", id_atendimento=id_atendimento, usuario=usuario["username"],
            observacao=(f"Materiais utilizados finalizados por {nome}: {usados} usado(s); "
                        f"{resto['total']} não utilizado(s) na lista para a farmácia."))
        if resto["total"]:
            id_dev = devolucoes._abrir_ou_pegar(conn, id_atendimento, usuario["username"], nome)
            for i in resto["itens"]:
                # nunca duas linhas pendentes da mesma unidade
                conn.execute(
                    """INSERT INTO devolucao_itens (id_devolucao, tipo, id_unidade, devolvido_por,
                                                    bipado_por, bipado_em)
                       SELECT ?,'item',?,?,?,? WHERE NOT EXISTS (
                           SELECT 1 FROM devolucao_itens WHERE id_unidade = ? AND situacao = 'pendente')""",
                    (id_dev, i["id_unidade"], nome, usuario["username"], agora, i["id_unidade"]))
            for c in resto["caixas"]:
                conn.execute(
                    """INSERT INTO devolucao_itens (id_devolucao, tipo, id_caixa, quantidade,
                                                    devolvido_por, bipado_por, bipado_em)
                       VALUES (?,'caixa',?,?,?,?,?)""",
                    (id_dev, c["id_caixa"], c["qtd"], nome, usuario["username"], agora))
            db.registrar_evento(
                conn, tipo="lista_nao_utilizados", id_atendimento=id_atendimento,
                usuario=usuario["username"], devolvido_por=nome,
                observacao=(("Devolução conferida pela sala: " if devolver is not None else
                             "Lista automática ao finalizar os utilizados: ") + f"{len(resto['itens'])} item(ns)"
                            + (f" e {len(resto['caixas'])} caixa(s)" if resto["caixas"] else "")
                            + "; aguardando a ciência da farmácia."))


def tem_devolucao_pendente(id_atendimento: str) -> bool:
    dev = devolucoes.pendente_do_atendimento(id_atendimento)
    return bool(dev and devolucoes.itens(dev["id_devolucao"], so_pendentes=True))


def pendencias(id_atendimento: str) -> dict:
    """Depois da ciência: o que a farmácia não recebeu e ainda está com o paciente."""
    at = atendimentos.buscar(id_atendimento)
    if not finalizado(at) or at["status"] != "aberto":
        return {"itens": [], "caixas": [], "total": 0}
    return sobras(id_atendimento)


def encerrar_se_completo(id_atendimento: str, usuario: str) -> bool:
    at = atendimentos.buscar(id_atendimento)
    if not finalizado(at) or at["status"] != "aberto":
        return False
    if tem_devolucao_pendente(id_atendimento) or sobras(id_atendimento)["total"]:
        return False
    ok, _ = atendimentos.encerrar(id_atendimento, usuario)
    return ok


def receber_pendencia(id_atendimento: str, quem: dict, id_unidade: str = "",
                      id_caixa: str = "") -> tuple[bool, str]:
    """A farmácia recebeu de volta um item (ou caixa) que tinha desmarcado."""
    if tem_devolucao_pendente(id_atendimento):
        return False, "Dê ciência da lista de não utilizados deste procedimento primeiro."
    resto = pendencias(id_atendimento)
    nome = quem.get("nome") or quem["username"]
    agora = db.agora()
    with db.transacao() as conn:
        if id_unidade:
            if not any(i["id_unidade"] == id_unidade for i in resto["itens"]):
                return False, "Este item não está pendente neste procedimento."
            id_dev = devolucoes._abrir_ou_pegar(conn, id_atendimento, quem["username"], "sala (pendência)")
            conn.execute("""INSERT INTO devolucao_itens (id_devolucao, tipo, id_unidade, devolvido_por,
                                                         bipado_por, bipado_em) VALUES (?,'item',?,?,?,?)""",
                         (id_dev, id_unidade, "sala (pendência)", quem["username"], agora))
        else:
            caixa = next((c for c in resto["caixas"] if c["id_caixa"].upper() == texto(id_caixa).upper()), None)
            if not caixa:
                return False, "Esta caixa não está pendente neste procedimento."
            id_dev = devolucoes._abrir_ou_pegar(conn, id_atendimento, quem["username"], "sala (pendência)")
            conn.execute("""INSERT INTO devolucao_itens (id_devolucao, tipo, id_caixa, quantidade,
                                                         devolvido_por, bipado_por, bipado_em)
                            VALUES (?,'caixa',?,?,?,?,?)""",
                         (id_dev, caixa["id_caixa"], caixas_consignado.esperado(caixa["id_caixa"]),
                          "sala (pendência)", quem["username"], agora))
    ok, msg = devolucoes.confirmar(id_devolucao=id_dev, operador=quem["username"], responsavel=quem,
                                   encerrar_auto=False,
                                   observacao=f"Recebido de volta depois da conferência da sala ({nome}).")
    return ok, ("Recebido de volta. " + msg) if ok else msg


def concluir(id_atendimento: str, quem: dict) -> tuple[bool, str]:
    """A farmácia conclui o procedimento quando não sobrou pendência."""
    at = atendimentos.buscar(id_atendimento)
    if not at or at["status"] != "aberto":
        return False, "Este atendimento não está aberto."
    if not finalizado(at):
        return False, "A sala ainda não finalizou os materiais utilizados."
    if tem_devolucao_pendente(id_atendimento):
        return False, "Dê ciência da lista de não utilizados primeiro."
    resto = sobras(id_atendimento)
    if resto["total"]:
        return False, (f"Ainda há {resto['total']} item(ns) com o paciente sem uso nem devolução. "
                       "Aguarde a sala conferir (bipar o uso) ou marque “Recebi de volta”.")
    return atendimentos.encerrar(id_atendimento, quem["username"])


def a_concluir(unidade: str = "") -> list[dict]:
    """Procedimentos com os utilizados finalizados e ainda abertos (para a farmácia)."""
    params: list = list(UNIDADES_ATIVAS)
    filtro = ""
    if texto(unidade):
        filtro = "AND a.unidade = ?"
        params.append(texto(unidade))
    lista = db.consultar(
        f"""SELECT a.id_atendimento, a.prontuario, a.paciente, a.unidade, a.sala, a.data_procedimento,
                   a.uso_finalizado_em, a.uso_finalizado_por,
                   (SELECT COUNT(*) FROM unidades u WHERE u.id_atendimento = a.id_atendimento
                      AND u.status = '{UTILIZADO}') AS usados
            FROM atendimentos a
            WHERE a.status = 'aberto' AND COALESCE(a.uso_finalizado_em,'') <> ''
              AND a.unidade IN ({','.join('?' for _ in UNIDADES_ATIVAS)}) {filtro}
            ORDER BY a.uso_finalizado_em""", tuple(params))
    for l in lista:
        dev = devolucoes.pendente_do_atendimento(l["id_atendimento"])
        l["id_devolucao"] = dev["id_devolucao"] if dev else ""
        l["a_conferir"] = len(devolucoes.itens(dev["id_devolucao"], so_pendentes=True)) if dev else 0
        l["pendentes"] = 0 if l["a_conferir"] else sobras(l["id_atendimento"])["total"]
    return lista


def pendencias_da_sala(unidade: str = "") -> list[dict]:
    """Para o alerta da sala: o que a farmácia não recebeu de volta."""
    return [l for l in a_concluir(unidade) if not l["a_conferir"] and l["pendentes"]]
