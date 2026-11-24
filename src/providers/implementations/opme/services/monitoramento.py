"""Central de monitoramento das salas de procedimento (v18.1; etapas refeitas na v18.3).

Uma foto, em tempo real, de cada sala do dia. Nada aqui grava: tudo é lido do
que as outras telas registram.

Etapas de um procedimento (v18.3, definidas pela Camila):
    1. Sala aberta              — botão "Abrir sala" na ficha (ou, se ninguém
                                  clicou, a 1ª ciência/bip, marcada como automática)
    2. Ciência do material      — a sala confirmou o recebimento da dispensação
    3. Uso do material          — bips no paciente
    4. Uso e devoluções finalizados — a sala finalizou o registro de uso (sala liberada)
    5. Conferência da farmácia  — a farmácia deu ciência dos não utilizados
    6. Concluído                — a farmácia concluiu o procedimento
Pedido de OPME em aberto é ALERTA (não é etapa).

Sobreposição: depois que a sala finaliza, o procedimento sai da sala e fica
"na farmácia" (conferência). A sala fica livre para o próximo procedimento, e
o cartão mostra os dois: o que está na sala agora e o(s) que a farmácia ainda
está conferindo.
"""

from __future__ import annotations

from datetime import datetime

from .. import db
from ..config import UNIDADES_ATIVAS, rotulo_unidade, salas_da_unidade
from ..utils import texto

ETAPAS = [
    {"chave": "aberta", "rotulo": "Sala aberta"},
    {"chave": "ciencia", "rotulo": "Ciência do material"},
    {"chave": "em_uso", "rotulo": "Uso do material"},
    {"chave": "finalizado", "rotulo": "Uso e devoluções finalizados"},
    {"chave": "conferencia", "rotulo": "Conferência da farmácia"},
    {"chave": "concluido", "rotulo": "Concluído"},
]
ORDEM = {"agendado": 0, "aberta": 1, "ciencia": 2, "em_uso": 3, "aguardando_farmacia": 4, "conferido": 5,
         "concluido": 6, "cancelado": -1}
NA_SALA = ("aberta", "ciencia", "em_uso")
NA_FARMACIA = ("aguardando_farmacia", "conferido")
SITUACAO = {
    "livre": ("Sala livre", "cinza"),
    "agendado": ("Agendado", "azul-claro"),
    "aberta": ("Sala aberta", "azul"),
    "ciencia": ("Material recebido", "ciano"),
    "em_uso": ("Em uso — bipando", "verde"),
    "aguardando_farmacia": ("Sala liberada · farmácia conferindo", "roxo"),
    "conferido": ("Conferido — falta concluir", "roxo"),
    "livre_conferencia": ("Sala liberada · farmácia conferindo", "roxo"),
    "concluido": ("Concluído", "verde-escuro"),
    "cancelado": ("Cancelado", "cinza"),
}
MINUTOS_PEDIDO_ATRASADO = 30
MINUTOS_DISPENSA_SEM_CONFIRMAR = 30

# Um bip pode gerar mais de um evento (ex.: registrar_uso + saida_sem_dispensacao);
# a contagem de itens vem das unidades ligadas ao paciente, não dos eventos.
TIPOS_BIP = ("registrar_uso", "uso_nao_cadastrado")

ROTULO_EVENTO = {
    "sala_aberta": "Sala aberta",
    "solicitacao_opme": "Pediu OPME à farmácia",
    "dispensar_sala": "Farmácia dispensou para a sala",
    "confirmar_recebimento_sala": "Ciência do material recebido",
    "nao_recebido_sala": "Sala NÃO recebeu",
    "registrar_uso": "Bipado no paciente",
    "selecao_manual": "Selecionado pelo código AGHU",
    "uso_nao_cadastrado": "Uso de material não cadastrado",
    "avaria_sinalizada": "⚠ Problema sinalizado no material",
    "estornar_uso": "Uso estornado",
    "excluir_bip": "Bip excluído",
    "uso_finalizado": "Registro de uso e devoluções finalizado",
    "lista_nao_utilizados": "Lista de não utilizados para a farmácia",
    "devolver_nao_utilizado": "Farmácia conferiu os não utilizados",
    "atendimento_encerrado": "Farmácia concluiu o procedimento",
    "atendimento_cancelado": "Procedimento cancelado",
    "atendimento_reaberto": "Procedimento reaberto",
    "chamado_sala": "Chamado para o QG",
    "chamado_direcionado": "QG direcionou o chamado",
    "chamado_atendido": "Chamado atendido",
    "chamado_cancelado": "Chamado cancelado",
}


def _dt(valor) -> datetime | None:
    v = texto(valor)
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace(" ", "T")[:19])
    except ValueError:
        return None


def _hora(valor) -> str:
    d = _dt(valor)
    return d.strftime("%H:%M") if d else ""


def _minutos(desde, ate: datetime) -> int | None:
    d = _dt(desde)
    return max(0, int((ate - d).total_seconds() // 60)) if d else None


def _duracao(minutos: int | None) -> str:
    if minutos is None:
        return ""
    h, m = divmod(minutos, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def _nome_curto(nome: str) -> str:
    """Primeiro nome + inicial do último: dá para reconhecer sem expor o nome todo no painel."""
    partes = [p for p in texto(nome).split() if p]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0].title()
    return f"{partes[0].title()} {partes[-1][0].upper()}."


def _no_mesmo_dia(ids: list[str], sql: str, params: tuple = ()) -> dict:
    """Roda `sql` (com {ids}) para a lista de atendimentos e indexa por id_atendimento."""
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    return {l["id_atendimento"]: l for l in db.consultar(sql.format(ids=marcas), (*params, *ids))}


def procedimento(a: dict, agora: datetime, ev: dict, sol: dict, disp: dict, dev: dict) -> dict:
    """Situação de um procedimento (atendimento), com as horas de cada etapa."""
    e = ev.get(a["id_atendimento"]) or {}
    s = sol.get(a["id_atendimento"]) or {}
    d = disp.get(a["id_atendimento"]) or {}
    v = dev.get(a["id_atendimento"]) or {}
    bips = int(e.get("usados") or 0)
    ciencia = d.get("confirmada_em") or ""
    # Antes do botão (ou dado antigo): a 1ª ciência/bip vale como abertura.
    aberta = a.get("sala_aberta_em") or min([x for x in (ciencia, e.get("primeiro_bip")) if x], default="")
    conferencia = v.get("confirmada_em") or ""
    if a.get("uso_finalizado_em") and not conferencia and a.get("encerrado_em"):
        conferencia = a["encerrado_em"]
    horas = {"aberta": aberta, "ciencia": ciencia, "em_uso": e.get("primeiro_bip") or "",
             "finalizado": a.get("uso_finalizado_em") or "", "conferencia": conferencia,
             "concluido": a.get("encerrado_em") or ""}
    if a.get("cancelado_em") or a.get("status") == "cancelado":
        etapa = "cancelado"
    elif a.get("encerrado_em") or a.get("status") == "encerrado":
        etapa = "concluido"
    elif a.get("uso_finalizado_em"):
        etapa = "conferido" if (conferencia and not v.get("pendentes")) else "aguardando_farmacia"
    elif bips > 0:
        etapa = "em_uso"
    elif ciencia:
        etapa = "ciencia"
    elif aberta:
        etapa = "aberta"
    else:
        etapa = "agendado"

    alertas = []
    if s and s.get("faltando") and etapa not in ("concluido", "cancelado", "aguardando_farmacia", "conferido"):
        m = _minutos(s.get("criado_em"), agora) or 0
        alertas.append({"tipo": "pedido", "atrasado": m >= MINUTOS_PEDIDO_ATRASADO,
                        "texto": f"Pedido de OPME em aberto (faltam {s['faltando']}) · há {_duracao(m)}"})
    if d.get("pendentes"):
        m = _minutos(d.get("criado_em"), agora)
        if m is not None and m >= MINUTOS_DISPENSA_SEM_CONFIRMAR:
            alertas.append({"tipo": "dispensa", "atrasado": True,
                            "texto": f"Material dispensado sem ciência da sala há {_duracao(m)}"})
    if int(e.get("avarias") or 0):
        alertas.append({"tipo": "avaria", "atrasado": True,
                        "texto": f"{e['avarias']} material(is) com problema sinalizado"})

    fim_sala = horas["finalizado"] or (a.get("cancelado_em") or "")
    minutos_sala = _minutos(aberta, _dt(fim_sala) or agora) if aberta else None
    rot, cor = SITUACAO[etapa]
    return {
        "id_atendimento": a["id_atendimento"], "prontuario": a["prontuario"],
        "paciente": _nome_curto(a.get("paciente") or ""), "especialidade": a.get("especialidade") or "",
        "sala": a["sala"], "unidade": a["unidade"], "hora_agendada": texto(a.get("hora_inicio"))[:5],
        "etapa": etapa, "ordem": ORDEM[etapa], "situacao": rot, "cor": cor,
        "horas": {k: _hora(x) for k, x in horas.items()},
        "aberta_auto": bool(a.get("sala_aberta_auto")) or (bool(aberta) and not a.get("sala_aberta_em")),
        "inicio_iso": texto(aberta)[:19], "fim_iso": texto(fim_sala)[:19],
        "farmacia_desde": _hora(horas["finalizado"]) if etapa in NA_FARMACIA else "",
        "farmacia_ha": _duracao(_minutos(horas["finalizado"], agora)) if etapa in NA_FARMACIA else "",
        "aberta_ha": _duracao(minutos_sala) if etapa in NA_SALA else "",
        "duracao": _duracao(minutos_sala) if etapa in NA_FARMACIA + ("concluido",) else "",
        "bips": max(bips, 0), "ultimo_bip": _hora(e.get("ultimo_bip")),
        "bips_horas": [h for h in texto(e.get("bips_horas")).split(",") if h][:200],
        "avarias": int(e.get("avarias") or 0),
        "dispensa_pendente": int(d.get("pendentes") or 0),
        "sala_aberta_registrada": bool(a.get("sala_aberta_em")),
        "solicitacao": ({"linhas": s.get("linhas", 0), "faltando": s.get("faltando", 0)} if s else None),
        "alertas": alertas,
    }


def _situacao_solicitacoes(ids: list[str]) -> dict:
    sol = _no_mesmo_dia(ids, """SELECT id_atendimento, criado_em, finalizada_em, cancelada_em FROM solicitacoes
                                WHERE COALESCE(cancelada_em,'') = '' AND id_atendimento IN ({ids})""")
    if sol:
        from . import solicitacoes
        for k, s in sol.items():
            try:
                st = solicitacoes.situacao(k)
                s["linhas"], s["faltando"] = st.get("qtd_linhas", 0), st.get("qtd_faltando", 0)
            except Exception:  # o painel nunca pode cair por causa de um pedido
                s["linhas"], s["faltando"] = 0, 0
    return sol


def _procedimentos(atend: list[dict], agora: datetime) -> list[dict]:
    ids = [a["id_atendimento"] for a in atend]
    t_bip = ",".join(f"'{t}'" for t in TIPOS_BIP)
    ev = _no_mesmo_dia(ids, f"""
        SELECT id_atendimento,
               MIN(CASE WHEN tipo IN ({t_bip}) THEN data_evento END) AS primeiro_bip,
               MAX(CASE WHEN tipo IN ({t_bip}) THEN data_evento END) AS ultimo_bip,
               COUNT(DISTINCT CASE WHEN tipo = 'avaria_sinalizada' THEN id_unidade END) AS avarias,
               GROUP_CONCAT(CASE WHEN tipo IN ({t_bip}) THEN substr(data_evento, 12, 5) END) AS bips_horas
        FROM eventos WHERE id_atendimento IN ({{ids}}) GROUP BY id_atendimento""")
    usados = _no_mesmo_dia(ids, """SELECT id_atendimento, COUNT(*) AS n FROM unidades
                                   WHERE status = 'utilizado' AND id_atendimento IN ({ids}) GROUP BY id_atendimento""")
    for k, u in usados.items():
        ev.setdefault(k, {"id_atendimento": k})["usados"] = u["n"]
    sol = _situacao_solicitacoes(ids)
    disp = _no_mesmo_dia(ids, """
        SELECT id_atendimento, MIN(criado_em) AS criado_em, MIN(confirmada_em) AS confirmada_em,
               SUM(CASE WHEN status = 'pendente' THEN 1 ELSE 0 END) AS pendentes
        FROM dispensacoes WHERE id_atendimento IN ({ids}) GROUP BY id_atendimento""")
    dev = _no_mesmo_dia(ids, """
        SELECT id_atendimento, SUM(CASE WHEN status = 'pendente' THEN 1 ELSE 0 END) AS pendentes,
               MAX(confirmada_em) AS confirmada_em
        FROM devolucoes WHERE id_atendimento IN ({ids}) GROUP BY id_atendimento""")
    return [procedimento(a, agora, ev, sol, disp, dev) for a in atend]


def do_atendimento(id_atendimento: str) -> dict | None:
    """As etapas de um procedimento só (para a ficha da sala)."""
    a = db.consultar_um("SELECT * FROM atendimentos WHERE id_atendimento = ?", (texto(id_atendimento),))
    return _procedimentos([dict(a)], datetime.now())[0] if a else None


def painel(unidade: str = "", data: str = "") -> dict:
    """Tudo o que a central mostra, para uma unidade (ou todas) e um dia."""
    from . import chamados_sala as chamados
    agora = datetime.now()
    data = texto(data)[:10] or agora.date().isoformat()
    unidade = texto(unidade).upper()
    unidades = [unidade] if unidade in UNIDADES_ATIVAS else list(UNIDADES_ATIVAS)
    marcas = ",".join("?" * len(unidades))
    atend = [dict(a) for a in db.consultar(
        f"""SELECT * FROM atendimentos WHERE data_procedimento = ? AND unidade IN ({marcas})
            ORDER BY sala, COALESCE(hora_inicio, '99:99'), criado_em""", (data, *unidades))]
    procs = _procedimentos(atend, agora)
    chamados_abertos = chamados.abertos_por_sala() if data == agora.date().isoformat() else {}

    salas = []
    for un in unidades:
        nomes = list(salas_da_unidade(un))
        extras = sorted({p["sala"] for p in procs if p["unidade"] == un} - set(nomes))
        for sala in nomes + extras:
            dela = [p for p in procs if p["unidade"] == un and p["sala"] == sala]
            na_sala = [p for p in dela if p["etapa"] in NA_SALA]
            na_farmacia = [p for p in dela if p["etapa"] in NA_FARMACIA]
            proximos = [p for p in dela if p["etapa"] == "agendado"]
            concluidos = [p for p in dela if p["etapa"] == "concluido"]
            # O cartão mostra o que está NA SALA agora; o que já saiu da sala e
            # espera a farmácia aparece à parte (a sala pode já ter outro paciente).
            if na_sala:
                atual, etapa = na_sala[-1], na_sala[-1]["etapa"]
            elif proximos:
                atual, etapa = proximos[0], "agendado"
            elif na_farmacia:
                atual, etapa = None, "livre_conferencia"
            elif concluidos:
                atual, etapa = concluidos[-1], "concluido"
            else:
                atual, etapa = None, "livre"
            rot, cor = SITUACAO[etapa]
            salas.append({
                "chave": f"{un}|{sala}", "unidade": un, "unidade_rotulo": rotulo_unidade(un), "sala": sala,
                "etapa": etapa, "situacao": rot, "cor": cor, "atual": atual,
                "na_farmacia": na_farmacia,
                "alertas": [x for p in dela for x in p["alertas"]],
                "chamados": chamados_abertos.get((un, sala), []),
                "procedimentos": dela,
                "contagem": {"total": len(dela), "feitos": len(concluidos) + len(na_farmacia),
                             "proximos": len(proximos),
                             "cancelados": len([p for p in dela if p["etapa"] == "cancelado"])},
            })

    def conta(*etapas):
        return sum(1 for p in procs if p["etapa"] in etapas)
    resumo = {
        "salas": len(salas),
        "em_andamento": conta(*NA_SALA),
        "pedidos_abertos": sum(1 for p in procs for x in p["alertas"] if x["tipo"] == "pedido"),
        "conferencia_farmacia": conta(*NA_FARMACIA),
        "finalizados": conta("concluido", *NA_FARMACIA),
        "procedimentos": len([p for p in procs if p["etapa"] != "cancelado"]),
        "itens_bipados": sum(p["bips"] for p in procs),
        "chamados": sum(len(s["chamados"]) for s in salas),
        "com_alerta": sum(1 for s in salas if s["alertas"]),
    }
    return {"data": data, "unidade": unidade if unidade in UNIDADES_ATIVAS else "",
            "atualizado_em": agora.strftime("%H:%M:%S"), "agora_iso": agora.isoformat(timespec="seconds"),
            "hoje": data == agora.date().isoformat(),
            "salas": salas, "resumo": resumo, "etapas": ETAPAS,
            "legenda": [{"etapa": k, "rotulo": v[0], "cor": v[1]} for k, v in SITUACAO.items()
                        if k not in ("cancelado", "conferido", "livre_conferencia")],
            "unidades": {k: rotulo_unidade(k) for k in UNIDADES_ATIVAS}}


def linha_do_tempo(id_atendimento: str) -> list[dict]:
    """Tudo o que aconteceu no procedimento, na ordem (para o painel lateral)."""
    tipos = ",".join(f"'{t}'" for t in ROTULO_EVENTO)
    linhas = db.consultar(
        f"""SELECT e.tipo, e.data_evento, e.usuario, e.motivo, e.observacao, e.id_unidade,
                   COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd) AS material
            FROM eventos e LEFT JOIN unidades u ON u.id_unidade = e.id_unidade
            WHERE e.id_atendimento = ? AND e.tipo IN ({tipos})
            ORDER BY e.data_evento, e.id_evento""", (texto(id_atendimento),))
    saida, ultimo = [], None
    for l in linhas:
        # bips seguidos viram uma linha só ("Bipado no paciente — 3 itens")
        chave = (l["tipo"], _hora(l["data_evento"]), l["usuario"])
        if l["tipo"] in TIPOS_BIP and ultimo and ultimo["_chave"] == chave:
            ultimo["qtd"] += 1
            if l["material"] and len(ultimo["materiais"]) < 4:
                ultimo["materiais"].append(l["material"])
            continue
        ultimo = {"_chave": chave, "tipo": l["tipo"], "hora": _hora(l["data_evento"]),
                  "rotulo": ROTULO_EVENTO.get(l["tipo"], l["tipo"]), "usuario": l["usuario"] or "",
                  "detalhe": texto(l["motivo"]) or "", "qtd": 1,
                  "materiais": [l["material"]] if l["material"] else []}
        saida.append(ultimo)
    for s in saida:
        s.pop("_chave", None)
    return saida
