"""Painel de situação, rastreabilidade e exportações."""

import csv
import io

from ..config import FARMACIAS, rotulo_farmacia
from .. import db
from ..config import DIAS_ALERTA_VALIDADE, UNIDADES_ATIVAS
from ..domain import (
    DIVERGENCIA, EM_ESTOQUE_FARMACIA, EM_ESTOQUE_RECEBIMENTO, EM_SALA, ESTADOS,
    ESTOQUE_ATIVO, SEPARADO, TRANSITO_FARMACIA, TRANSITO_RETORNO, TRANSITO_SALA,
    UTILIZADO, rotulo,
)
from ..utils import data_br, data_hora_br, data_iso, hoje_iso, texto
from . import empenhos


def contagem_por_status(farmacia: str = "") -> dict[str, int]:
    """Quantidade por situação. Com `farmacia`, só o estoque daquela farmácia.

    As duas farmácias satélites têm estoques separados, então os números da
    tela da farmácia precisam ser os dela, não a soma das duas.
    """
    filtro, params = ("", [])
    if texto(farmacia):
        filtro, params = (" WHERE farmacia = ?", [texto(farmacia)])
    linhas = db.consultar(
        f"SELECT status, COUNT(*) AS total FROM unidades{filtro} GROUP BY status", params)
    return {l["status"]: l["total"] for l in linhas}


def painel() -> dict:
    contagem = contagem_por_status()

    # v17: sem farmácia, kit nem trânsito — as únicas pendências de fluxo são
    # divergência e consignado usado sem empenho.
    pendencias = [
        {
            "chave": "divergencia",
            "titulo": "Itens em divergência",
            "quantidade": contagem.get(DIVERGENCIA, 0),
            "acao": "/consultas/itens?status=divergencia",
            "modulo": "consultas",
            "urgencia": "alta",
        },
        {
            "chave": "dispensacao_a_confirmar",
            "titulo": "Dispensações aguardando a confirmação da sala",
            "quantidade": db.escalar(
                """SELECT COUNT(*) FROM dispensacoes d WHERE d.status = 'pendente' AND EXISTS
                   (SELECT 1 FROM dispensacao_itens i WHERE i.id_dispensacao = d.id_dispensacao
                      AND i.situacao = 'pendente')"""),
            "acao": "/farmacia/dispensacoes",
            "modulo": "farmacia",
            "urgencia": "media",
        },
        {
            "chave": "nao_cadastrado",
            "titulo": "Material NÃO cadastrado usado na sala aguardando regularização",
            "quantidade": db.escalar("SELECT COUNT(*) FROM nao_cadastrados WHERE situacao = 'pendente'"),
            "acao": "/almoxarifado/nao-cadastrados",
            "modulo": "almoxarifado",
            "urgencia": "alta",
        },
        {
            "chave": "uso_sem_dispensacao",
            "titulo": "Usos sem dispensação aguardando a ciência da farmácia",
            "quantidade": db.escalar("SELECT COUNT(*) FROM usos_sem_dispensacao WHERE situacao = 'pendente'"),
            "acao": "/farmacia/usos-sem-dispensacao",
            "modulo": "farmacia",
            "urgencia": "alta",
        },
        {
            "chave": "dispensado_nao_devolvido",
            "titulo": "Material dispensado de atendimento encerrado que não foi usado nem devolvido",
            "quantidade": db.escalar(
                """SELECT COUNT(*) FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
                   WHERE u.status IN ('transito_sala', 'em_sala') AND a.status <> 'aberto'"""),
            "acao": "/consultas/eventos?tipo=dispensacao",
            "modulo": "farmacia",
            "urgencia": "alta",
        },
        {
            "chave": "devolucao_a_confirmar",
            "titulo": "Devoluções da sala aguardando a senha da farmácia",
            "quantidade": db.escalar(
                """SELECT COUNT(*) FROM devolucoes d WHERE d.status = 'pendente' AND EXISTS
                   (SELECT 1 FROM devolucao_itens i WHERE i.id_devolucao = d.id_devolucao
                      AND i.situacao = 'pendente')"""),
            "acao": "/farmacia/devolucoes",
            "modulo": "farmacia",
            "urgencia": "media",
        },
        {
            "chave": "caixa_bloqueada",
            "titulo": "Caixas de consignado bloqueadas — conferir",
            "quantidade": db.escalar("SELECT COUNT(*) FROM caixas WHERE bloqueada = 1 AND encerrada_em IS NULL"),
            "acao": "/farmacia/caixas-consignado",
            "modulo": "farmacia",
            "urgencia": "alta",
        },
        {
            "chave": "empenho_no_limite",
            "titulo": "Empenhos no limite de segurança — pedir mais empenho",
            "quantidade": len(empenhos.no_limite()),
            "acao": "/consignados/empenhos?status=ativo",
            "modulo": "consignados",
            "urgencia": "alta",
        },
        {
            "chave": "caixas_fora_do_prazo",
            "titulo": "Caixas de consignado não devolvidas pela sala até as 23:59",
            "quantidade": __import__(__package__ + ".caixas_sala", fromlist=["x"]).contar()["fora_do_prazo"],
            "acao": "/farmacia/caixas-sala",
            "modulo": "farmacia",
            "urgencia": "alta",
        },
        {
            "chave": "vincular_empenho",
            "titulo": "Consignados utilizados aguardando vínculo a empenho",
            "quantidade": empenhos.contar_pendentes_de_vinculo(),
            "acao": "/consignados/pendentes",
            "modulo": "consignados",
            "urgencia": "media",
        },
    ]

    estoques = [
        {"titulo": "Em estoque (Almoxarifado)", "quantidade": contagem.get(EM_ESTOQUE_RECEBIMENTO, 0),
         "link": "/consultas/itens?status=em_estoque_recebimento"},
        *[{"titulo": f"Em estoque ({rotulo_farmacia(f)})", "quantidade": n,
           "link": f"/consultas/itens?status={EM_ESTOQUE_FARMACIA}:{f}"}
          for f, n in estoque_por_farmacia().items()],
        {"titulo": "Em trânsito para a farmácia", "quantidade": contagem.get(TRANSITO_FARMACIA, 0),
         "link": "/consultas/itens?status=transito_farmacia"},
        {"titulo": "Devolvido ao almoxarifado (aguardando ciência)", "quantidade": contagem.get("transito_almoxarifado", 0),
         "link": "/consultas/itens?status=transito_almoxarifado"},
        {"titulo": "Utilizados hoje", "quantidade": usos_do_dia(),
         "link": "/consultas/utilizados"},
        {"titulo": "Em divergência", "quantidade": contagem.get(DIVERGENCIA, 0),
         "link": "/consultas/itens?status=divergencia"},
        {"titulo": "Utilizados (total)", "quantidade": contagem.get(UTILIZADO, 0),
         "link": "/consultas/itens?status=utilizado"},
    ]

    return {
        "pendencias": [p for p in pendencias if p["quantidade"] > 0],
        "pendencias_todas": pendencias,
        "estoques": estoques,
        "validades": validades_criticas(),
        "cirurgias_hoje": cirurgias_do_dia(),
        "ultimos_eventos": ultimos_eventos(12),
        "parados": itens_parados(),
    }


def usos_do_dia(data: str = "") -> int:
    """Quantas unidades foram de fato utilizadas na data (padrão: hoje).

    Conta a UNIDADE que está utilizada e cujo último registro de uso foi nessa
    data — não os bips. Bipado 3 vezes e excluído 2 conta 1; bipado e excluído
    (ou estornado) não conta."""
    data = data or hoje_iso()
    return db.escalar(
        f"""SELECT COUNT(*) FROM unidades u
            WHERE u.status = '{UTILIZADO}'
              AND date((SELECT MAX(e.data_evento) FROM eventos e
                         WHERE e.id_unidade = u.id_unidade AND e.tipo = 'registrar_uso')) = date(?)""",
        (data,),
    ) or 0


def validades_criticas(dias: int = DIAS_ALERTA_VALIDADE) -> list[dict]:
    return db.consultar(
        f"""SELECT xProd, nLote, dVal, fornecedor, COUNT(*) AS quantidade,
                   CAST(julianday(dVal) - julianday('now') AS INTEGER) AS dias_restantes
            FROM unidades
            WHERE status IN ({','.join('?' for _ in ESTOQUE_ATIVO)})
              AND dVal IS NOT NULL AND dVal <> ''
              AND julianday(dVal) - julianday('now') <= ?
            GROUP BY xProd, nLote, dVal, fornecedor
            ORDER BY dVal LIMIT 30""",
        (*ESTOQUE_ATIVO, dias),
    )


def cirurgias_do_dia(data: str = "", unidade: str = "") -> list[dict]:
    data = data or hoje_iso()
    alvos = [texto(unidade)] if texto(unidade) in UNIDADES_ATIVAS else list(UNIDADES_ATIVAS)
    marcadores = ",".join("?" for _ in alvos)
    return db.consultar(
        f"""SELECT a.id_atendimento, a.prontuario, a.paciente, a.unidade, a.sala,
                   a.especialidade, a.status, a.hora_inicio, a.opme_solicitado,
                   SUM(CASE WHEN u.status = '{SEPARADO}' THEN 1 ELSE 0 END) AS separados,
                   SUM(CASE WHEN u.status = '{TRANSITO_SALA}' THEN 1 ELSE 0 END) AS em_transito,
                   SUM(CASE WHEN u.status = '{EM_SALA}' THEN 1 ELSE 0 END) AS na_sala,
                   SUM(CASE WHEN u.status = '{UTILIZADO}' THEN 1 ELSE 0 END) AS utilizados,
                   SUM(CASE WHEN u.status = '{TRANSITO_RETORNO}' THEN 1 ELSE 0 END) AS em_retorno
            FROM atendimentos a
            LEFT JOIN unidades u ON u.id_atendimento = a.id_atendimento
            WHERE a.data_procedimento = ? AND a.unidade IN ({marcadores})
            GROUP BY a.id_atendimento
            ORDER BY a.unidade, a.sala, COALESCE(NULLIF(a.hora_inicio,''),'99:99')""",
        (data, *alvos),
    )


def itens_parados(dias: int = 2) -> list[dict]:
    """Itens presos em trânsito há dias — o sintoma clássico de conferência esquecida."""
    return db.consultar(
        f"""SELECT u.id_unidade, u.xProd, u.nLote, u.status, u.atualizado_em,
                   a.prontuario, a.sala,
                   CAST(julianday('now') - julianday(u.atualizado_em) AS INTEGER) AS dias_parado
            FROM unidades u LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.status IN ('{TRANSITO_FARMACIA}','{TRANSITO_SALA}','{TRANSITO_RETORNO}','transito_almoxarifado')
              AND julianday('now') - julianday(u.atualizado_em) >= ?
            ORDER BY u.atualizado_em LIMIT 30""",
        (dias,),
    )


def ultimos_eventos(limite: int = 30) -> list[dict]:
    linhas = db.consultar(
        """SELECT e.tipo, e.data_evento, e.usuario, e.status_novo, e.motivo, e.observacao,
                  u.xProd, u.nLote, u.id_unidade, a.prontuario, a.sala
           FROM eventos e
           LEFT JOIN unidades u ON u.id_unidade = e.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
           ORDER BY e.id_evento DESC LIMIT ?""",
        (limite,),
    )
    for linha in linhas:
        linha["quando"] = data_hora_br(linha["data_evento"])
        linha["situacao"] = rotulo(linha["status_novo"]) if linha["status_novo"] else ""
    return linhas


# =========================================================
# RASTREABILIDADE
# =========================================================

def _filtro_data(data: str) -> tuple[str, list]:
    """Recorte por data do procedimento. Vazio = histórico completo do paciente."""
    data = data_iso(data)
    return ("AND date(a.data_procedimento) = date(?)", [data]) if data else ("", [])


def atendimentos_com_uso(inicio: str = "", fim: str = "", prontuario: str = "",
                         so_com_uso: bool = True, limite: int = 500) -> list[dict]:
    """v18: procedimentos (paciente + data) num dia/período, com o que foi registrado.

    Usado em Consultas → por prontuário (lista do período) e em Estornar uso
    (que agora é por paciente). `so_com_uso` deixa só quem tem material
    registrado como utilizado."""
    cond, params = ["1=1"], []
    if texto(inicio):
        cond.append("date(a.data_procedimento) >= date(?)")
        params.append(texto(inicio))
    if texto(fim):
        cond.append("date(a.data_procedimento) <= date(?)")
        params.append(texto(fim))
    if texto(prontuario):
        cond.append("a.prontuario = ?")
        params.append(texto(prontuario))
    linhas = db.consultar(
        f"""SELECT a.id_atendimento, a.prontuario, a.paciente, a.unidade, a.sala, a.especialidade,
                   date(a.data_procedimento) AS data, a.hora_inicio, a.status,
                   (SELECT COUNT(*) FROM unidades u WHERE u.id_atendimento = a.id_atendimento
                      AND u.status = '{UTILIZADO}') AS usados,
                   (SELECT COUNT(*) FROM eventos e WHERE e.id_atendimento = a.id_atendimento
                      AND e.tipo = 'estornar_uso') AS estornos
            FROM atendimentos a
            WHERE {' AND '.join(cond)}
            ORDER BY date(a.data_procedimento) DESC, a.hora_inicio, a.prontuario
            LIMIT ?""", (*params, limite))
    if so_com_uso:
        linhas = [l for l in linhas if l["usados"]]
    return linhas


def datas_do_prontuario(prontuario: str) -> list[dict]:
    """Procedimentos do paciente que têm material implantado, do mais recente.

    A consulta abre por aqui: o descritivo é colado no prontuário de UMA
    cirurgia, e trazer o histórico inteiro misturava materiais de procedimentos
    de outros dias no texto que vai para o prontuário de hoje.
    """
    # v17: entram também os procedimentos que só tiveram devolução.
    return db.consultar(
        f"""SELECT data, especialidade, SUM(usados) AS quantidade FROM (
              SELECT date(a.data_procedimento) AS data, a.especialidade, 1 AS usados
              FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
              WHERE a.prontuario = ? AND u.status = '{UTILIZADO}'
              UNION ALL
              SELECT date(a.data_procedimento), a.especialidade, 0
              FROM eventos e JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
              WHERE a.prontuario = ? AND e.tipo = 'devolver_nao_utilizado')
            GROUP BY data, especialidade
            ORDER BY data DESC""",
        (texto(prontuario), texto(prontuario)),
    )


def rastrear_por_prontuario(prontuario: str, data: str = "") -> list[dict]:
    filtro, extra = _filtro_data(data)
    return db.consultar(
        f"""SELECT u.id_unidade, u.codigo_barras, u.xProd, u.nLote, u.dVal, u.numero_serie,
                   u.fornecedor, u.marca_fabricante, u.chave_nf, u.numero_nf, u.vUnCom,
                   u.tipo_entrada, u.status,
                   a.prontuario, a.paciente, a.sala, a.especialidade, a.data_procedimento,
                   (SELECT data_evento FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.tipo = 'registrar_uso' ORDER BY ev.id_evento DESC LIMIT 1) AS data_uso,
                   (SELECT usuario FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.tipo = 'registrar_uso' ORDER BY ev.id_evento DESC LIMIT 1) AS usuario_uso
            FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE a.prontuario = ? AND u.status = '{UTILIZADO}' {filtro}
            ORDER BY a.data_procedimento DESC, u.xProd""",
        (texto(prontuario), *extra),
    )


def resumo_prontuario(prontuario: str, data: str = "") -> list[dict]:
    """Material implantado no paciente, agrupado por produto/lote/validade.

    É o formato que vai para o descritivo cirúrgico: o médico precisa da
    quantidade por lote, não de uma linha por unidade.
    """
    filtro, extra = _filtro_data(data)
    return db.consultar(
        f"""SELECT COALESCE(NULLIF(u.codigo_aghu,''),'—') AS codigo_aghu, u.xProd,
                   COALESCE(NULLIF(u.nLote,''),'—') AS nLote,
                   u.dVal, COALESCE(NULLIF(u.fornecedor,''),'—') AS fornecedor,
                   COUNT(*) AS quantidade,
                   GROUP_CONCAT(NULLIF(u.numero_serie,'')) AS series,
                   a.paciente, a.data_procedimento, a.especialidade
            FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE a.prontuario = ? AND u.status = '{UTILIZADO}' {filtro}
            GROUP BY u.codigo_aghu, u.xProd, u.nLote, u.dVal, u.fornecedor,
                     a.data_procedimento
            ORDER BY a.data_procedimento DESC, u.xProd""",
        (texto(prontuario), *extra),
    )


def descritivo_prontuario(prontuario: str, data: str = "") -> str:
    """Texto pronto para colar no descritivo cirúrgico.

    Campos na ordem pedida pela equipe: código AGHU, quantidade, lote, validade
    e fornecedor. Texto puro, sem tabela, porque o destino é um campo livre do
    prontuário eletrônico.
    """
    linhas = resumo_prontuario(prontuario, data)
    saida = [f"MATERIAIS IMPLANTADOS — PRONTUÁRIO {texto(prontuario)}"]
    if linhas and linhas[0].get("paciente"):
        saida.append(f"Paciente: {linhas[0]['paciente']}")
    saida.append("")

    if not linhas:
        saida.append("Nenhum material registrado como utilizado para este prontuário"
                     + (f" em {data_br(data)}." if data_iso(data) else "."))
        return "\n".join(saida)

    data_atual = None
    for linha in linhas:
        if linha["data_procedimento"] != data_atual:
            data_atual = linha["data_procedimento"]
            saida.append(f"Procedimento em {data_br(data_atual)}"
                         f" — {texto(linha.get('especialidade')).title()}")
        # A descrição do produto vai em linha própria: junto com o resto, a
        # linha passava da margem e era cortada na impressão.
        saida.append(
            f"  {linha['codigo_aghu']} --- {linha['quantidade']} un --- "
            f"lote {linha['nLote']} --- val {data_br(linha['dVal']) or '—'} --- "
            f"{linha['fornecedor']}"
        )
        saida.append(f"      {linha['xProd']}")
        if linha.get("series"):
            saida.append(f"      nº de série: {linha['series']}")

    saida.append("")
    saida.append(f"Total de {sum(l['quantidade'] for l in linhas)} unidade(s). "
                 f"Emitido pelo sistema de rastreabilidade de OPME em {data_br(hoje_iso())}.")
    return "\n".join(saida)


def rastrear_por_lote(codigo_ou_lote: str) -> list[dict]:
    from .. import busca
    # nov/2026: aceita a etiqueta GS1 bipada inteira (ver `busca.condicao`).
    cond, params, etiqueta = busca.condicao(
        codigo_ou_lote, ["u.nLote", "u.codigo_barras", "u.numero_serie"])
    linhas = db.consultar(
        f"""SELECT u.id_unidade, u.codigo_barras, u.xProd, u.nLote, u.dVal, u.status,
                  u.numero_serie, u.fornecedor, u.numero_nf, a.prontuario, a.sala, a.data_procedimento
           FROM unidades u LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE {cond}
           ORDER BY u.status, u.xProd LIMIT 500""",
        params,
    )
    return busca.refinar(linhas, etiqueta, codigo_ou_lote)


def itens_utilizados(data_inicial: str, data_final: str, filtros: dict | None = None) -> list[dict]:
    filtros = filtros or {}
    condicoes = [
        f"u.status = '{UTILIZADO}'",
        "date(a.data_procedimento) BETWEEN date(?) AND date(?)",
    ]
    params: list = [data_inicial, data_final]

    for campo, coluna in (("prontuario", "a.prontuario"), ("sala", "a.sala"),
                          ("especialidade", "a.especialidade"), ("fornecedor", "u.fornecedor"),
                          ("tipo_entrada", "u.tipo_entrada")):
        if texto(filtros.get(campo)):
            condicoes.append(f"{coluna} = ?")
            params.append(texto(filtros[campo]))

    if texto(filtros.get("produto")):
        condicoes.append("u.xProd LIKE ?")
        params.append(f"%{texto(filtros['produto'])}%")

    return db.consultar(
        f"""SELECT a.data_procedimento, a.prontuario, a.paciente, a.sala, a.especialidade,
                   u.xProd, u.nLote, u.dVal, u.numero_serie, u.codigo_barras, u.codigo_aghu,
                   u.fornecedor, u.marca_fabricante, u.tipo_entrada, u.vUnCom, u.numero_nf,
                   u.id_unidade,
                   (SELECT usuario FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.tipo = 'registrar_uso' ORDER BY ev.id_evento DESC LIMIT 1) AS usuario_uso,
                   (SELECT data_evento FROM eventos ev WHERE ev.id_unidade = u.id_unidade
                     AND ev.tipo = 'registrar_uso' ORDER BY ev.id_evento DESC LIMIT 1) AS data_uso
            FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE {' AND '.join(condicoes)}
            ORDER BY a.data_procedimento DESC, a.sala, u.xProd""",
        params,
    )


def por_classificacao(data_inicial: str, data_final: str, tipo_entrada: str = "",
                      fornecedor: str = "", somente_utilizados: bool = False) -> list[dict]:
    """Material por classificação (consignado, aquisição própria, doação…) no período.

    A data considerada é a da entrada do material no almoxarifado, não a do uso:
    a pergunta que isto responde é "o que entrou como consignado neste mês",
    que é a base da conferência com o fornecedor. Com `somente_utilizados`,
    passa a contar pela data do procedimento, para fechar o que foi consumido.
    """
    condicoes: list[str] = []
    params: list = []

    if somente_utilizados:
        condicoes.append(f"u.status = '{UTILIZADO}'")
        condicoes.append("date(a.data_procedimento) BETWEEN date(?) AND date(?)")
    else:
        condicoes.append("date(u.criado_em) BETWEEN date(?) AND date(?)")
        # nov/2026: cadastro excluído (entrada errada) não conta como entrada.
        condicoes.append("NOT EXISTS (SELECT 1 FROM eventos x WHERE x.id_unidade = u.id_unidade"
                         " AND x.tipo = 'cadastro_excluido')")
    params += [data_inicial, data_final]

    if texto(tipo_entrada):
        condicoes.append("u.tipo_entrada = ?")
        params.append(texto(tipo_entrada))
    if texto(fornecedor):
        condicoes.append("u.fornecedor LIKE ?")
        params.append(f"%{texto(fornecedor)}%")

    return db.consultar(
        f"""SELECT u.tipo_entrada, u.xProd, u.codigo_aghu, u.fornecedor,
                   COUNT(*) AS quantidade,
                   COALESCE(SUM(u.vUnCom),0) AS valor_total,
                   MIN(date(u.criado_em)) AS primeira_entrada,
                   MAX(date(u.criado_em)) AS ultima_entrada
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE {' AND '.join(condicoes)}
            GROUP BY u.tipo_entrada, u.xProd, u.codigo_aghu, u.fornecedor
            ORDER BY u.tipo_entrada, valor_total DESC, u.xProd
            LIMIT 500""",
        params,
    )


# Teto da lista detalhada. Diferente do resumo, aqui cada material é uma linha —
# e uma lista cortada em silêncio seria pedida ao fornecedor pela metade.
LIMITE_DETALHE = 2000


def detalhe_por_classificacao(
    data_inicial: str, data_final: str, tipo_entrada: str = "",
    fornecedor: str = "", somente_utilizados: bool = False,
) -> tuple[list[dict], bool]:
    """Uma linha por material, com paciente, lote, validade e série.

    O resumo agrupa por produto e responde "quanto entrou/saiu". Esta consulta
    responde outra pergunta: *quais* materiais, um a um. É o que o fornecedor
    precisa para emitir a nota do consignado — ele fatura contra lote, série e
    paciente, não contra um total por produto.

    Devolve também se a lista foi cortada no limite, para a tela poder avisar:
    mandar ao fornecedor uma relação truncada sem saber seria pior que não ter.
    """
    condicoes: list[str] = []
    params: list = []

    if somente_utilizados:
        condicoes.append(f"u.status = '{UTILIZADO}'")
        condicoes.append("date(a.data_procedimento) BETWEEN date(?) AND date(?)")
    else:
        condicoes.append("date(u.criado_em) BETWEEN date(?) AND date(?)")
        # nov/2026: cadastro excluído (entrada errada) não conta como entrada.
        condicoes.append("NOT EXISTS (SELECT 1 FROM eventos x WHERE x.id_unidade = u.id_unidade"
                         " AND x.tipo = 'cadastro_excluido')")
    params += [data_inicial, data_final]

    if texto(tipo_entrada):
        condicoes.append("u.tipo_entrada = ?")
        params.append(texto(tipo_entrada))
    if texto(fornecedor):
        condicoes.append("u.fornecedor LIKE ?")
        params.append(f"%{texto(fornecedor)}%")

    linhas = db.consultar(
        f"""SELECT a.data_procedimento, a.paciente, a.prontuario,
                   u.codigo_aghu, u.codigo_barras, u.xProd, u.marca_fabricante,
                   u.nLote, u.dVal, u.numero_serie,
                   u.fornecedor, u.tipo_entrada, COALESCE(u.codigo_consignado, '') AS codigo_consignado,
                   u.vUnCom, u.numero_nf,
                   u.status, u.id_unidade
            FROM unidades u
            LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE {' AND '.join(condicoes)}
            ORDER BY u.fornecedor, a.data_procedimento, u.xProd, u.nLote
            LIMIT {LIMITE_DETALHE + 1}""",
        params,
    )
    return linhas[:LIMITE_DETALHE], len(linhas) > LIMITE_DETALHE


def totais_por_classificacao(linhas: list[dict]) -> list[dict]:
    """Soma por classificação, para o resumo no topo da tela."""
    totais: dict[str, dict] = {}
    for linha in linhas:
        alvo = totais.setdefault(
            linha["tipo_entrada"], {"tipo_entrada": linha["tipo_entrada"],
                                    "quantidade": 0, "valor_total": 0.0})
        alvo["quantidade"] += linha["quantidade"]
        alvo["valor_total"] += linha["valor_total"] or 0
    return sorted(totais.values(), key=lambda t: -t["valor_total"])


# =========================================================
# EXPORTAÇÃO
# =========================================================

CABECALHOS = {
    "data_procedimento": "Data do procedimento", "prontuario": "Prontuário",
    "paciente": "Paciente", "sala": "Sala", "especialidade": "Especialidade",
    "xProd": "Produto", "nLote": "Lote", "dVal": "Validade", "dFab": "Fabricação",
    "numero_serie": "Nº de série", "codigo_barras": "Código de barras",
    "codigo_aghu": "Código AGHU", "fornecedor": "Fornecedor",
    "marca_fabricante": "Marca/Fabricante", "tipo_entrada": "Classificação", "codigo_consignado": "Código consignado",
    "vUnCom": "Valor unitário", "numero_nf": "NF", "id_unidade": "ID da unidade",
    "usuario_uso": "Registrado por", "data_uso": "Data do registro de uso",
    "status": "Situação", "quantidade": "Quantidade", "dias_restantes": "Dias para vencer",
    "situacao": "Pendência", "codigo_lido": "Código bipado", "farmacia": "Farmácia",
}


def para_csv(linhas: list[dict]) -> str:
    if not linhas:
        return ""
    buffer = io.StringIO()
    colunas = list(linhas[0].keys())
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow([CABECALHOS.get(c, c) for c in colunas])
    for linha in linhas:
        valores = []
        for coluna in colunas:
            valor = linha.get(coluna)
            if coluna in ("dVal", "dFab", "data_procedimento"):
                valor = data_br(valor)
            elif coluna in ("data_uso", "data_evento", "criado_em", "atualizado_em"):
                valor = data_hora_br(valor)
            elif coluna == "status":
                valor = rotulo(texto(valor))
            elif coluna == "vUnCom":
                valor = texto(valor).replace(".", ",")
            valores.append("" if valor is None else valor)
        escritor.writerow(valores)
    return buffer.getvalue()


def indicadores_periodo(data_inicial: str, data_final: str) -> dict:
    utilizados = db.escalar(
        f"""SELECT COUNT(*) FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.status = '{UTILIZADO}' AND date(a.data_procedimento) BETWEEN date(?) AND date(?)""",
        (data_inicial, data_final),
    )
    valor = db.escalar(
        f"""SELECT COALESCE(SUM(u.vUnCom),0) FROM unidades u
            JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.status = '{UTILIZADO}' AND date(a.data_procedimento) BETWEEN date(?) AND date(?)""",
        (data_inicial, data_final),
    )
    cirurgias = db.escalar(
        "SELECT COUNT(*) FROM atendimentos WHERE date(data_procedimento) BETWEEN date(?) AND date(?)",
        (data_inicial, data_final),
    )
    devolvidos = db.escalar(
        """SELECT COUNT(DISTINCT e.id_unidade) FROM eventos e
           WHERE e.tipo = 'conferir_retorno' AND date(e.data_evento) BETWEEN date(?) AND date(?)""",
        (data_inicial, data_final),
    )
    return {
        "utilizados": utilizados, "valor": valor, "cirurgias": cirurgias,
        "devolvidos": devolvidos,
        "aproveitamento": round(100 * utilizados / (utilizados + devolvidos), 1)
        if (utilizados + devolvidos) else 0.0,
    }


def top_produtos(data_inicial: str, data_final: str, limite: int = 15) -> list[dict]:
    return db.consultar(
        f"""SELECT u.xProd, u.fornecedor, COUNT(*) AS quantidade,
                   COALESCE(SUM(u.vUnCom),0) AS valor_total
            FROM unidades u JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
            WHERE u.status = '{UTILIZADO}' AND date(a.data_procedimento) BETWEEN date(?) AND date(?)
            GROUP BY u.xProd, u.fornecedor ORDER BY quantidade DESC LIMIT ?""",
        (data_inicial, data_final, limite),
    )


def opcoes_status() -> list[dict]:
    contagem = contagem_por_status()
    # v17: estados de farmácia/trânsito/sala só aparecem se houver item neles
    # (base antiga); no fluxo novo não são usados.
    usados_v17 = {EM_ESTOQUE_RECEBIMENTO, TRANSITO_FARMACIA, EM_ESTOQUE_FARMACIA, UTILIZADO,
                  DIVERGENCIA, "devolvido_fornecedor", "baixado"}
    opcoes = []
    for c, e in ESTADOS.items():
        if c in usados_v17 or contagem.get(c, 0):
            opcoes.append({"codigo": c, "rotulo": e.rotulo, "quantidade": contagem.get(c, 0)})
        if c == EM_ESTOQUE_FARMACIA:
            # Os dois estoques de farmácia são separados: um filtro para cada.
            for farm, qtd in estoque_por_farmacia().items():
                opcoes.append({"codigo": f"{c}:{farm}", "rotulo": "   — " + rotulo_farmacia(farm),
                               "quantidade": qtd})
    return opcoes


def estoque_por_farmacia() -> dict[str, int]:
    """Unidades no estoque de cada farmácia (Bloco e Hemodinâmica), sempre as duas."""
    qtd = {l["farmacia"]: l["n"] for l in db.consultar(
        "SELECT farmacia, COUNT(*) AS n FROM unidades WHERE status = ? GROUP BY farmacia",
        (EM_ESTOQUE_FARMACIA,))}
    return {f: qtd.get(f, 0) for f in FARMACIAS}



# =========================================================
# v17 — HISTÓRICO DE MOVIMENTAÇÕES COM FILTROS
# =========================================================

# Tipos de movimento que a tela oferece no filtro, na ordem em que acontecem.
TIPOS_MOVIMENTO = {
    "uso_devolucao": ("Uso e devolução", ("registrar_uso", "devolver_nao_utilizado",
                                           "devolver_caixa", "devolucao_caixa_divergente")),
    "entrada": ("Entrada no almoxarifado", ("entrada_nf", "entrada_manual", "nf_importada",
                                            "nf_excluida", "estorno_entrada_nf")),
    "registrar_uso": ("Uso no paciente", ("registrar_uso",)),
    "dispensacao": ("Dispensação farmácia → sala", ("dispensar_sala", "confirmar_recebimento_sala",
                                                    "remover_da_dispensacao", "nao_recebido_sala", "saida_sem_dispensacao",
                                                    "ciencia_uso_sem_dispensacao")),
    "devolver_nao_utilizado": ("Devolução de não utilizado", ("devolver_nao_utilizado", "devolver_caixa",
                                                              "devolucao_caixa_divergente")),
    "devolucao_etapas": ("Devolução: bipada, tirada ou não recebida",
                         ("bipar_devolucao", "remover_da_devolucao", "devolucao_nao_recebida")),
    "excluir_bip": ("Exclusão de bip", ("excluir_bip", "desfazer")),
    "estornar_uso": ("Estorno de uso", ("estornar_uso",)),
    "ciencia": ("Ciência de entrega da caixa ao paciente", ("ciencia_entrega_paciente",)),
    "atendimento": ("Atendimento: encerrado, reaberto ou cancelado",
                    ("atendimento_encerrado", "atendimento_reaberto", "atendimento_cancelado",
                     "devolvido_por_cancelamento")),
    "saidas": ("Baixa, divergência ou devolução ao fornecedor",
               ("baixar", "marcar_divergencia", "devolver_fornecedor")),
    "correcao": ("Correção ou exclusão de cadastro", ("correcao", "cadastro_excluido")),
    "ciencia_validade": ("Ciência de lote com validade mais próxima", ("ciencia_validade",)),
    "almox_farmacia": ("Envios e devoluções almoxarifado ⇄ farmácia",
                       ("enviar_farmacia", "remover_do_envio", "envio_farmacia_finalizado", "receber_farmacia",
                        "envio_nao_recebido", "tratativa_envio", "envio_cancelado",
                        "devolver_almoxarifado", "receber_almoxarifado", "devolucao_almox_nao_recebida")),
    "transferencia": ("Transferências entre farmácias",
                      ("transferir_farmacia", "transferencia_finalizada", "receber_transferencia")),
}

ROTULO_TIPO = {
    "entrada_nf": "Entrada por NF", "entrada_manual": "Entrada manual",
    "nf_importada": "NF importada", "nf_excluida": "NF excluída",
    "estorno_entrada_nf": "Entrada estornada (NF excluída)",
    "registrar_uso": "Uso no paciente", "devolver_nao_utilizado": "Devolução de não utilizado",
    "devolver_caixa": "Devolução da caixa", "devolucao_caixa_divergente": "Devolução da caixa RECUSADA",
    "conferir_caixa": "Caixa conferida e liberada",
    "avaria_sinalizada": "Problema sinalizado no material (sala)",
    "cancelado_aguarda_farmacia": "Procedimento cancelado — aguardando a farmácia",
    "caixa_enviada_farmacia": "Caixa dispensada à farmácia",
    "caixa_recebida_farmacia": "Caixa recebida pela farmácia (ciência)",
    "bipar_devolucao": "Devolução bipada (aguardando farmácia)",
    "dispensar_sala": "Dispensação para a sala (saída da farmácia)",
    "confirmar_recebimento_sala": "Recebido na sala (senha)",
    "remover_da_dispensacao": "Tirado da dispensação",
    "nao_recebido_sala": "Sala NÃO recebeu — aguardando conferência da farmácia",
    "nao_recebido_conferido": "Farmácia conferiu o não recebido",
    "saida_sem_dispensacao": "Uso sem dispensação (saída registrada no uso)",
    "selecao_manual": "Selecionado pelo AGHU (não foi possível bipar)",
    "uso_nao_cadastrado": "Uso de material NÃO cadastrado (exceção)",
    "regularizar_nao_cadastrado": "Material não cadastrado regularizado",
    "uso_finalizado": "Materiais utilizados finalizados pela sala",
    "lista_nao_utilizados": "Lista de não utilizados enviada à farmácia",
    "ciencia_uso_sem_dispensacao": "Farmácia ciente do uso sem dispensação",
    "remover_da_devolucao": "Tirado da devolução",
    "devolucao_nao_recebida": "Devolução NÃO recebida",
    "excluir_bip": "Bip excluído", "desfazer": "Movimento desfeito", "estornar_uso": "Estorno de uso",
    "ciencia_entrega_paciente": "Ciência: caixa ao paciente",
    "atendimento_encerrado": "Atendimento encerrado", "atendimento_reaberto": "Atendimento reaberto",
    "atendimento_cancelado": "Procedimento cancelado", "baixar": "Baixa",
    "devolvido_por_cancelamento": "Voltou à farmácia (procedimento cancelado)",
    "enviar_farmacia": "Enviado à farmácia",
    "remover_do_envio": "Tirado do envio à farmácia",
    "envio_farmacia_finalizado": "Envio à farmácia finalizado",
    "receber_farmacia": "Recebido pela farmácia (ciência)",
    "envio_nao_recebido": "Envio: não recebido pela farmácia",
    "tratativa_envio": "Envio: tratativa de não recebido",
    "solicitacao_opme": "Solicitação de OPME",
    "solicitacao_divergente": "Dispensa diferente da solicitação",
    "marcar_divergencia": "Divergência", "devolver_fornecedor": "Devolução ao fornecedor",
    "correcao": "Correção de cadastro",
    "cadastro_excluido": "Cadastro excluído (entrada errada)",
    "ciencia_validade": "Ciente: havia lote com validade mais próxima",
    "envio_cancelado": "Envio cancelado (voltou à origem)",
    "devolver_almoxarifado": "Devolvido pela farmácia ao almoxarifado",
    "receber_almoxarifado": "Recebido pelo almoxarifado (ciência)",
    "devolucao_almox_nao_recebida": "Devolução ao almoxarifado: não recebido",
    "transferir_farmacia": "Transferido para a outra farmácia",
    "transferencia_finalizada": "Transferência entre farmácias finalizada",
    "receber_transferencia": "Recebido da outra farmácia (ciência)",
}


def movimentacoes(*, inicio: str = "", fim: str = "", unidade: str = "", sala: str = "",
                  prontuario: str = "", tipo: str = "", usuario: str = "",
                  limite: int = 3000, agrupar_caixas: bool = True) -> list[dict]:
    """Eventos filtrados por período (data do movimento), local, prontuário, tipo e usuário.

    Cada devolução já traz quem recebeu na farmácia (o evento de confirmação é
    lido junto, não aparece como linha à parte).
    """
    from ..utils import normalizar_sala
    condicoes = ["e.tipo NOT LIKE 'confirmar_%'"]
    params: list = []
    if texto(inicio):
        condicoes.append("date(e.data_evento) >= date(?)")
        params.append(data_iso(inicio))
    if texto(fim):
        condicoes.append("date(e.data_evento) <= date(?)")
        params.append(data_iso(fim))
    if texto(unidade):
        condicoes.append("a.unidade = ?")
        params.append(texto(unidade))
    if texto(sala):
        condicoes.append("a.sala = ?")
        params.append(normalizar_sala(sala))
    if texto(prontuario):
        condicoes.append("(a.prontuario LIKE ? OR a.paciente LIKE ?)")
        so_digitos = "".join(c for c in texto(prontuario) if c.isdigit())
        params += [f"%{so_digitos or texto(prontuario)}%", f"%{texto(prontuario)}%"]
    if texto(tipo) in TIPOS_MOVIMENTO:
        tipos = TIPOS_MOVIMENTO[texto(tipo)][1]
        condicoes.append(f"e.tipo IN ({','.join('?' for _ in tipos)})")
        params += list(tipos)
    if texto(usuario):
        # v17: acha a pessoa também como quem devolveu ou quem recebeu.
        condicoes.append("(LOWER(e.usuario) LIKE LOWER(?) OR LOWER(COALESCE(e.devolvido_por, '')) LIKE LOWER(?)"
                         " OR LOWER(COALESCE(e.recebido_por, '')) LIKE LOWER(?))")
        params += [f"%{texto(usuario)}%"] * 3
    params.append(limite)
    linhas = db.consultar(
        f"""SELECT e.id_evento, e.data_evento, e.tipo, e.usuario, e.motivo, e.observacao,
                   e.status_novo, e.id_unidade, e.id_atendimento,
                   u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                   u.numero_serie, u.fornecedor, u.tipo_entrada,
                   a.prontuario, a.paciente, a.unidade, a.sala, a.especialidade,
                   a.data_procedimento,
                   COALESCE(e.recebido_por, CASE WHEN e.tipo = 'devolver_nao_utilizado' THEN
                     (SELECT c.usuario FROM eventos c WHERE c.id_unidade = e.id_unidade
                        AND c.tipo = 'confirmar_devolver_nao_utilizado'
                        AND c.id_atendimento = e.id_atendimento AND c.id_evento > e.id_evento
                      ORDER BY c.id_evento LIMIT 1) END) AS recebido_por,
                   CASE WHEN e.tipo IN ('devolver_nao_utilizado', 'devolver_caixa',
                                        'devolucao_caixa_divergente', 'bipar_devolucao',
                                        'devolucao_nao_recebida')
                        THEN COALESCE(e.devolvido_por, e.usuario) END AS devolvido_por
            FROM eventos e
            LEFT JOIN unidades u ON u.id_unidade = e.id_unidade
            LEFT JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
            WHERE {' AND '.join(condicoes)}
            ORDER BY e.id_evento DESC LIMIT ?""",
        params,
    )
    import re
    for linha in linhas:
        linha["movimento"] = ROTULO_TIPO.get(linha["tipo"], texto(linha["tipo"]).replace("_", " ").capitalize())
        linha["rotulo_unidade"] = UNIDADES_ATIVAS.get(texto(linha["unidade"]), {}).get("rotulo", texto(linha["unidade"]))
        achou = re.search(r"\[(CX-[^\]]+)\]", texto(linha["observacao"]))
        linha["caixa"] = achou.group(1) if achou else ""
        linha["itens_caixa"] = []
    # v17: devolução de caixa aparece como UMA linha (a caixa), com os itens dentro;
    # as linhas por item da mesma devolução saem da tela (continuam no CSV).
    if agrupar_caixas:
        por_caixa = {(l["id_atendimento"], l["caixa"]): l for l in linhas if l["tipo"] == "devolver_caixa"}
        restantes = []
        for l in linhas:
            chave = (l["id_atendimento"], l["caixa"])
            if l["tipo"] == "devolver_nao_utilizado" and l["caixa"] and chave in por_caixa:
                por_caixa[chave]["itens_caixa"].append(l)
                por_caixa[chave]["recebido_por"] = por_caixa[chave].get("recebido_por") or l["recebido_por"]
                continue
            restantes.append(l)
        linhas = restantes
        for l in linhas:
            if l["tipo"] == "devolver_caixa" and not l["itens_caixa"]:
                # Itens fora do recorte da consulta: busca direto.
                l["itens_caixa"] = db.consultar(
                    """SELECT e.id_unidade, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote
                       FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
                       WHERE e.tipo = 'devolver_nao_utilizado' AND e.id_atendimento = ?
                         AND e.observacao LIKE ?""", (l["id_atendimento"], f"%[{l['caixa']}]%"))
            if l["tipo"] == "devolver_caixa" and not l.get("recebido_por"):
                achou = re.search(r"recebida por (.+)$", texto(l["observacao"]))
                l["recebido_por"] = achou.group(1) if achou else ""
    return linhas


def movimentacoes_para_csv(linhas: list[dict]) -> str:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Data e hora", "Movimento", "Unidade", "Sala", "Prontuário", "Paciente",
                       "Data do procedimento", "Código AGHU", "Material", "Lote", "Validade",
                       "Nº série", "Fornecedor", "Classificação", "Usuário (login)",
                       "Devolvido por (sala)", "Recebido por (farmácia)",
                       "Caixa", "Motivo", "Observação"])
    for l in linhas:
        escritor.writerow([
            data_hora_br(l["data_evento"]), l["movimento"], l["rotulo_unidade"] or "", l["sala"] or "",
            l["prontuario"] or "", l["paciente"] or "", data_br(l["data_procedimento"]) or "",
            l["codigo_aghu"] or "", l["descritivo_hospital"] or l["xProd"] or "", l["nLote"] or "",
            data_br(l["dVal"]) or "", l["numero_serie"] or "", l["fornecedor"] or "",
            l["tipo_entrada"] or "", l["usuario"] or "", l.get("devolvido_por") or "",
            l["recebido_por"] or "",
            l.get("caixa") or "", l["motivo"] or "", l["observacao"] or ""])
    return buffer.getvalue()



def devolucoes_por_prontuario(prontuario: str, data: str = "") -> list[dict]:
    """v17 — material devolvido sem uso à farmácia nos procedimentos do paciente."""
    filtro, extra = _filtro_data(data)
    linhas = db.consultar(
        f"""SELECT e.id_unidade, e.data_evento, e.usuario AS bipado_por,
                   a.data_procedimento, a.unidade, a.sala, a.especialidade, a.id_atendimento,
                   u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal, u.numero_serie,
                   u.fornecedor,
                   (SELECT c.usuario FROM eventos c WHERE c.id_unidade = e.id_unidade
                      AND c.tipo = 'confirmar_devolver_nao_utilizado'
                      AND c.id_atendimento = e.id_atendimento AND c.id_evento > e.id_evento
                    ORDER BY c.id_evento LIMIT 1) AS recebido_por_antigo,
                   e.recebido_por AS recebido_por_nome,
                   COALESCE(e.devolvido_por, e.usuario) AS devolvido_por
            FROM eventos e
            JOIN atendimentos a ON a.id_atendimento = e.id_atendimento
            JOIN unidades u ON u.id_unidade = e.id_unidade
            WHERE e.tipo = 'devolver_nao_utilizado' AND a.prontuario = ? {filtro}
            ORDER BY a.data_procedimento DESC, e.id_evento""",
        [texto(prontuario), *extra],
    )
    for linha in linhas:
        linha["recebido_por"] = linha.pop("recebido_por_nome") or linha.pop("recebido_por_antigo")
        linha.pop("recebido_por_antigo", None)
    return linhas
