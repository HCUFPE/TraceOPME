"""Cálculo dos indicadores.

Todos os números saem das mesmas três tabelas (`unidades`, `eventos`,
`atendimentos`). Como cada movimento vira um evento datado, os tempos de ciclo
são medidos de verdade — não estimados.
"""

import statistics
from datetime import date, timedelta

from .. import db
from ..domain import (
    BAIXADO, DIVERGENCIA, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, EM_SALA,
    ESTOQUE_ATIVO, SEPARADO, TRANSITO_FARMACIA, TRANSITO_RETORNO, TRANSITO_SALA,
    UTILIZADO,
)
from ..indicadores import CATALOGO, Indicador, avaliar, formatar
from ..utils import hoje_iso, texto

TRANSITOS = (TRANSITO_FARMACIA, TRANSITO_SALA, TRANSITO_RETORNO, "transito_almoxarifado")
CONFERENCIAS = ("conferir_farmacia", "conferir_sala", "conferir_retorno")

# Um uso estornado não pode continuar contando como consumo. Este trecho descarta
# todo evento de uso que tenha um estorno posterior para a mesma unidade.
# Exige que o evento de uso esteja com o apelido `e` na consulta.
USO_VALIDO = """NOT EXISTS (
    SELECT 1 FROM eventos estorno
    WHERE estorno.id_unidade = e.id_unidade
      AND estorno.tipo = 'estornar_uso'
      AND estorno.id_evento > e.id_evento
)"""


# =========================================================
# METAS
# =========================================================

def metas_atuais() -> dict[str, dict]:
    """Metas gravadas pelo administrador, com o padrão do catálogo como base."""
    salvas = {m["codigo"]: m for m in db.consultar("SELECT * FROM metas")}
    resultado = {}
    for codigo, ind in CATALOGO.items():
        gravada = salvas.get(codigo)
        if gravada:
            # Existe linha gravada: vale o que o administrador definiu, inclusive
            # deixar em branco de propósito para acompanhar sem semáforo.
            resultado[codigo] = {
                "meta": gravada["meta"],
                "atencao": gravada["atencao"],
                "personalizada": True,
                "atualizado_em": gravada["atualizado_em"],
                "atualizado_por": gravada["atualizado_por"],
            }
        else:
            resultado[codigo] = {
                "meta": ind.meta, "atencao": ind.atencao, "personalizada": False,
                "atualizado_em": None, "atualizado_por": None,
            }
    return resultado


def salvar_meta(codigo: str, meta, atencao, usuario: str) -> tuple[bool, str]:
    if codigo not in CATALOGO:
        return False, "Indicador desconhecido."

    def numero(valor):
        valor = texto(valor).replace(",", ".")
        if valor == "":
            return None
        try:
            return float(valor)
        except ValueError:
            return "erro"

    valor_meta, valor_atencao = numero(meta), numero(atencao)
    if valor_meta == "erro" or valor_atencao == "erro":
        return False, "Informe apenas números."

    indicador = CATALOGO[codigo]
    if valor_meta is not None and valor_atencao is not None:
        if indicador.direcao == "maior" and valor_atencao > valor_meta:
            return False, ("Neste indicador, quanto maior melhor: o limite de atenção "
                           "precisa ser menor ou igual à meta.")
        if indicador.direcao == "menor" and valor_atencao < valor_meta:
            return False, ("Neste indicador, quanto menor melhor: o limite de atenção "
                           "precisa ser maior ou igual à meta.")

    db.executar(
        """INSERT INTO metas (codigo, meta, atencao, atualizado_em, atualizado_por)
           VALUES (?,?,?,?,?)
           ON CONFLICT(codigo) DO UPDATE SET
             meta = excluded.meta, atencao = excluded.atencao,
             atualizado_em = excluded.atualizado_em, atualizado_por = excluded.atualizado_por""",
        (codigo, valor_meta, valor_atencao, db.agora(), usuario),
    )
    return True, f"Meta de “{indicador.nome}” atualizada."


def restaurar_padrao(codigo: str) -> tuple[bool, str]:
    if codigo not in CATALOGO:
        return False, "Indicador desconhecido."
    db.executar("DELETE FROM metas WHERE codigo = ?", (codigo,))
    return True, f"Meta de “{CATALOGO[codigo].nome}” voltou ao valor sugerido."


# =========================================================
# FILTRO POR UNIDADE (v18.15)
#
# "Separar Bloco e Hemodinâmica" não é um corte só do atendimento nem só do
# estoque: uma unidade física pertence ao Bloco quando está na farmácia do
# Bloco OU quando está vinculada a um procedimento do Bloco (o mesmo para a
# Hemodinâmica). Os três fragmentos abaixo aplicam essa mesma regra às três
# formas de consulta do arquivo: a tabela `unidades`, a tabela `eventos` (pela
# unidade física do evento) e a tabela `atendimentos`.
# =========================================================

def chave_unidade(unidade: str) -> str:
    """Devolve a unidade válida em MAIÚSCULA, ou "" (= todas)."""
    from ..config import UNIDADES_ATIVAS
    u = texto(unidade).strip().upper()
    return u if u in UNIDADES_ATIVAS else ""


def unidades_disponiveis() -> list[dict]:
    """Opções do seletor das telas de indicadores."""
    from ..config import UNIDADES_ATIVAS
    return [{"chave": chave, "rotulo": dados["rotulo"]} for chave, dados in UNIDADES_ATIVAS.items()]


def _f_unidades(alias: str, unidade: str) -> str:
    """Fragmento ` AND (...)` para a tabela `unidades` (alias vazio = tabela sem apelido)."""
    u = chave_unidade(unidade)
    if not u:
        return ""
    from ..config import farmacia_da_unidade
    farmacia = farmacia_da_unidade(u)
    # Sem apelido, a coluna PRECISA ser qualificada pelo nome da tabela: `fa.id_atendimento
    # = id_atendimento` viraria uma comparação da subconsulta consigo mesma (sempre
    # verdadeira), porque `atendimentos` também tem a coluna `id_atendimento`.
    pre = f"{alias}." if alias else "unidades."
    return (f" AND (UPPER(COALESCE({pre}farmacia,'')) = '{farmacia}'"
            f" OR EXISTS (SELECT 1 FROM atendimentos fa WHERE fa.id_atendimento = {pre}id_atendimento"
            f" AND UPPER(fa.unidade) = '{u}'))")


def _f_eventos(alias: str, unidade: str) -> str:
    """Fragmento para `eventos`: o item do evento pertence à unidade escolhida."""
    u = chave_unidade(unidade)
    if not u:
        return ""
    pre = f"{alias}." if alias else "eventos."
    return (f" AND EXISTS (SELECT 1 FROM unidades fu WHERE fu.id_unidade = {pre}id_unidade"
            + _f_unidades("fu", u) + ")")


def _f_atendimentos(alias: str, unidade: str) -> str:
    u = chave_unidade(unidade)
    pre = f"{alias}." if alias else "atendimentos."
    return f" AND UPPER({pre}unidade) = '{u}'" if u else ""


def rotulo_do_filtro(unidade: str) -> str:
    from ..config import rotulo_unidade
    u = chave_unidade(unidade)
    return rotulo_unidade(u) if u else "Bloco Cirúrgico e Hemodinâmica"


# =========================================================
# APOIO
# =========================================================

def periodo_padrao(dias: int = 30) -> tuple[str, str]:
    return (date.today() - timedelta(days=dias)).isoformat(), hoje_iso()


def _duracoes_horas(tipo_inicio: str, tipo_fim: str, inicio: str, fim: str,
                    unidade: str = "") -> list[float]:
    """Horas entre um evento e a próxima ocorrência do evento seguinte, por unidade.

    Considera o par concluído dentro do período (filtra pela data do evento final),
    para que o indicador reflita o que foi finalizado na janela analisada.
    """
    linhas = db.consultar(
        """SELECT (julianday(fim) - julianday(inicio)) * 24 AS horas
           FROM (
             SELECT e1.data_evento AS inicio,
                    (SELECT MIN(e2.data_evento) FROM eventos e2
                      WHERE e2.id_unidade = e1.id_unidade AND e2.tipo = ?
                        AND e2.id_evento > e1.id_evento) AS fim
             FROM eventos e1
             WHERE e1.tipo = ? AND e1.id_unidade IS NOT NULL
               {filtro}
           )
           WHERE fim IS NOT NULL AND date(fim) BETWEEN date(?) AND date(?)""".format(
            filtro=_f_eventos("e1", unidade)),
        (tipo_fim, tipo_inicio, inicio, fim),
    )
    return [l["horas"] for l in linhas if l["horas"] is not None and l["horas"] >= 0]


def _estatisticas(valores: list[float]) -> dict:
    if not valores:
        return {"media": None, "mediana": None, "p90": None, "quantidade": 0,
                "minimo": None, "maximo": None}
    ordenados = sorted(valores)
    indice_p90 = min(len(ordenados) - 1, int(round(0.9 * (len(ordenados) - 1))))
    return {
        "media": round(statistics.fmean(ordenados), 2),
        "mediana": round(statistics.median(ordenados), 2),
        "p90": round(ordenados[indice_p90], 2),
        "minimo": round(ordenados[0], 2),
        "maximo": round(ordenados[-1], 2),
        "quantidade": len(ordenados),
    }


def _contar_utilizados(inicio: str, fim: str, unidade: str = "") -> int:
    return db.escalar(
        f"""SELECT COUNT(*) FROM eventos e
            WHERE e.tipo = 'registrar_uso'
              AND date(e.data_evento) BETWEEN date(?) AND date(?)
              AND {USO_VALIDO}{_f_eventos("e", unidade)}""",
        (inicio, fim),
    )


def _contar_eventos(tipos: tuple[str, ...], inicio: str, fim: str, unidade: str = "") -> int:
    marcadores = ",".join("?" for _ in tipos)
    return db.escalar(
        f"""SELECT COUNT(*) FROM eventos e WHERE e.tipo IN ({marcadores})
            AND date(e.data_evento) BETWEEN date(?) AND date(?){_f_eventos("e", unidade)}""",
        (*tipos, inicio, fim),
    )


def _percentual(parte: float, total: float) -> float | None:
    if not total:
        return None
    return round(100 * parte / total, 1)


def _ativos_sql() -> str:
    return "(" + ",".join(f"'{s}'" for s in ESTOQUE_ATIVO) + ")"


# =========================================================
# CÁLCULO DE CADA INDICADOR
# =========================================================

def calcular_valores(inicio: str, fim: str, unidade: str = "") -> dict[str, float | None]:
    """v18.15: `unidade` vazia = hospital todo; "BLOCO CIRURGICO"/"HEMODINAMICA" separam."""
    ativos = _ativos_sql()
    fu = _f_unidades("u", unidade)          # consultas com a tabela unidades apelidada de u
    fun = _f_unidades("", unidade)          # consultas em unidades sem apelido
    fe = _f_eventos("e", unidade)           # consultas em eventos (apelido e)
    valores: dict[str, float | None] = {}

    # ---- fluxo ----
    for codigo, (de, para) in {
        "tempo_conferencia_farmacia": ("enviar_farmacia", "conferir_farmacia"),
        "tempo_separacao_envio": ("separar", "enviar_sala"),
        "tempo_conferencia_sala": ("enviar_sala", "conferir_sala"),
        "tempo_ate_uso": ("conferir_sala", "registrar_uso"),
        "tempo_retorno": ("devolver_farmacia", "conferir_retorno"),
    }.items():
        valores[codigo] = _estatisticas(_duracoes_horas(de, para, inicio, fim, unidade))["media"]

    ciclo = db.consultar(
        f"""SELECT (julianday(e.data_evento) - julianday(u.criado_em)) AS dias
           FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
             AND {USO_VALIDO}{fu}""",
        (inicio, fim),
    )
    dias_ciclo = [l["dias"] for l in ciclo if l["dias"] is not None and l["dias"] >= 0]
    valores["ciclo_total"] = round(statistics.fmean(dias_ciclo), 1) if dias_ciclo else None

    valores["itens_parados"] = db.escalar(
        f"""SELECT COUNT(*) FROM unidades WHERE status IN {str(TRANSITOS)}
            AND julianday('now') - julianday(atualizado_em) > 2{fun}"""
    )
    valores["backlog_atual"] = db.escalar(
        f"""SELECT COUNT(*) FROM unidades
            WHERE status IN {str(TRANSITOS + (DIVERGENCIA,))}{fun}"""
    )

    conferencias_no_prazo = 0
    conferencias_total = 0
    for de, para in (("enviar_farmacia", "conferir_farmacia"),
                     ("enviar_sala", "conferir_sala"),
                     ("devolver_farmacia", "conferir_retorno")):
        horas = _duracoes_horas(de, para, inicio, fim, unidade)
        conferencias_total += len(horas)
        conferencias_no_prazo += sum(1 for h in horas if h <= 24)
    valores["conferencia_no_prazo"] = _percentual(conferencias_no_prazo, conferencias_total)

    # ---- desperdício ----
    utilizados = _contar_utilizados(inicio, fim, unidade)
    devolvidos = _contar_eventos(("conferir_retorno",), inicio, fim, unidade)
    enviados_sala = _contar_eventos(("enviar_sala",), inicio, fim, unidade)

    valores["taxa_aproveitamento"] = _percentual(utilizados, utilizados + devolvidos)
    valores["taxa_devolucao"] = _percentual(
        _contar_eventos(("devolver_farmacia",), inicio, fim, unidade), enviados_sala)

    valores["itens_vencidos"] = db.escalar(
        f"""SELECT COUNT(*) FROM unidades WHERE status IN {ativos}
            AND dVal IS NOT NULL AND dVal <> '' AND date(dVal) < date('now'){fun}""")
    valores["valor_vencido"] = round(db.escalar(
        f"""SELECT COALESCE(SUM(vUnCom),0) FROM unidades WHERE status IN {ativos}
            AND dVal IS NOT NULL AND dVal <> '' AND date(dVal) < date('now'){fun}"""), 2)
    valores["valor_a_vencer_90"] = round(db.escalar(
        f"""SELECT COALESCE(SUM(vUnCom),0) FROM unidades WHERE status IN {ativos}
            AND dVal IS NOT NULL AND dVal <> ''
            AND date(dVal) >= date('now')
            AND julianday(dVal) - julianday('now') <= 90{fun}"""), 2)

    baixados = _contar_eventos(("baixar",), inicio, fim, unidade)
    movimentados = db.escalar(
        f"""SELECT COUNT(DISTINCT e.id_unidade) FROM eventos e
            WHERE date(e.data_evento) BETWEEN date(?) AND date(?) AND e.id_unidade IS NOT NULL{fe}""",
        (inicio, fim))
    valores["taxa_perda"] = _percentual(baixados, movimentados)

    valores["separacao_ociosa"] = db.escalar(
        f"""SELECT COUNT(*) FROM unidades WHERE status = '{SEPARADO}'
            AND julianday('now') - julianday(atualizado_em) > 2{fun}""")
    valores["estoque_parado"] = db.escalar(
        f"""SELECT COUNT(*) FROM unidades WHERE status IN {ativos}
            AND julianday('now') - julianday(COALESCE(atualizado_em, criado_em)) > 180{fun}""")

    # ---- financeiro ----
    valores["valor_consumido"] = round(db.escalar(
        f"""SELECT COALESCE(SUM(u.vUnCom),0) FROM eventos e
           JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
             AND {USO_VALIDO}{fu}""",
        (inicio, fim)), 2)

    cirurgias_com_consumo = db.escalar(
        f"""SELECT COUNT(DISTINCT e.id_atendimento) FROM eventos e
           WHERE e.tipo = 'registrar_uso' AND e.id_atendimento IS NOT NULL
             AND date(e.data_evento) BETWEEN date(?) AND date(?) AND {USO_VALIDO}{fe}""",
        (inicio, fim))
    valores["custo_medio_cirurgia"] = (
        round(valores["valor_consumido"] / cirurgias_com_consumo, 2)
        if cirurgias_com_consumo else None)
    valores["itens_por_cirurgia"] = (
        round(utilizados / cirurgias_com_consumo, 1) if cirurgias_com_consumo else None)

    valores["valor_consignado"] = round(db.escalar(
        f"""SELECT COALESCE(SUM(vUnCom),0) FROM unidades
            WHERE status IN {ativos} AND tipo_entrada = 'consignado'{fun}"""), 2)
    valores["valor_estoque_total"] = round(db.escalar(
        f"SELECT COALESCE(SUM(vUnCom),0) FROM unidades WHERE status IN {ativos}{fun}"), 2)

    dias_periodo = max(1, (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1)
    consumo_diario = utilizados / dias_periodo
    em_estoque = db.escalar(
        f"""SELECT COUNT(*) FROM unidades
            WHERE status IN ('{EM_ESTOQUE_RECEBIMENTO}','{EM_ESTOQUE_FARMACIA}'){fun}""")
    valores["giro_estoque"] = round(em_estoque / consumo_diario, 1) if consumo_diario else None

    # ---- qualidade ----
    divergencias = _contar_eventos(
        ("marcar_divergencia", "conferir_farmacia_pendencia", "conferir_sala_pendencia",
         "conferir_retorno_pendencia"), inicio, fim, unidade)
    conferidos = _contar_eventos(CONFERENCIAS, inicio, fim, unidade)
    valores["taxa_divergencia"] = _percentual(divergencias, conferidos + divergencias)

    completos = db.escalar(
        f"""SELECT COUNT(*) FROM unidades WHERE status IN {ativos}
            AND COALESCE(nLote,'') <> '' AND COALESCE(dVal,'') <> ''
            AND COALESCE(codigo_aghu,'') <> '' AND COALESCE(marca_fabricante,'') <> ''{fun}""")
    total_ativos = db.escalar(f"SELECT COUNT(*) FROM unidades WHERE status IN {ativos}{fun}")
    valores["completude_cadastro"] = _percentual(completos, total_ativos)

    usados_ok = db.escalar(
        f"""SELECT COUNT(*) FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
             AND COALESCE(u.nLote,'') <> '' AND COALESCE(u.dVal,'') <> '' AND {USO_VALIDO}{fu}""",
        (inicio, fim))
    valores["rastreabilidade_uso"] = _percentual(usados_ok, utilizados)

    valores["correcoes_cadastro"] = _contar_eventos(("correcao",), inicio, fim, unidade)

    valores["usos_fora_do_fluxo"] = db.escalar(
        f"""SELECT COUNT(*) FROM eventos e
           WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
             AND {USO_VALIDO}{fe}
             AND NOT EXISTS (SELECT 1 FROM eventos c WHERE c.id_unidade = e.id_unidade
                               AND c.tipo = 'conferir_sala' AND c.id_evento < e.id_evento)""",
        (inicio, fim))

    base = _base_cancelamento(inicio, fim, unidade)
    valores["taxa_cancelamento"] = _percentual(base["cancelados"], base["previstos"])

    from . import usos_sem_dispensacao
    sem_disp = usos_sem_dispensacao.taxa_e_ciencia(inicio, fim, unidade=unidade)
    valores["taxa_uso_sem_dispensacao"] = _percentual(sem_disp["casos"],
                                                     _contar_utilizados(inicio, fim, unidade))
    valores["ciencia_uso_sem_dispensacao"] = _percentual(sem_disp["no_prazo"], sem_disp["casos"])

    # v17 (out/2026)
    valores["procedimentos_cancelados"] = base["cancelados"]
    valores["procedimentos_criados"] = db.escalar(
        f"""SELECT COUNT(*) FROM atendimentos a
            WHERE COALESCE(a.origem,'agenda') = 'manual'
              AND date(a.data_procedimento) BETWEEN date(?) AND date(?)
              AND {_filtro_previstos()}{_f_atendimentos("a", unidade)}""",
        (inicio, fim))
    util = utilizacao_dispensado(inicio, fim, unidade)
    valores["taxa_utilizacao_dispensado"] = _percentual(util["usados"], util["dispensados"])
    valores["pendentes_ciencia_farmacia"] = pendentes_ciencia_farmacia(unidade)["total"]
    leituras = (_contar_utilizados(inicio, fim, unidade)
                + _contar_eventos(("dispensar_sala",), inicio, fim, unidade))
    valores["taxa_selecao_manual"] = _percentual(
        _contar_eventos(("selecao_manual",), inicio, fim, unidade), leituras)
    valores["materiais_nao_cadastrados"] = _contar_eventos(("uso_nao_cadastrado",), inicio, fim, unidade)

    return valores


def utilizacao_dispensado(inicio: str, fim: str, unidade: str = "") -> dict:
    """v17 — itens dispensados no período e quantos foram usados no mesmo paciente."""
    linha = db.consultar_um(
        f"""SELECT COUNT(*) AS dispensados,
                  SUM(CASE WHEN u.status = 'utilizado' AND u.id_atendimento = d.id_atendimento
                           THEN 1 ELSE 0 END) AS usados
           FROM dispensacao_itens i
           JOIN dispensacoes d ON d.id_dispensacao = i.id_dispensacao
           JOIN unidades u ON u.id_unidade = i.id_unidade
           JOIN atendimentos a ON a.id_atendimento = d.id_atendimento
           WHERE i.situacao <> 'removido' AND date(i.bipado_em) BETWEEN date(?) AND date(?)
             -- só procedimento já fechado pela sala: em andamento ainda pode usar o material
             AND (a.status = 'encerrado' OR COALESCE(a.uso_finalizado_em,'') <> '')
             {_f_atendimentos("a", unidade)}""",
        (inicio, fim))
    return {"dispensados": linha["dispensados"] or 0, "usados": linha["usados"] or 0}


def pendentes_ciencia_farmacia(unidade: str = "") -> dict:
    """v17 — o que espera a ciência da farmácia agora (v18.15: por unidade)."""
    existe_unidade = _f_unidades("fu", unidade)
    filtro_uso = (f" AND EXISTS (SELECT 1 FROM unidades fu WHERE fu.id_unidade = s.id_unidade"
                  f"{existe_unidade})" if existe_unidade else "")
    filtro_dev = (f" AND EXISTS (SELECT 1 FROM unidades fu WHERE fu.id_unidade = i.id_unidade"
                  f"{existe_unidade})" if existe_unidade else "")
    usos = db.escalar(
        f"SELECT COUNT(*) FROM usos_sem_dispensacao s WHERE s.situacao = 'pendente'{filtro_uso}")
    lista = db.escalar(
        f"""SELECT COALESCE(SUM(CASE WHEN i.tipo = 'caixa' THEN COALESCE(i.quantidade, 0) ELSE 1 END), 0)
            FROM devolucao_itens i JOIN devolucoes d ON d.id_devolucao = i.id_devolucao
            WHERE i.situacao = 'pendente' AND d.status = 'pendente'{filtro_dev}""")
    return {"usos_sem_dispensacao": usos or 0, "nao_utilizados": lista or 0,
            "total": (usos or 0) + (lista or 0)}


# ---- v17: cancelamento de procedimentos ----

def _filtro_previstos() -> str:
    from ..config import UNIDADES_ATIVAS
    unidades = ",".join(f"'{u}'" for u in UNIDADES_ATIVAS)
    return f"""a.unidade IN ({unidades})
        AND (COALESCE(a.opme_solicitado,'') <> '' OR COALESCE(a.origem,'agenda') = 'manual'
             OR EXISTS (SELECT 1 FROM unidades u WHERE u.id_atendimento = a.id_atendimento))"""


def _base_cancelamento(inicio: str, fim: str, unidade: str = "") -> dict:
    linha = db.consultar_um(
        f"""SELECT COUNT(*) AS previstos,
                   SUM(CASE WHEN a.status = 'cancelado' THEN 1 ELSE 0 END) AS cancelados
            FROM atendimentos a
            WHERE date(a.data_procedimento) BETWEEN date(?) AND date(?)
              AND {_filtro_previstos()}{_f_atendimentos("a", unidade)}""", (inicio, fim))
    return {"previstos": linha["previstos"] or 0, "cancelados": linha["cancelados"] or 0}


def cancelamentos(inicio: str, fim: str, unidade: str = "") -> dict:
    """Detalhe do indicador: por motivo, por unidade/especialidade e a lista."""
    from ..config import rotulo_unidade
    base = _base_cancelamento(inicio, fim, unidade)
    filtro = (f"""date(a.data_procedimento) BETWEEN date(?) AND date(?) AND {_filtro_previstos()}"""
              + _f_atendimentos("a", unidade))
    por_motivo = db.consultar(
        f"""SELECT a.motivo_cancelamento AS motivo, COUNT(*) AS quantidade
            FROM atendimentos a WHERE a.status = 'cancelado' AND {filtro}
            GROUP BY a.motivo_cancelamento ORDER BY quantidade DESC""", (inicio, fim))
    por_grupo = db.consultar(
        f"""SELECT a.unidade, a.especialidade, COUNT(*) AS previstos,
                   SUM(CASE WHEN a.status = 'cancelado' THEN 1 ELSE 0 END) AS cancelados
            FROM atendimentos a WHERE {filtro}
            GROUP BY a.unidade, a.especialidade
            HAVING cancelados > 0 ORDER BY cancelados DESC""", (inicio, fim))
    for linha in por_grupo:
        linha["rotulo_unidade"] = rotulo_unidade(linha["unidade"])
        linha["taxa"] = _percentual(linha["cancelados"], linha["previstos"])
    lista = db.consultar(
        f"""SELECT a.id_atendimento, a.data_procedimento, a.unidade, a.sala, a.prontuario,
                   a.especialidade, a.motivo_cancelamento, a.detalhe_cancelamento,
                   a.cancelado_por, a.cancelado_em
            FROM atendimentos a WHERE a.status = 'cancelado' AND {filtro}
            ORDER BY a.data_procedimento DESC, a.unidade, a.sala LIMIT 200""", (inicio, fim))
    for linha in lista:
        linha["rotulo_unidade"] = rotulo_unidade(linha["unidade"])
    return base | {"taxa": _percentual(base["cancelados"], base["previstos"]),
                   "por_motivo": por_motivo, "por_grupo": por_grupo, "lista": lista}


def montar(inicio: str, fim: str, grupo: str = "", unidade: str = "") -> list[dict]:
    """Indicadores prontos para a tela: valor, formatação, meta e semáforo."""
    valores = calcular_valores(inicio, fim, unidade)
    metas = metas_atuais()
    resultado = []
    for codigo, indicador in CATALOGO.items():
        if grupo and indicador.grupo != grupo:
            continue
        valor = valores.get(codigo)
        configuracao = metas[codigo]
        resultado.append({
            "indicador": indicador,
            "codigo": codigo,
            "valor": valor,
            "texto": formatar(indicador, valor),
            "meta": configuracao["meta"],
            "meta_texto": formatar(indicador, configuracao["meta"]),
            "atencao": configuracao["atencao"],
            "personalizada": configuracao["personalizada"],
            "situacao": avaliar(indicador, valor, configuracao["meta"], configuracao["atencao"]),
        })
    return resultado


# =========================================================
# DETALHAMENTOS (as tabelas de cada aba)
# =========================================================

def tempos_por_etapa(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    """v17: uma etapa só — da entrada no almoxarifado ao uso no paciente, em horas."""
    horas = []
    for entrada in ("entrada_nf", "entrada_manual"):
        horas += _duracoes_horas(entrada, "registrar_uso", inicio, fim, unidade)
    estatisticas = _estatisticas(horas)
    return [{
        "etapa": "Entrada no almoxarifado → uso no paciente",
        "codigo": "ciclo_total", **estatisticas,
        "meta": None, "situacao": "",
    }]


def gargalos_abertos(unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT u.status, COUNT(*) AS quantidade,
                   ROUND(AVG(julianday('now') - julianday(u.atualizado_em)), 1) AS dias_medio,
                   MAX(CAST(julianday('now') - julianday(u.atualizado_em) AS INTEGER)) AS pior_caso
            FROM unidades u
            WHERE u.status IN {str(TRANSITOS + (SEPARADO, DIVERGENCIA))}{_f_unidades("u", unidade)}
            GROUP BY u.status ORDER BY quantidade DESC""")


def produtividade(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT e.usuario AS usuario, COUNT(*) AS movimentos,
                   COUNT(DISTINCT date(e.data_evento)) AS dias_ativos,
                   ROUND(CAST(COUNT(*) AS REAL) / COUNT(DISTINCT date(e.data_evento)), 1) AS media_dia
            FROM eventos e
            WHERE date(e.data_evento) BETWEEN date(?) AND date(?)
              AND e.usuario IS NOT NULL AND e.usuario <> ''{_f_eventos("e", unidade)}
            GROUP BY e.usuario ORDER BY movimentos DESC LIMIT 20""",
        (inicio, fim))


def aproveitamento_por_especialidade(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT a.especialidade,
                   SUM(CASE WHEN e.tipo = 'registrar_uso' THEN 1 ELSE 0 END) AS utilizados,
                   SUM(CASE WHEN e.tipo = 'devolver_farmacia' THEN 1 ELSE 0 END) AS devolvidos,
                   SUM(CASE WHEN e.tipo = 'enviar_sala' THEN 1 ELSE 0 END) AS enviados
            FROM eventos e JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
            WHERE e.tipo IN ('registrar_uso','devolver_farmacia','enviar_sala')
              AND date(e.data_evento) BETWEEN date(?) AND date(?)
              AND (e.tipo <> 'registrar_uso' OR {USO_VALIDO}){_f_atendimentos("a", unidade)}
            GROUP BY a.especialidade ORDER BY enviados DESC""",
        (inicio, fim))


def produtos_mais_devolvidos(inicio: str, fim: str, limite: int = 15, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT u.xProd, u.fornecedor,
                  SUM(CASE WHEN e.tipo = 'devolver_farmacia' THEN 1 ELSE 0 END) AS devolvidos,
                  SUM(CASE WHEN e.tipo = 'enviar_sala' THEN 1 ELSE 0 END) AS enviados
           FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo IN ('devolver_farmacia','enviar_sala')
             AND date(e.data_evento) BETWEEN date(?) AND date(?){_f_unidades("u", unidade)}
           GROUP BY u.xProd, u.fornecedor
           HAVING devolvidos > 0 ORDER BY devolvidos DESC LIMIT ?""",
        (inicio, fim, limite))


def vencimentos_por_faixa(unidade: str = "") -> list[dict]:
    ativos = _ativos_sql()
    fun = _f_unidades("", unidade)
    faixas = [
        ("Já vencidos", "julianday(dVal) - julianday('now') < 0"),
        ("Vence em até 30 dias", "julianday(dVal) - julianday('now') BETWEEN 0 AND 30"),
        ("31 a 90 dias", "julianday(dVal) - julianday('now') BETWEEN 31 AND 90"),
        ("91 a 180 dias", "julianday(dVal) - julianday('now') BETWEEN 91 AND 180"),
        ("Mais de 180 dias", "julianday(dVal) - julianday('now') > 180"),
    ]
    linhas = []
    for nome, condicao in faixas:
        linha = db.consultar_um(
            f"""SELECT COUNT(*) AS quantidade, COALESCE(SUM(vUnCom),0) AS valor
                FROM unidades WHERE status IN {ativos}
                  AND dVal IS NOT NULL AND dVal <> '' AND {condicao}{fun}""")
        linhas.append({"faixa": nome, **(linha or {"quantidade": 0, "valor": 0})})
    sem_validade = db.consultar_um(
        f"""SELECT COUNT(*) AS quantidade, COALESCE(SUM(vUnCom),0) AS valor
            FROM unidades WHERE status IN {ativos} AND COALESCE(dVal,'') = ''{fun}""")
    linhas.append({"faixa": "Sem validade cadastrada", **(sem_validade or {"quantidade": 0, "valor": 0})})
    return linhas


def baixas_por_motivo(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT COALESCE(NULLIF(TRIM(e.motivo),''), 'não informado') AS motivo,
                  COUNT(*) AS quantidade,
                  COALESCE(SUM(u.vUnCom),0) AS valor
           FROM eventos e LEFT JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo IN ('baixar','marcar_divergencia')
             AND date(e.data_evento) BETWEEN date(?) AND date(?){_f_unidades("u", unidade)}
           GROUP BY motivo ORDER BY quantidade DESC LIMIT 20""",
        (inicio, fim))


def consumo_por(dimensao: str, inicio: str, fim: str, limite: int = 20, unidade: str = "") -> list[dict]:
    colunas = {
        "especialidade": "a.especialidade",
        "sala": "a.sala",
        "fornecedor": "u.fornecedor",
        "tipo_entrada": "u.tipo_entrada",
        "produto": "u.xProd",
    }
    coluna = colunas.get(dimensao, "a.especialidade")
    return db.consultar(
        f"""SELECT COALESCE(NULLIF({coluna},''),'não informado') AS chave,
                   COUNT(*) AS quantidade,
                   COALESCE(SUM(u.vUnCom),0) AS valor,
                   COUNT(DISTINCT e.id_atendimento) AS cirurgias
            FROM eventos e
            JOIN unidades u ON u.id_unidade = e.id_unidade
            LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
            WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
              AND {USO_VALIDO}{_f_unidades("u", unidade)}
            GROUP BY chave ORDER BY valor DESC LIMIT ?""",
        (inicio, fim, limite))


def evolucao_mensal(meses: int = 12, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT strftime('%Y-%m', e.data_evento) AS mes,
                  COUNT(*) AS utilizados,
                  COALESCE(SUM(u.vUnCom),0) AS valor,
                  COUNT(DISTINCT e.id_atendimento) AS cirurgias
           FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo = 'registrar_uso' AND {USO_VALIDO}{_f_unidades("u", unidade)}
             AND e.data_evento >= date('now', ?)
           GROUP BY mes ORDER BY mes""",
        (f"-{meses} months",))


def cobertura_por_produto(inicio: str, fim: str, limite: int = 20, unidade: str = "") -> list[dict]:
    dias = max(1, (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1)
    fu, fun = _f_unidades("u", unidade), _f_unidades("", unidade)
    # O SQLite não aceita expressão no ORDER BY de um UNION, por isso o SELECT externo.
    return db.consultar(
        f"""SELECT * FROM (
              WITH consumo AS (
                SELECT u.xProd, COUNT(*) AS usados
                FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
                WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
                  AND {USO_VALIDO}{fu}
                GROUP BY u.xProd
              ),
              estoque AS (
                SELECT xProd, COUNT(*) AS disponivel FROM unidades
                WHERE status IN ('{EM_ESTOQUE_RECEBIMENTO}','{EM_ESTOQUE_FARMACIA}'){fun}
                GROUP BY xProd
              )
              SELECT c.xProd AS xProd,
                     COALESCE(s.disponivel,0) AS disponivel,
                     c.usados AS usados,
                     ROUND(COALESCE(s.disponivel,0) / (CAST(c.usados AS REAL) / {dias}), 0)
                       AS dias_cobertura
              FROM consumo c LEFT JOIN estoque s ON s.xProd = c.xProd
              UNION ALL
              SELECT s.xProd, s.disponivel, 0, NULL FROM estoque s
              WHERE s.xProd NOT IN (SELECT xProd FROM consumo)
            )
            ORDER BY (dias_cobertura IS NULL), dias_cobertura LIMIT ?""",
        (inicio, fim, limite))


def divergencias_por_fornecedor(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT COALESCE(NULLIF(u.fornecedor,''),'não informado') AS fornecedor,
                  COUNT(*) AS divergencias
           FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo IN ('marcar_divergencia','conferir_farmacia_pendencia',
                            'conferir_sala_pendencia','conferir_retorno_pendencia')
             AND date(e.data_evento) BETWEEN date(?) AND date(?){_f_unidades("u", unidade)}
           GROUP BY fornecedor ORDER BY divergencias DESC LIMIT 15""",
        (inicio, fim))


def problemas_na_sala(inicio: str, fim: str, unidade: str = "") -> dict:
    """v18.4.7: material com problema registrado na sala (caiu, danificado, defeito…).

    Conta a última sinalização de cada unidade no período, para a mesma unidade
    corrigida duas vezes não contar em dobro."""
    base = """FROM eventos e
              JOIN (SELECT id_unidade, MAX(id_evento) AS ultimo FROM eventos
                    WHERE tipo = 'avaria_sinalizada' AND date(data_evento) BETWEEN date(?) AND date(?)
                    GROUP BY id_unidade) x ON x.ultimo = e.id_evento
              JOIN unidades u ON u.id_unidade = e.id_unidade
              LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
              WHERE 1 = 1""" + _f_unidades("u", unidade)
    p = (inicio, fim)
    desc = "COALESCE(NULLIF(u.descritivo_hospital,''), u.xProd)"
    return {
        "total": db.escalar(f"SELECT COUNT(*) {base}", p) or 0,
        "por_motivo": db.consultar(f"""SELECT e.motivo, COUNT(*) AS qtd {base}
                                       GROUP BY e.motivo ORDER BY qtd DESC""", p),
        "por_material": db.consultar(f"""SELECT u.codigo_aghu, {desc} AS descricao,
                                                COALESCE(NULLIF(u.marca_fabricante,''),'—') AS marca,
                                                COALESCE(NULLIF(u.fornecedor,''),'não informado') AS fornecedor,
                                                COUNT(*) AS qtd,
                                                GROUP_CONCAT(DISTINCT e.motivo) AS motivos {base}
                                         GROUP BY u.codigo_aghu, descricao ORDER BY qtd DESC LIMIT 15""", p),
        "por_fornecedor": db.consultar(f"""SELECT COALESCE(NULLIF(u.fornecedor,''),'não informado') AS fornecedor,
                                                  COUNT(*) AS qtd {base}
                                           GROUP BY fornecedor ORDER BY qtd DESC LIMIT 10""", p),
        "por_sala": db.consultar(f"""SELECT COALESCE(a.unidade,'') AS unidade, COALESCE(a.sala,'—') AS sala,
                                            COUNT(*) AS qtd {base}
                                     GROUP BY a.unidade, a.sala ORDER BY qtd DESC LIMIT 10""", p),
        "ultimos": db.consultar(f"""SELECT e.data_evento, e.motivo, e.observacao, e.usuario, u.id_unidade,
                                           u.codigo_aghu, {desc} AS descricao, u.nLote, a.prontuario, a.sala
                                    {base} ORDER BY e.data_evento DESC LIMIT 30""", p),
    }


def completude_por_campo(unidade: str = "") -> list[dict]:
    ativos = _ativos_sql()
    fun = _f_unidades("", unidade)
    campos = [("Lote", "nLote"), ("Validade", "dVal"), ("Código AGHU", "codigo_aghu"),
              ("Marca/Fabricante", "marca_fabricante"), ("Fornecedor", "fornecedor"),
              ("Nota fiscal", "numero_nf"), ("Nº de série", "numero_serie")]
    total = db.escalar(f"SELECT COUNT(*) FROM unidades WHERE status IN {ativos}{fun}")
    linhas = []
    for nome, coluna in campos:
        preenchidos = db.escalar(
            f"""SELECT COUNT(*) FROM unidades WHERE status IN {ativos}
                AND COALESCE({coluna},'') <> ''{fun}""")
        linhas.append({
            "campo": nome, "preenchidos": preenchidos, "total": total,
            "faltando": total - preenchidos,
            "percentual": _percentual(preenchidos, total) or 0,
        })
    return linhas


def itens_sem_conferencia_sala(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    return db.consultar(
        f"""SELECT u.id_unidade, u.xProd, u.nLote, a.prontuario, a.sala,
                  e.data_evento, e.usuario
           FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
           WHERE e.tipo = 'registrar_uso' AND date(e.data_evento) BETWEEN date(?) AND date(?)
             AND {USO_VALIDO}{_f_unidades("u", unidade)}
             AND NOT EXISTS (SELECT 1 FROM eventos c WHERE c.id_unidade = e.id_unidade
                               AND c.tipo = 'conferir_sala' AND c.id_evento < e.id_evento)
           ORDER BY e.data_evento DESC LIMIT 50""",
        (inicio, fim))


# =========================================================
# EXPORTAÇÃO
# =========================================================

def exportar(inicio: str, fim: str, unidade: str = "") -> list[dict]:
    """Uma linha por indicador, pronta para planilha."""
    from ..indicadores import GRUPOS
    linhas = []
    for item in montar(inicio, fim, unidade=unidade):
        indicador = item["indicador"]
        linhas.append({
            "grupo": GRUPOS[indicador.grupo][0],
            "indicador": indicador.nome,
            "valor": item["valor"],
            "unidade": indicador.unidade,
            "meta": item["meta"],
            "limite_atencao": item["atencao"],
            "situacao": item["situacao"],
            "periodo": f"{inicio} a {fim}",
            "local": rotulo_do_filtro(unidade),
            "como_e_calculado": indicador.formula,
        })
    return linhas
