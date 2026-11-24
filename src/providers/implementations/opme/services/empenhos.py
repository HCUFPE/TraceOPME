"""Controle de saldo de empenho para materiais consignados.

Para materiais consignados, o fornecedor deixa o material no hospital e só
fatura quando ele é usado. Cada uso precisa ser vinculado a um empenho — a
"linha de crédito" que autoriza aquele gasto — e debita uma unidade do saldo.
Sem saldo, não dá para vincular: é preciso pedir mais orçamento à gestão antes
de continuar. Um empenho costuma cobrir várias medidas/especificações do mesmo
material (ex.: cateter balão em vários tamanhos) — todas debitam do mesmo
saldo, contado em unidades, não por especificação.

Este módulo não altera o fluxo de rastreabilidade existente. Ele só observa
unidades que já chegaram ao estado final `utilizado` (registrado no paciente)
com `tipo_entrada == 'consignado'`, e controla um vínculo à parte — nunca muda
o status da unidade em si.
"""

import sqlite3

from .. import db
from ..config import LIMIAR_ALERTA_EMPENHO
from ..domain import UTILIZADO
from ..erros import ErroDeNegocio
from ..utils import data_iso, decimal, gerar_id, hoje_iso, inteiro, texto
from . import alertas

MODULO = "consignados"


# =========================================================
# EMPENHOS
# =========================================================

def _com_saldo(linha: dict) -> dict:
    empenho = dict(linha)
    vinculados = empenho.pop("vinculados", 0) or 0
    total = empenho["quantidade_total"] or 0
    saldo = max(0, total - vinculados)
    empenho["saldo"] = saldo
    empenho["utilizados"] = vinculados
    empenho["valor_total"] = round(total * empenho["valor_unitario"], 2)
    empenho["valor_utilizado"] = round(vinculados * empenho["valor_unitario"], 2)
    empenho["valor_saldo"] = round(saldo * empenho["valor_unitario"], 2)
    empenho["percentual_usado"] = round(100 * vinculados / total, 1) if total else 0.0
    # v17: limite de segurança em unidades. Empenho antigo, sem limite gravado,
    # usa o percentual geral da configuração.
    limite = empenho.get("limite_seguranca")
    if limite is None:
        limite = int(round(total * (1 - LIMIAR_ALERTA_EMPENHO)))
    empenho["limite"] = limite
    empenho["no_limite"] = empenho.get("status") == "ativo" and saldo <= limite
    codigos = texto(empenho.pop("codigos_aghu", "") or "")
    empenho["codigos_aghu"] = [c for c in codigos.split(",") if c]
    # nov/2026: códigos consignados cobertos, cada um com o AGHU associado.
    pares = texto(empenho.pop("pares_consignado", "") or "")
    empenho["pares"] = [{"consignado": p.split("=", 1)[0], "aghu": (p.split("=", 1) + [""])[1]}
                        for p in sorted(pares.split(",")) if p]
    empenho["codigos_consignado"] = [p["consignado"] for p in empenho["pares"]]
    # v17: vigência da licitação. Fora da vigência o empenho não recebe débito.
    hoje = hoje_iso()
    inicio, fim = texto(empenho.get("vigencia_inicio")), texto(empenho.get("vigencia_fim"))
    empenho["vigencia"] = ("vencida" if fim and fim < hoje else
                           "futura" if inicio and inicio > hoje else "vigente")
    empenho["identificacao"] = (texto(empenho.get("numero"))
                                or (f"Registro {empenho['numero_registro']}" if texto(empenho.get("numero_registro")) else "")
                                or (f"Pregão {empenho['numero_pregao']}" if texto(empenho.get("numero_pregao")) else "")
                                or (f"Processo {empenho['numero_processo']}" if texto(empenho.get("numero_processo")) else "")
                                or "—")
    return empenho


def _codigos(valor) -> list[str]:
    import re
    return list(dict.fromkeys(
        c.strip().upper() for c in re.split(r"[\s,;]+", texto(valor)) if c.strip()))


def cadastrar(dados: dict, usuario: str) -> tuple[bool, str]:
    fornecedor = texto(dados.get("fornecedor"))
    material = texto(dados.get("material"))
    numero = texto(dados.get("numero"))
    quantidade = inteiro(dados.get("quantidade_total"), 0)
    valor_unitario = decimal(dados.get("valor_unitario"))

    processo = texto(dados.get("numero_processo"))
    pregao = texto(dados.get("numero_pregao"))
    registro = texto(dados.get("numero_registro"))
    if not (numero or processo or pregao or registro):
        return False, ("Informe ao menos um número: do empenho, do processo, do pregão ou "
                       "do registro de licitação.")
    if not fornecedor:
        return False, "Informe o fornecedor."
    # nov/2026: o empenho é cadastrado pelo CÓDIGO CONSIGNADO; o AGHU vem da
    # associação (ou é informado ao lado, e a associação é criada).
    from . import consignado_aghu
    ok_pares, pares = consignado_aghu.resolver_pares(_pares(dados))
    if not ok_pares:
        return False, pares
    codigos = list(dict.fromkeys(a for _, a, _ in pares))
    if not material:
        from . import materiais
        material = materiais.descritivo_hospital(codigos[0])
    if not material:
        # Sem catálogo carregado: identifica pelo(s) código(s) AGHU.
        material = "AGHU " + ", ".join(codigos)
    if quantidade <= 0:
        return False, "A quantidade de unidades do empenho precisa ser maior que zero."
    if valor_unitario <= 0:
        return False, "Informe o valor unitário."
    import math
    limite_txt = texto(dados.get("limite_seguranca"))
    limite = inteiro(limite_txt, -1) if limite_txt else math.ceil(quantidade * 0.2)
    if limite < 0 or limite >= quantidade:
        return False, ("O limite de segurança precisa ser um número de unidades entre 0 e "
                       f"{quantidade - 1}.")

    vig_inicio = data_iso(dados.get("vigencia_inicio")) if texto(dados.get("vigencia_inicio")) else ""
    vig_fim = data_iso(dados.get("vigencia_fim")) if texto(dados.get("vigencia_fim")) else ""
    if texto(dados.get("vigencia_inicio")) and not vig_inicio:
        return False, "Data de início da vigência inválida (use dd/mm/aaaa)."
    if texto(dados.get("vigencia_fim")) and not vig_fim:
        return False, "Data de fim da vigência inválida (use dd/mm/aaaa)."
    if vig_inicio and vig_fim and vig_fim < vig_inicio:
        return False, "O fim da vigência não pode ser antes do início."

    data_empenho = data_iso(dados.get("data_empenho")) or vig_inicio or db.agora()[:10]

    id_empenho = gerar_id("EMP")
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO empenhos
               (id_empenho, numero, fornecedor, material, data_empenho, quantidade_total,
                valor_unitario, status, observacao, criado_em, criado_por, limite_seguranca,
                vigencia_inicio, vigencia_fim, numero_processo, numero_pregao, numero_registro)
               VALUES (?,?,?,?,?,?,?,'ativo',?,?,?,?,?,?,?,?,?)""",
            (id_empenho, numero, fornecedor, material, data_empenho,
             quantidade, valor_unitario, texto(dados.get("observacao")), db.agora(), usuario,
             limite, vig_inicio or None, vig_fim or None, processo or None, pregao or None,
             registro or None),
        )
        for codigo in codigos:
            conn.execute("INSERT INTO empenho_aghu (id_empenho, codigo_aghu) VALUES (?,?)",
                         (id_empenho, codigo))
        for consignado, aghu, nova in pares:
            if nova:
                consignado_aghu.salvar(consignado, aghu, usuario, fornecedor, conn=conn)
            conn.execute("INSERT INTO empenho_consignado (id_empenho, codigo_consignado, codigo_aghu) VALUES (?,?,?)",
                         (id_empenho, consignado, aghu))
    return True, id_empenho


def _pares(dados: dict) -> list[tuple[str, str]]:
    """Pares (código consignado, AGHU) do formulário ou da planilha.

    Formulário: lista `pares`. Planilha/texto: `codigos_consignado` (um ou
    vários, separados por vírgula) e `codigos_aghu` alinhados — um AGHU só vale
    para todos; AGHU em branco vem da associação.
    """
    if dados.get("pares"):
        return [(texto(c), texto(a)) for c, a in dados["pares"]]
    consignados = _codigos(dados.get("codigos_consignado"))
    aghus = _codigos(dados.get("codigos_aghu"))
    if not consignados:
        return []
    if len(aghus) == len(consignados):
        return list(zip(consignados, aghus))
    if len(aghus) == 1:
        return [(c, aghus[0]) for c in consignados]
    return [(c, "") for c in consignados]


def listar(fornecedor: str = "", status: str = "", termo: str = "") -> list[dict]:
    condicoes = ["1=1"]
    params: list = []
    if texto(fornecedor):
        condicoes.append("e.fornecedor = ?")
        params.append(texto(fornecedor))
    if texto(status):
        condicoes.append("e.status = ?")
        params.append(texto(status))
    if texto(termo):
        condicoes.append("""(e.material LIKE ? OR e.numero LIKE ? OR e.fornecedor LIKE ?
            OR e.numero_processo LIKE ? OR e.numero_pregao LIKE ? OR e.numero_registro LIKE ?
            OR EXISTS (SELECT 1 FROM empenho_aghu x WHERE x.id_empenho = e.id_empenho
                       AND x.codigo_aghu LIKE ?)
            OR EXISTS (SELECT 1 FROM empenho_consignado y WHERE y.id_empenho = e.id_empenho
                       AND y.codigo_consignado LIKE ?))""")
        params += [f"%{texto(termo)}%"] * 7 + [f"%{texto(termo).upper()}%"]

    linhas = db.consultar(
        f"""SELECT e.*, COUNT(v.id_vinculo) AS vinculados,
                   (SELECT GROUP_CONCAT(codigo_aghu) FROM empenho_aghu x
                     WHERE x.id_empenho = e.id_empenho) AS codigos_aghu,
                   (SELECT GROUP_CONCAT(codigo_consignado || '=' || COALESCE(codigo_aghu, '')) FROM empenho_consignado y
                     WHERE y.id_empenho = e.id_empenho) AS pares_consignado
            FROM empenhos e
            LEFT JOIN empenho_vinculos v
                   ON v.id_empenho = e.id_empenho AND v.status = 'ativo'
            WHERE {' AND '.join(condicoes)}
            GROUP BY e.id_empenho
            ORDER BY e.status, e.data_empenho DESC, e.criado_em DESC""",
        params,
    )
    return [_com_saldo(l) for l in linhas]


def buscar(id_empenho: str) -> dict | None:
    linha = db.consultar_um(
        """SELECT e.*, COUNT(v.id_vinculo) AS vinculados,
                  (SELECT GROUP_CONCAT(codigo_aghu) FROM empenho_aghu x
                    WHERE x.id_empenho = e.id_empenho) AS codigos_aghu,
                  (SELECT GROUP_CONCAT(codigo_consignado || '=' || COALESCE(codigo_aghu, '')) FROM empenho_consignado y
                     WHERE y.id_empenho = e.id_empenho) AS pares_consignado
           FROM empenhos e
           LEFT JOIN empenho_vinculos v
                  ON v.id_empenho = e.id_empenho AND v.status = 'ativo'
           WHERE e.id_empenho = ?
           GROUP BY e.id_empenho""",
        (texto(id_empenho),),
    )
    return _com_saldo(linha) if linha else None


def disponiveis(fornecedor: str = "") -> list[dict]:
    """Empenhos ativos com saldo — as opções válidas para um novo vínculo."""
    return [e for e in listar(fornecedor=fornecedor, status="ativo") if e["saldo"] > 0]


def encerrar(id_empenho: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    empenho = buscar(id_empenho)
    if not empenho:
        return False, "Empenho não encontrado."
    if empenho["status"] != "ativo":
        return False, "Este empenho já não está ativo."
    with db.transacao() as conn:
        conn.execute(
            """UPDATE empenhos SET status = 'encerrado', encerrado_em = ?, encerrado_por = ?,
                                   observacao = CASE WHEN ? <> '' THEN
                                       COALESCE(observacao || ' | ', '') || 'Encerrado: ' || ?
                                       ELSE observacao END
               WHERE id_empenho = ?""",
            (db.agora(), usuario, texto(motivo), texto(motivo), id_empenho),
        )
    return True, ("Empenho encerrado. Ele deixa de aparecer como opção para novos vínculos, "
                  "mas o histórico continua disponível.")


# =========================================================
# VÍNCULO USO → EMPENHO
# =========================================================

def itens_pendentes_de_vinculo(limite: int = 200) -> list[dict]:
    """Consignados já utilizados no paciente que ainda não têm vínculo ativo a um empenho."""
    return db.consultar(
        f"""SELECT u.id_unidade, u.xProd, u.codigo_aghu, u.codigo_consignado, u.nLote, u.numero_serie, u.dVal,
                   u.fornecedor, u.vUnCom, a.prontuario, a.paciente, a.sala, a.especialidade,
                   a.data_procedimento,
                   (SELECT data_evento FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.tipo = 'registrar_uso' ORDER BY ev.id_evento DESC LIMIT 1) AS data_uso
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.status = '{UTILIZADO}' AND u.tipo_entrada = 'consignado'
              AND NOT EXISTS (
                  SELECT 1 FROM empenho_vinculos v
                  WHERE v.id_unidade = u.id_unidade AND v.status = 'ativo'
              )
            ORDER BY u.atualizado_em DESC LIMIT ?""",
        (limite,),
    )


def contar_pendentes_de_vinculo() -> int:
    return db.escalar(
        f"""SELECT COUNT(*) FROM unidades u
            WHERE u.status = '{UTILIZADO}' AND u.tipo_entrada = 'consignado'
              AND NOT EXISTS (
                  SELECT 1 FROM empenho_vinculos v
                  WHERE v.id_unidade = u.id_unidade AND v.status = 'ativo'
              )"""
    )


def vincular(id_unidade: str, id_empenho: str, usuario: str, observacao: str = "") -> tuple[bool, str]:
    """Vincula uma unidade consignada já utilizada a um empenho, debitando o saldo.

    Funciona como um limite de cartão de crédito: sem saldo, o vínculo é
    recusado — não dá para gerar um gasto sem cobertura de empenho.
    """
    id_unidade = texto(id_unidade)
    id_empenho = texto(id_empenho)
    if not id_unidade or not id_empenho:
        return False, "Selecione o item e o empenho."

    unidade = db.consultar_um("SELECT * FROM unidades WHERE id_unidade = ?", (id_unidade,))
    if not unidade:
        return False, "Item não encontrado."
    if unidade["status"] != UTILIZADO:
        return False, "Este item ainda não foi registrado como utilizado no paciente."
    coberto = db.escalar(
        "SELECT COUNT(*) FROM empenho_aghu WHERE id_empenho = ? AND codigo_aghu = ?",
        (id_empenho, texto(unidade["codigo_aghu"]).upper())) or db.escalar(
        "SELECT COUNT(*) FROM empenho_consignado WHERE id_empenho = ? AND codigo_consignado = ?",
        (id_empenho, texto(_valor(unidade, "codigo_consignado")).upper().replace(" ", "")))
    if unidade["tipo_entrada"] != "consignado" and not coberto:
        return False, "Este item não é consignado — não precisa de vínculo a empenho."

    id_vinculo = gerar_id("VIN")
    try:
        # Saldo e vínculo duplicado são checados DENTRO da transação. Conferir
        # antes e gravar depois abre uma janela em que duas pessoas vinculam ao
        # mesmo tempo, cada uma vendo a última unidade livre — e o empenho
        # estoura o saldo sem ninguém perceber.
        with db.transacao() as conn:
            linha = conn.execute(
                """SELECT e.*, COUNT(v.id_vinculo) AS vinculados
                   FROM empenhos e
                   LEFT JOIN empenho_vinculos v
                          ON v.id_empenho = e.id_empenho AND v.status = 'ativo'
                   WHERE e.id_empenho = ?
                   GROUP BY e.id_empenho""",
                (id_empenho,),
            ).fetchone()
            if linha is None:
                raise ErroDeNegocio("Empenho não encontrado.")
            empenho = _com_saldo(dict(linha))
            if empenho["status"] != "ativo":
                raise ErroDeNegocio("Este empenho está encerrado e não aceita novos vínculos.")
            if empenho["saldo"] <= 0:
                raise ErroDeNegocio(
                    f"Empenho {empenho.get('identificacao') or empenho['numero']} sem saldo disponível "
                    f"({empenho['quantidade_total']} de {empenho['quantidade_total']} já usadas). "
                    f"Solicite mais saldo à gestão antes de vincular este uso.")
            if conn.execute(
                "SELECT 1 FROM empenho_vinculos WHERE id_unidade = ? AND status = 'ativo'",
                (id_unidade,),
            ).fetchone():
                raise ErroDeNegocio("Este item já está vinculado a um empenho.")

            saldo_antes = empenho["saldo"]
            conn.execute(
                """INSERT INTO empenho_vinculos
                   (id_vinculo, id_empenho, id_unidade, status, data_vinculo, usuario, observacao)
                   VALUES (?,?,?,'ativo',?,?,?)""",
                (id_vinculo, id_empenho, id_unidade, db.agora(), usuario, texto(observacao)),
            )
    except ErroDeNegocio as recusa:
        return False, str(recusa)
    except sqlite3.IntegrityError:
        # Índice único parcial: a outra ponta da corrida chegou primeiro.
        return False, "Este item já está vinculado a um empenho."

    saldo_depois = saldo_antes - 1
    _avaliar_alerta(empenho, saldo_antes, saldo_depois, usuario)

    return True, (f"Vinculado ao empenho {empenho.get('identificacao') or empenho['numero']} — "
                  f"{saldo_depois} de {empenho['quantidade_total']} unidade(s) restante(s).")


def _avaliar_alerta(empenho: dict, saldo_antes: int, saldo_depois: int, usuario: str) -> None:
    """Dispara alerta ao esgotar o saldo, ou ao cruzar o limiar de aviso antecipado.

    A checagem "antes < limiar <= depois" garante que o alerta antecipado
    dispara uma única vez, no vínculo exato que cruza o limiar — não a cada
    vínculo seguinte, o que enche a lista de avisos repetidos e sem utilidade.
    """
    total = empenho["quantidade_total"]
    if total <= 0:
        return
    identificacao = f"{empenho.get('identificacao') or empenho['numero']} ({empenho['fornecedor']} · {empenho['material']})"
    limite = empenho.get("limite")
    if limite is None:
        limite = int(round(total * (1 - LIMIAR_ALERTA_EMPENHO)))

    if saldo_depois == 0:
        alertas.criar(
            modulo_destino=MODULO,
            titulo="Empenho sem saldo",
            mensagem=(f"O empenho {identificacao} chegou a 0 de {total} unidade(s) "
                      f"disponíveis. Solicite mais saldo à gestão antes do próximo uso "
                      f"deste material — sem isso, novos vínculos serão recusados."),
            usuario=usuario,
            link=f"/consignados/empenhos/{empenho['id_empenho']}",
        )
    elif saldo_depois <= limite < saldo_antes:
        # Cruzou o limite de segurança agora — um aviso só, neste uso.
        alertas.criar(
            modulo_destino=MODULO,
            titulo="Comprar mais empenho — limite de segurança atingido",
            mensagem=(f"O empenho {identificacao} chegou ao limite de segurança: restam "
                      f"{saldo_depois} de {total} unidade(s) (limite: {limite}). "
                      f"Providencie novo empenho antes que o saldo acabe."),
            usuario=usuario,
            link=f"/consignados/empenhos/{empenho['id_empenho']}",
        )


def buscar_vinculo(id_vinculo: str) -> dict | None:
    return db.consultar_um(
        "SELECT * FROM empenho_vinculos WHERE id_vinculo = ?", (texto(id_vinculo),)
    )


def cancelar_vinculo(id_vinculo: str, usuario: str, motivo: str) -> tuple[bool, str]:
    """Desfaz um vínculo feito por engano — o saldo do empenho volta.

    Nada é apagado: o vínculo original continua na tabela, marcado como
    cancelado com o motivo, seguindo o mesmo princípio do estorno de uso.
    """
    if not texto(motivo):
        return False, "Informe o motivo do cancelamento — ele fica registrado."
    vinculo = buscar_vinculo(id_vinculo)
    if not vinculo:
        return False, "Vínculo não encontrado."
    if vinculo["status"] != "ativo":
        return False, "Este vínculo já foi cancelado."

    with db.transacao() as conn:
        conn.execute(
            """UPDATE empenho_vinculos
               SET status = 'cancelado', motivo_cancelamento = ?,
                   cancelado_em = ?, cancelado_por = ?
               WHERE id_vinculo = ?""",
            (texto(motivo), db.agora(), usuario, texto(id_vinculo)),
        )
    return True, "Vínculo cancelado. A unidade volta a aguardar vínculo e o saldo do empenho volta."


def vinculos_do_empenho(id_empenho: str, limite: int = 300, inicio: str = "",
                        fim: str = "", so_ativos: bool = True) -> list[dict]:
    """Materiais vinculados ao empenho, com a descrição do AGHU, validade, série,
    especialidade e unidade (Bloco ou Hemodinâmica). Filtro por período (data do
    vínculo, que é a data do uso). Por padrão só os vínculos ativos: o cancelado
    não debita o empenho e não interessa ao relatório."""
    from ..config import rotulo_unidade
    condicoes, params = ["v.id_empenho = ?"], [texto(id_empenho)]
    if so_ativos:
        condicoes.append("v.status = 'ativo'")
    if data_iso(inicio):
        condicoes.append("substr(v.data_vinculo, 1, 10) >= ?")
        params.append(data_iso(inicio))
    if data_iso(fim):
        condicoes.append("substr(v.data_vinculo, 1, 10) <= ?")
        params.append(data_iso(fim))
    params.append(limite)
    linhas = db.consultar(
        f"""SELECT v.*, u.xProd, u.codigo_aghu, u.codigo_consignado, u.nLote, u.numero_serie, u.dVal,
                   COALESCE(NULLIF(u.descritivo_hospital, ''), NULLIF(m.descritivo_hospital, ''),
                            NULLIF(e.material, ''), u.xProd) AS descricao_aghu,
                   a.prontuario, a.paciente, a.sala, a.unidade, a.especialidade, a.data_procedimento
            FROM empenho_vinculos v
            JOIN unidades u ON u.id_unidade = v.id_unidade
            LEFT JOIN empenhos e ON e.id_empenho = v.id_empenho
            LEFT JOIN materiais_mestre m ON m.codigo_aghu = u.codigo_aghu
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE {' AND '.join(condicoes)}
            ORDER BY v.data_vinculo DESC LIMIT ?""",
        params,
    )
    for l in linhas:
        l["descricao_hc"] = l["descricao_aghu"]
        l["unidade_rotulo"] = rotulo_unidade(l["unidade"]) if l.get("unidade") else "—"
    return linhas


def pdf_vinculos(id_empenho: str, inicio: str = "", fim: str = "") -> bytes | None:
    """v17 — relatório em PDF dos materiais vinculados, no período escolhido."""
    from ..pdf_simples import tabela
    from ..utils import data_br, data_hora_br, moeda
    empenho = buscar(id_empenho)
    if not empenho:
        return None
    vinculos = vinculos_do_empenho(id_empenho, limite=100000, inicio=inicio, fim=fim)
    ativos = vinculos
    periodo = (f"{data_br(data_iso(inicio)) or 'início'} a {data_br(data_iso(fim)) or 'hoje'}"
               if (data_iso(inicio) or data_iso(fim)) else "todo o período")
    info = [("Fornecedor", empenho["fornecedor"]),
            ("Material / AGHU", f"{empenho['material']} · AGHU {', '.join(empenho['codigos_aghu'])}"),
            ("Código consignado → AGHU", ", ".join(f"{p['consignado']} → {p['aghu'] or '—'}" for p in empenho["pares"]) or "—"),
            ("Licitação", " · ".join(x for x in (
                f"Processo {empenho.get('numero_processo')}" if empenho.get("numero_processo") else "",
                f"Pregão {empenho.get('numero_pregao')}" if empenho.get("numero_pregao") else "",
                f"Registro {empenho.get('numero_registro')}" if empenho.get("numero_registro") else "",
            ) if x) or "—"),
            ("Vigência", f"{data_br(empenho.get('vigencia_inicio')) or '—'} a {data_br(empenho.get('vigencia_fim')) or '—'}"),
            ("Saldo atual", f"{empenho['saldo']} de {empenho['quantidade_total']} unidade(s) · "
                            f"valor unitário {moeda(empenho['valor_unitario'])}")]
    linhas = [[data_hora_br(v["data_vinculo"]),
               v["descricao_aghu"] or "",
               v["codigo_consignado"] or "", v["codigo_aghu"] or "", v["nLote"] or "", data_br(v["dVal"]) or "",
               v["numero_serie"] or "", v["prontuario"] or "",
               v["paciente"] or "", v["especialidade"] or "", v["unidade_rotulo"]] for v in vinculos]
    return tabela(
        titulo=f"Empenho {empenho['identificacao']} — materiais vinculados",
        subtitulo=f"Período: {periodo}",
        informacoes=info,
        colunas=[("Data do uso", 1.25), ("Produto (descrição AGHU)", 3.0), ("Consignado", 1.0), ("AGHU", .8), ("Lote", 1.1),
                 ("Validade", 1.2), ("Nº série", 1.0), ("Prontuário", 1.25), ("Paciente", 1.7),
                 ("Especialidade", 1.45), ("Unidade", 1.3)],
        linhas=linhas,
        quebrar_linhas=True,
        totais=[f"{len(ativos)} material(is) vinculado(s) no período · "
                f"{moeda(len(ativos) * (empenho['valor_unitario'] or 0))}"],
        rodape="TraceOPME · Consignados - Empenhos",
    )



# =========================================================
# v17 — DÉBITO AUTOMÁTICO PELO CÓDIGO AGHU
# =========================================================

def empenho_para_aghu(codigo_aghu: str) -> dict | None:
    """Empenho ativo, com saldo, que cobre este AGHU — o mais antigo primeiro."""
    codigo = texto(codigo_aghu).strip().upper()
    if not codigo:
        return None
    candidatos = db.consultar(
        """SELECT e.id_empenho FROM empenhos e
           JOIN empenho_aghu x ON x.id_empenho = e.id_empenho
           WHERE x.codigo_aghu = ? AND e.status = 'ativo'
           ORDER BY CASE WHEN COALESCE(e.vigencia_fim, '') = '' THEN 1 ELSE 0 END, e.vigencia_fim,
                     COALESCE(e.data_empenho, e.criado_em), e.criado_em""", (codigo,))
    for c in candidatos:
        empenho = buscar(c["id_empenho"])
        # v17: só empenho dentro da vigência recebe débito.
        if empenho and empenho["saldo"] > 0 and empenho["vigencia"] == "vigente":
            return empenho
    return None


def aghu_tem_empenho(codigo_aghu: str) -> bool:
    return bool(db.escalar(
        """SELECT COUNT(*) FROM empenho_aghu x JOIN empenhos e ON e.id_empenho = x.id_empenho
           WHERE x.codigo_aghu = ? AND e.status = 'ativo'""",
        (texto(codigo_aghu).strip().upper(),)))


def _valor(linha, campo: str):
    try:
        return linha[campo]
    except (KeyError, IndexError):
        return None


def _consignado_da_unidade(unidade) -> str:
    return texto(_valor(unidade, "codigo_consignado")).upper().replace(" ", "")


def _ids_por_consignado(codigo: str) -> list[str]:
    return [l["id_empenho"] for l in db.consultar(
        """SELECT e.id_empenho FROM empenhos e JOIN empenho_consignado y ON y.id_empenho = e.id_empenho
           WHERE y.codigo_consignado = ? AND e.status = 'ativo'
           ORDER BY CASE WHEN COALESCE(e.vigencia_fim, '') = '' THEN 1 ELSE 0 END, e.vigencia_fim,
                     COALESCE(e.data_empenho, e.criado_em), e.criado_em""", (codigo,))]


def _ids_legados_por_aghu(codigo_aghu: str, so_sem_consignado: bool) -> list[str]:
    extra = ("AND NOT EXISTS (SELECT 1 FROM empenho_consignado y WHERE y.id_empenho = e.id_empenho)"
             if so_sem_consignado else "")
    return [l["id_empenho"] for l in db.consultar(
        f"""SELECT e.id_empenho FROM empenhos e JOIN empenho_aghu x ON x.id_empenho = e.id_empenho
            WHERE x.codigo_aghu = ? AND e.status = 'ativo' {extra}
            ORDER BY CASE WHEN COALESCE(e.vigencia_fim, '') = '' THEN 1 ELSE 0 END, e.vigencia_fim,
                     COALESCE(e.data_empenho, e.criado_em), e.criado_em""", (texto(codigo_aghu).strip().upper(),))]


def empenhos_da_unidade(unidade) -> list[str]:
    """Empenhos ativos que cobrem a unidade (nov/2026).

    Com código consignado: os empenhos desse código. Se nenhum empenho tem o
    código, valem os empenhos antigos (cadastrados só por AGHU, sem código
    consignado) — um empenho novo de OUTRO código consignado com o mesmo AGHU
    não é debitado. Unidade sem código consignado: qualquer empenho do AGHU.
    """
    consignado = _consignado_da_unidade(unidade)
    if consignado:
        ids = _ids_por_consignado(consignado)
        if ids:
            return ids
        return _ids_legados_por_aghu(texto(_valor(unidade, "codigo_aghu")), so_sem_consignado=True)
    return _ids_legados_por_aghu(texto(_valor(unidade, "codigo_aghu")), so_sem_consignado=False)


def empenho_para_aghu(codigo_aghu: str) -> dict | None:
    """Compatibilidade: empenho ativo, vigente e com saldo que cobre o AGHU (unidade sem código consignado)."""
    return empenho_para_unidade({"codigo_aghu": codigo_aghu, "codigo_consignado": ""})


def empenho_para_unidade(unidade) -> dict | None:
    """O empenho ativo, vigente e com saldo que cobre a unidade.

    nov/2026: com mais de um empenho para o mesmo material, debita primeiro o
    que tem o FIM DA VIGÊNCIA mais próximo (para não perder saldo que vai vencer);
    empenho sem fim de vigência fica por último; empate, o mais antigo.
    """
    for id_empenho in empenhos_da_unidade(unidade):
        empenho = buscar(id_empenho)
        if empenho and empenho["saldo"] > 0 and empenho["vigencia"] == "vigente":
            return empenho
    return None


def vincular_automatico(id_unidade: str, usuario: str) -> dict | None:
    """Chamado logo depois do registro de uso. Debita o saldo do empenho do
    código consignado (nov/2026) — ou do AGHU, nos empenhos antigos.

    Devolve None quando não há empenho (nada a fazer), ou
    {"ok": bool, "mensagem": str, "alerta": bool} para a tela mostrar.
    """
    unidade = db.consultar_um(
        "SELECT id_unidade, codigo_aghu, codigo_consignado, tipo_entrada FROM unidades WHERE id_unidade = ?",
        (texto(id_unidade),))
    if not unidade or not (texto(unidade["codigo_aghu"]) or texto(unidade["codigo_consignado"])):
        return None
    consignado = _consignado_da_unidade(unidade)
    rotulo_codigo = (f"código consignado {consignado}" if consignado else f"AGHU {unidade['codigo_aghu']}")
    if not empenhos_da_unidade(unidade):
        if unidade["tipo_entrada"] == "consignado":
            return {"ok": False, "alerta": True,
                    "mensagem": (f"Consignado sem empenho cadastrado para o {rotulo_codigo} "
                                 f"— ficou pendente de vínculo.")}
        return None
    empenho = empenho_para_unidade(unidade)
    if not empenho:
        alertas.criar(
            modulo_destino=MODULO,
            titulo="Uso sem saldo de empenho",
            mensagem=(f"Foi usada uma unidade do {rotulo_codigo} (AGHU {unidade['codigo_aghu'] or '—'}), mas nenhum "
                      f"empenho ativo e dentro da vigência tem saldo. O uso ficou pendente de vínculo — cadastre "
                      f"novo empenho e vincule em Consignados."),
            usuario=usuario, ids_unidade=[unidade["id_unidade"]])
        return {"ok": False, "alerta": True,
                "mensagem": (f"SEM SALDO de empenho vigente para o {rotulo_codigo}. "
                            f"Avise a gestão.")}
    ok, mensagem = vincular(unidade["id_unidade"], empenho["id_empenho"], usuario,
                            "Débito automático no registro de uso")
    if not ok:
        return {"ok": False, "alerta": True, "mensagem": mensagem}
    depois = buscar(empenho["id_empenho"])
    return {"ok": True, "alerta": bool(depois and depois["no_limite"]),
            "mensagem": (f"Empenho {empenho['identificacao']}: saldo {depois['saldo']} de "
                         f"{depois['quantidade_total']}"
                         + (" — LIMITE DE SEGURANÇA, pedir mais empenho" if depois["no_limite"] else ""))}


def desfazer_vinculo_da_unidade(id_unidade: str, usuario: str, motivo: str) -> None:
    """Uso estornado/excluído: o saldo volta ao empenho."""
    vinculo = db.consultar_um(
        "SELECT id_vinculo FROM empenho_vinculos WHERE id_unidade = ? AND status = 'ativo'",
        (texto(id_unidade),))
    if vinculo:
        cancelar_vinculo(vinculo["id_vinculo"], usuario, motivo or "Uso desfeito")


def no_limite() -> list[dict]:
    """Empenhos ativos no limite de segurança (ou zerados) — pedir mais empenho."""
    return [e for e in listar(status="ativo") if e["no_limite"]]


# =========================================================
# v17 — IMPORTAÇÃO DE EMPENHOS POR PLANILHA
# =========================================================

# Campo → palavras que precisam estar TODAS no título da coluna (sem acento,
# minúsculo). A ordem importa: o primeiro que casar leva a coluna.
_COLUNAS = [
    ("numero_registro", [["registro"]]),
    ("numero_pregao", [["pregao"]]),
    ("numero_processo", [["processo"]]),
    ("numero", [["empenho"]]),
    ("vigencia_inicio", [["inicio"]]),
    ("vigencia_fim", [["fim"], ["termino"], ["final"]]),
    ("codigos_consignado", [["consignado"]]),
    ("codigos_aghu", [["aghu"]]),
    ("quantidade_total", [["quant"], ["qtd"], ["qtde"]]),
    ("valor_unitario", [["valor"], ["preco"]]),
    ("limite_seguranca", [["limite"]]),
    ("fornecedor", [["fornecedor"]]),
    ("material", [["material"], ["descricao"]]),
]
OBRIGATORIAS = {"fornecedor": "Fornecedor", "codigos_consignado": "Código consignado",
                "quantidade_total": "Quantidade licitada", "valor_unitario": "Valor unitário"}


def _data_planilha(valor: str) -> str:
    """Data como vem do Excel: número de série (46000), 2026-01-31 ou 31/01/2026."""
    import datetime
    import re
    valor = texto(valor)
    if not valor:
        return ""
    if re.fullmatch(r"\d{4,5}(\.0+)?", valor):
        base = datetime.date(1899, 12, 30)
        return (base + datetime.timedelta(days=int(float(valor)))).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", valor):
        return valor[:10]
    return valor  # dd/mm/aaaa — `cadastrar` converte e valida


def _mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    from .materiais import _cabecalho
    mapa: dict[str, int] = {}
    for indice, bruto in enumerate(cabecalho):
        titulo = _cabecalho(bruto)
        if not titulo:
            continue
        for campo, alternativas in _COLUNAS:
            if campo in mapa:
                continue
            if any(all(p in titulo for p in palavras) for palavras in alternativas):
                mapa[campo] = indice
                break
    return mapa


def importar_planilha(conteudo: bytes, nome_arquivo: str, usuario: str) -> tuple[bool, str, dict]:
    """Cadastra um empenho por linha. Linhas com erro são listadas e puladas;
    linhas iguais a um empenho ativo já cadastrado são ignoradas (não duplica)."""
    from .materiais import PlanilhaInvalida, _codigo, _linhas_csv, _linhas_xlsx, _valor

    try:
        linhas = (_linhas_csv(conteudo) if texto(nome_arquivo).lower().endswith(".csv")
                  else _linhas_xlsx(conteudo))
    except PlanilhaInvalida as erro:
        return False, str(erro), {}
    # O cabeçalho é a primeira linha (entre as 10 primeiras) que tenha as colunas obrigatórias.
    inicio, mapa = None, {}
    for i, linha in enumerate(linhas[:10]):
        tentativa = _mapear_colunas(linha)
        if all(c in tentativa for c in OBRIGATORIAS):
            inicio, mapa = i, tentativa
            break
    if inicio is None:
        return False, ("Não encontrei o cabeçalho. A planilha precisa ter as colunas: "
                       + ", ".join(OBRIGATORIAS.values()) + "."), {}

    resultado = {"criados": 0, "repetidos": 0, "erros": []}
    for numero_linha, linha in enumerate(linhas[inicio + 1:], start=inicio + 2):
        celula = lambda campo: texto(linha[mapa[campo]]) if campo in mapa and mapa[campo] < len(linha) else ""
        if not any(texto(c) for c in linha):
            continue
        valor = _valor(celula("valor_unitario"))
        quantidade = _valor(celula("quantidade_total"))
        dados = {
            "fornecedor": celula("fornecedor"),
            "codigos_consignado": ", ".join(_codigo(c) for c in celula("codigos_consignado").replace(";", ",").split(",") if c.strip()),
            "codigos_aghu": ", ".join(_codigo(c) for c in celula("codigos_aghu").replace(";", ",").split(",") if c.strip()),
            "quantidade_total": str(int(quantidade)) if quantidade else "",
            "valor_unitario": f"{valor:.2f}".replace(".", ",") if valor else "",
            "vigencia_inicio": _data_planilha(celula("vigencia_inicio")),
            "vigencia_fim": _data_planilha(celula("vigencia_fim")),
            "numero_processo": _codigo(celula("numero_processo")),
            "numero_pregao": _codigo(celula("numero_pregao")),
            "numero_registro": _codigo(celula("numero_registro")),
            "numero": _codigo(celula("numero")),
            "material": celula("material"),
            "limite_seguranca": _codigo(celula("limite_seguranca")),
            "observacao": f"Importado da planilha {texto(nome_arquivo)}",
        }
        faltando = [rotulo for campo, rotulo in OBRIGATORIAS.items() if not dados[campo]]
        if faltando:
            resultado["erros"].append({"linha": numero_linha, "mensagem": "Falta: " + ", ".join(faltando)})
            continue
        ok_pares, pares_lin = __import__(__package__ + ".consignado_aghu", fromlist=["x"]).resolver_pares(_pares(dados))
        if not ok_pares:
            resultado["erros"].append({"linha": numero_linha, "mensagem": pares_lin})
            continue
        codigos = sorted({a for _, a, _ in pares_lin})
        repetido = db.escalar(
            """SELECT COUNT(*) FROM empenhos e WHERE e.status = 'ativo' AND e.fornecedor = ?
                 AND COALESCE(e.numero, '') = ? AND COALESCE(e.numero_processo, '') = ?
                 AND COALESCE(e.numero_pregao, '') = ? AND COALESCE(e.numero_registro, '') = ?
                 AND e.quantidade_total = ?
                 AND (SELECT GROUP_CONCAT(codigo_aghu) FROM (SELECT codigo_aghu FROM empenho_aghu x
                        WHERE x.id_empenho = e.id_empenho ORDER BY codigo_aghu)) = ?""",
            (dados["fornecedor"], dados["numero"], dados["numero_processo"], dados["numero_pregao"],
             dados["numero_registro"], inteiro(dados["quantidade_total"], 0), ",".join(sorted(codigos))))
        if repetido:
            resultado["repetidos"] += 1
            continue
        ok, retorno = cadastrar(dados, usuario)
        if ok:
            resultado["criados"] += 1
        else:
            resultado["erros"].append({"linha": numero_linha, "mensagem": retorno})

    mensagem = f"{resultado['criados']} empenho(s) cadastrado(s) pela planilha."
    if resultado["repetidos"]:
        mensagem += f" {resultado['repetidos']} já existiam."
    if resultado["erros"]:
        mensagem += f" {len(resultado['erros'])} linha(s) com problema — veja abaixo."
    return True, mensagem, resultado
