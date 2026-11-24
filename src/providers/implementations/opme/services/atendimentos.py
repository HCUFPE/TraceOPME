"""Atendimentos cirúrgicos (o antigo "contexto"): prontuário + sala + especialidade + data."""

import csv
import io
import re

from .. import db
from ..config import ESPECIALIDADES_PADRAO, ROTULO_ESPECIALIDADE, UNIDADE_PADRAO, UNIDADES_ATIVAS, rotulo_unidade
from ..domain import (
    EM_SALA, SEPARADO, TRANSITO_RETORNO, TRANSITO_SALA, UTILIZADO,
)
from ..utils import (
    data_br, data_hora_br, data_iso, faixa_turno, gerar_id, hoje_iso, normalizar_sala,
    padronizar_especialidade, padronizar_unidade, texto,
)


def especialidades() -> list[str]:
    do_banco = [r["especialidade"] for r in db.consultar(
        "SELECT DISTINCT especialidade FROM atendimentos WHERE especialidade <> ''"
    )]
    return sorted({*ESPECIALIDADES_PADRAO, *(padronizar_especialidade(e) for e in do_banco)})


def abrir(dados: dict, usuario: str) -> tuple[bool, str]:
    # Prontuário do AGHU vem pontuado (21.472.063); guardamos só os dígitos.
    prontuario = re.sub(r"\D", "", texto(dados.get("prontuario")))
    sala = normalizar_sala(dados.get("sala"))
    unidade = padronizar_unidade(dados.get("unidade")) or UNIDADE_PADRAO
    especialidade = padronizar_especialidade(dados.get("especialidade"))
    data = data_iso(dados.get("data_procedimento")) or hoje_iso()

    if not prontuario:
        return False, "Informe o prontuário."
    if not sala:
        return False, "Informe a sala."
    if not especialidade:
        return False, "Informe a especialidade."

    existente = db.consultar_um(
        """SELECT id_atendimento FROM atendimentos
           WHERE prontuario = ? AND unidade = ? AND sala = ?
             AND especialidade = ? AND data_procedimento = ?""",
        (prontuario, unidade, sala, especialidade, data),
    )
    if existente:
        return True, existente["id_atendimento"]

    origem = "agenda" if texto(dados.get("origem")) == "agenda" else "manual"

    id_atendimento = gerar_id("AT")
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO atendimentos
               (id_atendimento, prontuario, paciente, unidade, sala, especialidade,
                data_procedimento, hora_inicio, codigo_cirurgia, opme_solicitado,
                observacao, origem, status, criado_em, criado_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'aberto',?,?)""",
            (id_atendimento, prontuario, texto(dados.get("paciente")), unidade, sala,
             especialidade, data, texto(dados.get("hora_inicio")),
             texto(dados.get("codigo_cirurgia")), texto(dados.get("opme_solicitado")),
             texto(dados.get("observacao")), origem, db.agora(), usuario),
        )
        db.registrar_evento(
            conn, tipo="atendimento_aberto", id_atendimento=id_atendimento, usuario=usuario,
            observacao=(f"Prontuário {prontuario} · {rotulo_unidade(unidade)} sala {sala} "
                        f"· {data_br(data)}"),
        )
    return True, id_atendimento


def buscar(id_atendimento: str) -> dict | None:
    return db.consultar_um(
        "SELECT * FROM atendimentos WHERE id_atendimento = ?", (texto(id_atendimento),)
    )


def descrever(atendimento: dict | None) -> str:
    if not atendimento:
        return "—"
    hora = f" às {atendimento['hora_inicio']}" if atendimento.get("hora_inicio") else ""
    # v18.42: o nome do paciente junto do prontuário — quem dispensa confere o
    # paciente pelo nome, não pelo número (pedido da Camila, 20/11/2026).
    nome = texto(atendimento.get("paciente"))
    return (f"Prontuário {atendimento['prontuario']}"
            f"{' · ' + nome if nome else ''} · "
            f"{rotulo_unidade(atendimento.get('unidade'))} — Sala {atendimento['sala']} · "
            f"{ROTULO_ESPECIALIDADE.get(atendimento['especialidade'], atendimento['especialidade'].title())} · "
            f"{data_br(atendimento['data_procedimento'])}{hora}")


def listar(data: str = "", sala: str = "", prontuario: str = "", somente_abertos: bool = False,
           unidade: str = "", so_com_opme: bool = False, turno: str = "",
           com_kit_em: str = "", todas_unidades: bool = False) -> list[dict]:
    # Só Bloco Cirúrgico e Hemodinâmica usam OPME — as demais unidades da agenda
    # do AGHU (Centro Obstétrico, Endoscopia etc.) não têm o que rastrear aqui.
    # nov/2026: a tela Procedimentos mostra todas (todas_unidades=True).
    condicoes: list[str] = ["1 = 1"]
    params: list = []
    if not todas_unidades:
        condicoes.append(f"a.unidade IN ({','.join('?' for _ in UNIDADES_ATIVAS)})")
        params += list(UNIDADES_ATIVAS)
    if texto(data):
        condicoes.append("a.data_procedimento = ?")
        params.append(data_iso(data))
    if texto(unidade):
        condicoes.append("a.unidade = ?")
        params.append(padronizar_unidade(unidade))
    if texto(sala):
        condicoes.append("a.sala = ?")
        params.append(normalizar_sala(sala))
    if texto(prontuario):
        condicoes.append("(a.prontuario LIKE ? OR a.paciente LIKE ?)")
        termo = f"%{re.sub(r'[^0-9A-Za-zÀ-ÿ]', '', texto(prontuario))}%"
        params += [termo, f"%{texto(prontuario)}%"]
    if somente_abertos:
        condicoes.append("a.status = 'aberto'")
    if so_com_opme:
        # O filtro existe para esconder as centenas de cirurgias da agenda que
        # nunca pediram OPME. Mas ele não pode esconder o que a farmácia já está
        # tratando: atendimento cadastrado à mão, ou que já tem material
        # vinculado. Sem esta ressalva, um kit montado num atendimento novo
        # sumia da tela de dispensação — e o material acabava indo para a
        # cirurgia do mapa que estava na mesma sala e horário.
        condicoes.append(
            """(COALESCE(a.opme_solicitado,'') <> ''
                OR COALESCE(a.origem,'agenda') = 'manual'
                OR EXISTS (SELECT 1 FROM solicitacoes s JOIN solicitacao_itens si
                             ON si.id_solicitacao = s.id_solicitacao
                           WHERE s.id_atendimento = a.id_atendimento)
                OR EXISTS (SELECT 1 FROM unidades u
                           WHERE u.id_atendimento = a.id_atendimento))""")
    if texto(com_kit_em):
        # Só atendimentos com kit montado esperando dispensação nesta farmácia.
        condicoes.append(
            f"""EXISTS (SELECT 1 FROM unidades u
                        WHERE u.id_atendimento = a.id_atendimento
                          AND u.status = '{SEPARADO}' AND u.farmacia = ?)""")
        params.append(texto(com_kit_em))
    faixa = faixa_turno(turno)
    if faixa:
        # Sem hora cadastrada não dá para dizer o turno — esses ficam de fora do
        # filtro em vez de entrarem no turno errado.
        condicoes.append("COALESCE(NULLIF(a.hora_inicio,''),'') <> ''"
                         " AND a.hora_inicio >= ? AND a.hora_inicio < ?")
        params += [faixa[0], faixa[1]]

    return db.consultar(
        f"""SELECT a.*,
                   SUM(CASE WHEN u.status = '{SEPARADO}' THEN 1 ELSE 0 END) AS qtd_separados,
                   SUM(CASE WHEN u.status = '{TRANSITO_SALA}' THEN 1 ELSE 0 END) AS qtd_transito,
                   SUM(CASE WHEN u.status = '{EM_SALA}' THEN 1 ELSE 0 END) AS qtd_na_sala,
                   SUM(CASE WHEN u.status = '{UTILIZADO}' THEN 1 ELSE 0 END) AS qtd_utilizados,
                   SUM(CASE WHEN u.status = '{TRANSITO_RETORNO}' THEN 1 ELSE 0 END) AS qtd_retorno
            FROM atendimentos a
            LEFT JOIN unidades u ON u.id_atendimento = a.id_atendimento
            WHERE {' AND '.join(condicoes)}
            GROUP BY a.id_atendimento
            ORDER BY a.data_procedimento DESC, a.unidade, a.sala,
                     COALESCE(NULLIF(a.hora_inicio,''),'99:99'), a.prontuario
            LIMIT 400""",
        params,
    )


def abertos_por_prontuario(prontuario: str, data: str) -> list[dict]:
    """Atendimentos abertos com este prontuário numa data — usado para localizar o
    destino ao trocar de paciente digitando o prontuário em vez de escolher da lista."""
    prontuario = re.sub(r"\D", "", texto(prontuario))
    data = data_iso(data) or hoje_iso()
    if not prontuario:
        return []
    return db.consultar(
        """SELECT * FROM atendimentos
           WHERE prontuario = ? AND data_procedimento = ? AND status = 'aberto'
           ORDER BY sala""",
        (prontuario, data),
    )


def marcar_conflitos(lista: list[dict]) -> list[dict]:
    """Marca atendimentos que dividem unidade, sala e horário com outro.

    Duas cirurgias na mesma sala e hora é situação real — remarcação, encaixe,
    cadastro à mão de algo que já estava no mapa. O problema é que as duas
    linhas ficam quase idênticas na tela, e dispensar para a errada significa
    material lançado no prontuário de outro paciente. Marcar não impede o erro,
    mas tira a semelhança do caminho de quem está com pressa.
    """
    contagem: dict[tuple, int] = {}
    for item in lista:
        chave = (item.get("unidade"), item.get("sala"), texto(item.get("hora_inicio")))
        # Cancelado não disputa a sala com ninguém (v17).
        if chave[2] and item.get("status") != "cancelado":
            contagem[chave] = contagem.get(chave, 0) + 1
    for item in lista:
        chave = (item.get("unidade"), item.get("sala"), texto(item.get("hora_inicio")))
        item["conflito"] = item.get("status") != "cancelado" and contagem.get(chave, 0) > 1
    return lista


def conflitos_do_atendimento(id_atendimento: str) -> list[dict]:
    """Outros atendimentos na mesma unidade, sala, data e horário."""
    atendimento = buscar(id_atendimento)
    if not atendimento or not texto(atendimento.get("hora_inicio")):
        return []
    return db.consultar(
        """SELECT id_atendimento, prontuario, paciente, especialidade
           FROM atendimentos
           WHERE id_atendimento <> ? AND unidade = ? AND sala = ?
             AND data_procedimento = ? AND hora_inicio = ?""",
        (id_atendimento, atendimento["unidade"], atendimento["sala"],
         atendimento["data_procedimento"], atendimento["hora_inicio"]),
    )


def atualizar(id_atendimento: str, dados: dict, usuario: str) -> tuple[bool, str]:
    atendimento = buscar(id_atendimento)
    if not atendimento:
        return False, "Atendimento não encontrado."

    ja_movimentou = db.escalar(
        f"""SELECT COUNT(*) FROM unidades WHERE id_atendimento = ?
            AND status IN ('{TRANSITO_SALA}','{EM_SALA}','{UTILIZADO}','{TRANSITO_RETORNO}')""",
        (id_atendimento,),
    )
    prontuario = texto(dados.get("prontuario")) or atendimento["prontuario"]
    sala = normalizar_sala(dados.get("sala")) or atendimento["sala"]

    if ja_movimentou and (prontuario != atendimento["prontuario"] or sala != atendimento["sala"]):
        return False, ("Já existe material registrado como utilizado neste atendimento. "
                       "Prontuário e sala não podem mais ser alterados.")

    unidade = padronizar_unidade(dados.get("unidade")) or atendimento["unidade"]

    # v18.43.5: a hora do procedimento também se corrige aqui (pedido da Camila,
    # 23/11/2026). Ela define o turno na agenda e aparece na identificação do
    # atendimento, então errada atrapalha quem procura o procedimento.
    hora = texto(dados.get("hora_inicio"))
    if "hora_inicio" in dados and hora and not re.fullmatch(r"\d{1,2}:\d{2}", hora):
        return False, "Hora inválida. Use o formato 14:30."
    if hora:
        h, m = (int(p) for p in hora.split(":"))
        if h > 23 or m > 59:
            return False, "Hora inválida. Use o formato 14:30."
        hora = f"{h:02d}:{m:02d}"
    if "hora_inicio" not in dados:
        hora = texto(atendimento.get("hora_inicio"))

    with db.transacao() as conn:
        conn.execute(
            """UPDATE atendimentos SET prontuario = ?, paciente = ?, unidade = ?, sala = ?,
                                       hora_inicio = ?, observacao = ?, opme_solicitado = ?
               WHERE id_atendimento = ?""",
            (prontuario, texto(dados.get("paciente")), unidade, sala, hora,
             texto(dados.get("observacao")),
             texto(dados.get("opme_solicitado")) or atendimento["opme_solicitado"],
             id_atendimento),
        )
        mudou_hora = hora != texto(atendimento.get("hora_inicio"))
        db.registrar_evento(
            conn, tipo="atendimento_atualizado", id_atendimento=id_atendimento, usuario=usuario,
            observacao=(f"Prontuário {prontuario} · {rotulo_unidade(unidade)} sala {sala}"
                        + (f" · hora {hora or '—'}"
                           f" (era {texto(atendimento.get('hora_inicio')) or '—'})"
                           if mudou_hora else "")))
    return True, "Atendimento atualizado."


def encerrar(id_atendimento: str, usuario: str) -> tuple[bool, str]:
    # v17: o que já foi bipado na devolução (aguardando a farmácia) não trava.
    pendentes = db.escalar(
        f"""SELECT COUNT(*) FROM unidades u WHERE u.id_atendimento = ?
            AND u.status IN ('{SEPARADO}','{TRANSITO_SALA}','{EM_SALA}','{TRANSITO_RETORNO}')
            AND NOT EXISTS (SELECT 1 FROM devolucao_itens i JOIN devolucoes d
                              ON d.id_devolucao = i.id_devolucao
                            WHERE i.id_unidade = u.id_unidade AND i.situacao = 'pendente'
                              AND d.status = 'pendente')""",
        (id_atendimento,),
    )
    if pendentes:
        return False, (f"Ainda há {pendentes} material(is) dispensado(s) para este paciente que não "
                       "foram usados nem devolvidos à farmácia. A sala confere (bipa o uso) ou a farmácia marca “Recebi de volta”.")
    atual = buscar(id_atendimento)
    if not atual:
        return False, "Atendimento não encontrado."
    if atual["status"] != "aberto":
        return False, "Este atendimento já está encerrado."
    from . import entrega_paciente
    sem_ciencia = entrega_paciente.pendentes_de_ciencia(id_atendimento)
    if sem_ciencia:
        return False, ("Antes de encerrar, dê ciência da entrega da caixa ao paciente: "
                       + ", ".join(f"{i['xProd']} (AGHU {i['codigo_aghu']})" for i in sem_ciencia)
                       + ".")
    with db.transacao() as conn:
        conn.execute(
            "UPDATE atendimentos SET status = 'encerrado', encerrado_em = ?, encerrado_por = ? WHERE id_atendimento = ?",
            (db.agora(), usuario, id_atendimento),
        )
        db.registrar_evento(conn, tipo="atendimento_encerrado", id_atendimento=id_atendimento,
                            usuario=usuario)
    return True, "Atendimento encerrado."


def materiais(id_atendimento: str) -> list[dict]:
    return db.consultar(
        """SELECT u.*, e.data_evento AS ultimo_movimento
           FROM unidades u
           LEFT JOIN (SELECT id_unidade, MAX(data_evento) AS data_evento
                      FROM eventos GROUP BY id_unidade) e ON e.id_unidade = u.id_unidade
           WHERE u.id_atendimento = ?
           ORDER BY u.status, u.xProd, u.nLote""",
        (id_atendimento,),
    )


def materiais_usados_em_outro(id_atendimento: str) -> list[dict]:
    """v18.34: dispensado para ESTE paciente e registrado como usado em outro.

    Acontece quando a sala bipa, no prontuário do paciente seguinte, material
    que já estava com o anterior. O bip avisa na hora, mas depois o item sumia
    da ficha de origem — que fechava "sem nada sobrando" — e não havia como
    saber para onde tinha ido.
    """
    return db.consultar(
        """SELECT u.id_unidade, u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                  u.status, a.prontuario AS prontuario_destino, a.id_atendimento AS destino,
                  e.data_evento AS quando, e.usuario AS por
           FROM eventos e
           JOIN unidades u ON u.id_unidade = e.id_unidade
           LEFT JOIN atendimentos a ON a.id_atendimento = u.id_atendimento
           WHERE e.tipo = 'uso_em_outro_paciente' AND e.id_atendimento = ?
           ORDER BY e.data_evento""",
        (texto(id_atendimento),),
    )


def conciliacao(id_atendimento: str) -> list[dict]:
    """Separado × utilizado × devolvido, por produto/lote. Uma consulta, uma tabela."""
    return db.consultar(
        f"""SELECT xProd, nLote, dVal, codigo_barras, fornecedor,
                   COUNT(*) AS separados,
                   SUM(CASE WHEN status = '{UTILIZADO}' THEN 1 ELSE 0 END) AS utilizados,
                   SUM(CASE WHEN status = '{TRANSITO_RETORNO}' THEN 1 ELSE 0 END) AS em_retorno,
                   SUM(CASE WHEN status IN ('{SEPARADO}','{TRANSITO_SALA}','{EM_SALA}') THEN 1 ELSE 0 END) AS em_aberto
            FROM unidades WHERE id_atendimento = ?
            GROUP BY xProd, nLote, dVal, codigo_barras, fornecedor
            ORDER BY xProd, nLote""",
        (id_atendimento,),
    )


def resumo(id_atendimento: str) -> dict:
    linhas = db.consultar(
        "SELECT status, COUNT(*) AS total FROM unidades WHERE id_atendimento = ? GROUP BY status",
        (id_atendimento,),
    )
    contagem = {l["status"]: l["total"] for l in linhas}
    return {
        "separados": contagem.get(SEPARADO, 0),
        "transito_sala": contagem.get(TRANSITO_SALA, 0),
        "na_sala": contagem.get(EM_SALA, 0),
        "utilizados": contagem.get(UTILIZADO, 0),
        "em_retorno": contagem.get(TRANSITO_RETORNO, 0),
        "devolvidos": db.escalar(
            "SELECT COUNT(DISTINCT id_unidade) FROM eventos "
            "WHERE tipo = 'devolver_nao_utilizado' AND id_atendimento = ?", (id_atendimento,)),
        # v17: bipado pela sala, aguardando a senha da farmácia.
        "devolucao_aguardando": db.escalar(
            """SELECT COUNT(*) FROM devolucao_itens i JOIN devolucoes d ON d.id_devolucao = i.id_devolucao
               WHERE d.id_atendimento = ? AND d.status = 'pendente' AND i.situacao = 'pendente'""",
            (id_atendimento,)),
        "total": sum(contagem.values()),
    }


# =========================================================
# IMPORTAÇÃO DA AGENDA
# =========================================================

# Nomes de coluna aceitos. Inclui o export do AGHU (primeiro nome de cada
# conjunto) e nomes genéricos, para uma planilha montada à mão também funcionar.
ALIASES = {
    "prontuario": {"PRONTUARIO", "PRONTUÁRIO", "REGISTRO", "MATRICULA"},
    "paciente": {"NOME", "PACIENTE", "NOME DO PACIENTE"},
    "unidade": {"DESCRICAO_UNIDADE_FUNCIONAL", "DESCRIÇÃO_UNIDADE_FUNCIONAL",
                "UNIDADE_FUNCIONAL", "UNIDADE FUNCIONAL", "UNIDADE"},
    "sala": {"SALA", "SALA CIRURGICA", "SALA CIRÚRGICA", "SALA_CIRURGICA"},
    "especialidade": {"ESPECIALIDADE", "AREA", "ÁREA", "SETOR"},
    "data_procedimento": {"DTHR_INICIO_CIRG", "DATA", "DATA DO PROCEDIMENTO",
                          "DATA_PROCEDIMENTO", "DATA PROCEDIMENTO", "DATA_CIRURGIA"},
    "codigo_cirurgia": {"CODIGO_CIRURGIA", "CÓDIGO_CIRURGIA", "CODIGO DA CIRURGIA"},
    "solicitacao_especial": {"SOLICITACAO_ESPECIAL", "SOLICITAÇÃO_ESPECIAL",
                             "SOLICITACAO ESPECIAL"},
    "opme": {"OPME", "OPME_SOLICITADO"},
    "procedimentos": {"PROCEDIMENTOS", "PROCEDIMENTO"},
}


def _separar_data_hora(valor: str) -> tuple[str, str]:
    """Trata o formato do AGHU: '11/8/2026, 00:34'. Devolve (data ISO, hora)."""
    bruto = texto(valor).replace(",", " ")
    partes = bruto.split()
    if not partes:
        return "", ""
    data = data_iso(partes[0])
    hora = partes[1][:5] if len(partes) > 1 and ":" in partes[1] else ""
    return data, hora


def _so_digitos(valor) -> str:
    """Prontuário vem como 21.472.063 no AGHU; guardamos apenas os dígitos."""
    return re.sub(r"\D", "", texto(valor))


def _extrair_opme(*campos: str) -> str:
    """Pega os pedidos de OPME, que no AGHU vêm dentro de solicitacao_especial.

    O conteúdo é um pseudo-array: ["OPME (2) - ...", "INSTRUMENTAIS CME (1) - ..."].
    Interessam apenas as entradas de OPME; instrumentais e caixas do CME não.
    """
    achados: list[str] = []
    for campo in campos:
        bruto = texto(campo)
        if not bruto or "OPME" not in bruto.upper():
            continue
        # nov/2026: aceita aspas duplas (AGHU) ou simples (lista vinda do relatórios)
        trechos = re.findall(r'"([^"]+)"', bruto) or re.findall(r"'([^']+)'", bruto) or [bruto.strip("[] ")]
        for trecho in trechos:
            limpo = " ".join(trecho.split())
            if limpo.upper().startswith("OPME"):
                achados.append(limpo)
    if not achados:
        return ""
    achados.sort()  # OPME (1), OPME (2), OPME (3)...
    return " | ".join(achados)


NEGATIVOS_OPME = {"", "N", "NAO", "NÃO", "NENHUM", "NENHUMA", "0", "[]", "NULL", "NONE", "-", "SEM OPME"}


def _coluna_opme(valor: str) -> str:
    """nov/2026: coluna própria de OPME (relatórios). Cada entrada já é um pedido de OPME."""
    bruto = texto(valor)
    if bruto.upper() in NEGATIVOS_OPME:
        return ""
    if bruto.upper() in {"S", "SIM", "TRUE", "1", "X"}:
        return "OPME solicitado (detalhe na agenda)"
    itens = re.findall(r'"([^"]+)"', bruto) or re.findall(r"'([^']+)'", bruto) or [bruto.strip("[] ")]
    itens = [" ".join(i.split()) for i in itens if texto(i).upper() not in NEGATIVOS_OPME]
    return " | ".join(sorted(itens))


def importar_agenda_csv(conteudo: bytes, usuario: str) -> tuple[bool, str]:
    """Importa a agenda cirúrgica a partir de CSV.

    Reconhece o export do AGHU e também planilhas simples montadas à mão.
    """
    try:
        texto_arquivo = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto_arquivo = conteudo.decode("latin-1")

    # nov/2026: o separador é decidido pela linha do cabeçalho. O Sniffer se
    # confundia com as vírgulas dentro dos campos ("11/8/2026, 00:34" e a lista
    # de OPME) e lia o arquivo do relatórios (separado por ";") como uma coluna só.
    cabecalho = texto_arquivo.lstrip().splitlines()[0] if texto_arquivo.strip() else ""
    contagem = {d: cabecalho.count(d) for d in (";", "\t", ",")}
    separador = max(contagem, key=contagem.get) if any(contagem.values()) else ","
    leitor = csv.DictReader(io.StringIO(texto_arquivo), delimiter=separador)
    if not leitor.fieldnames:
        return False, "Não foi possível ler o cabeçalho do arquivo."

    # nov/2026: compara sem acento e tratando espaço e "_" como iguais
    # ("Dthr Inicio Cirg" do Metabase = DTHR_INICIO_CIRG do AGHU).
    import unicodedata

    def _norm(nome: str) -> str:
        sem_acento = unicodedata.normalize("NFKD", texto(nome)).encode("ascii", "ignore").decode()
        return re.sub(r"[\s_]+", "_", sem_acento.strip().upper())

    mapa: dict[str, str] = {}
    for coluna in leitor.fieldnames:
        chave = _norm(coluna)
        for campo, nomes in ALIASES.items():
            if chave in {_norm(n) for n in nomes} and campo not in mapa:
                mapa[campo] = coluna

    faltando = [c for c in ("prontuario", "sala", "data_procedimento") if c not in mapa]
    if faltando:
        rotulos = {"prontuario": "prontuário", "sala": "sala",
                   "data_procedimento": "data da cirurgia"}
        return False, (
            "Faltam colunas obrigatórias: " + ", ".join(rotulos[c] for c in faltando) + ". "
            "Colunas encontradas no arquivo: " + ", ".join(leitor.fieldnames[:12]) +
            ("…" if len(leitor.fieldnames) > 12 else "") + "."
        )

    criados = repetidos = invalidos = atualizados = 0
    com_opme = 0
    datas: set[str] = set()

    for linha in leitor:
        pega = lambda campo: texto(linha.get(mapa.get(campo, ""), ""))  # noqa: E731

        prontuario = _so_digitos(pega("prontuario"))
        data, hora = _separar_data_hora(pega("data_procedimento"))
        sala = normalizar_sala(pega("sala"))
        unidade = padronizar_unidade(pega("unidade")) or UNIDADE_PADRAO
        especialidade = padronizar_especialidade(pega("especialidade")) or "NAO INFORMADA"

        if not prontuario or not data or not sala:
            invalidos += 1
            continue

        opme = _extrair_opme(pega("solicitacao_especial"), pega("opme")) or _coluna_opme(pega("opme"))
        if opme:
            com_opme += 1
        datas.add(data)

        existente = db.consultar_um(
            """SELECT id_atendimento, opme_solicitado FROM atendimentos
               WHERE prontuario = ? AND unidade = ? AND sala = ?
                 AND especialidade = ? AND data_procedimento = ?""",
            (prontuario, unidade, sala, especialidade, data),
        )
        if existente:
            # Reimportar a agenda atualizada não duplica; só completa o pedido de OPME.
            if opme and not texto(existente["opme_solicitado"]):
                db.executar(
                    "UPDATE atendimentos SET opme_solicitado = ? WHERE id_atendimento = ?",
                    (opme, existente["id_atendimento"]),
                )
                atualizados += 1
            else:
                repetidos += 1
            continue

        ok, _ = abrir({
            "prontuario": prontuario,
            "paciente": pega("paciente"),
            "unidade": unidade,
            "sala": sala,
            "especialidade": especialidade,
            "data_procedimento": data,
            "hora_inicio": hora,
            "codigo_cirurgia": pega("codigo_cirurgia"),
            "opme_solicitado": opme,
            "observacao": "Importado da agenda",
            "origem": "agenda",
        }, usuario)
        if ok:
            criados += 1
        else:
            invalidos += 1

    partes = [f"{criados} atendimento(s) importado(s)"]
    if com_opme:
        partes.append(f"{com_opme} com OPME solicitado")
    if atualizados:
        partes.append(f"{atualizados} atualizado(s) com o pedido de OPME")
    if repetidos:
        partes.append(f"{repetidos} já existia(m)")
    if invalidos:
        partes.append(f"{invalidos} linha(s) sem prontuário, data ou sala")
    if datas:
        partes.append(f"período de {data_br(min(datas))} a {data_br(max(datas))}")

    return True, "Importação concluída: " + ", ".join(partes) + "."


def reabrir(id_atendimento: str, operador: str, usuario_supervisao: str,
            senha_supervisao: str, motivo: str) -> tuple[bool, str]:
    """v17 — atendimento encerrado só reabre com a senha da supervisão, na hora.

    Caso típico: a sala esqueceu de bipar um material. A supervisora digita o
    próprio usuário e senha e o motivo; fica registrado quem autorizou.
    """
    from ..security import PAPEIS_REABRIR
    from . import usuarios

    atendimento = buscar(id_atendimento)
    if not atendimento:
        return False, "Atendimento não encontrado."
    if atendimento["status"] == "aberto":
        return False, "Este atendimento já está aberto."
    motivo = texto(motivo)
    if len(motivo) < 5:
        return False, "Informe o motivo da reabertura (ex.: material esquecido na bipagem)."
    if not texto(usuario_supervisao) or not texto(senha_supervisao):
        return False, "A supervisora precisa digitar o usuário e a senha dela."
    ok, resultado = usuarios.autenticar(usuario_supervisao, senha_supervisao)
    if not ok:
        return False, resultado
    if resultado["papel"] not in PAPEIS_REABRIR:
        return False, (f"{resultado['nome']} não tem o perfil de Supervisão e não pode "
                       "autorizar a reabertura.")

    with db.transacao() as conn:
        conn.execute(
            """UPDATE atendimentos SET status = 'aberto', encerrado_em = NULL,
                                       encerrado_por = NULL, cancelado_em = NULL,
                                       cancelado_por = NULL, motivo_cancelamento = NULL,
                                       detalhe_cancelamento = NULL,
                                       uso_finalizado_em = NULL, uso_finalizado_por = NULL
               WHERE id_atendimento = ?""",
            (id_atendimento,))
        db.registrar_evento(
            conn, tipo="atendimento_reaberto", id_atendimento=id_atendimento,
            usuario=resultado["username"], motivo=motivo,
            observacao=f"Reaberto a pedido de {operador}; autorizado por {resultado['nome']}.")
    return True, f"Atendimento reaberto, autorizado por {resultado['nome']}."


def quem_esta_na_sala(id_atendimento: str) -> dict | None:
    """v18.13.1: o OUTRO atendimento que está com esta sala aberta agora (ou None)."""
    at = buscar(id_atendimento)
    if not at or at["status"] != "aberto" or texto(at.get("sala_aberta_em")):
        return None
    return db.consultar_um(
        """SELECT id_atendimento, prontuario, paciente, sala, sala_aberta_em FROM atendimentos
           WHERE unidade = ? AND sala = ? AND id_atendimento <> ? AND status = 'aberto'
             AND COALESCE(sala_aberta_em, '') <> '' AND COALESCE(uso_finalizado_em, '') = ''
           ORDER BY sala_aberta_em DESC LIMIT 1""",
        (at["unidade"], at["sala"], texto(id_atendimento)))


def candidatos_troca(id_origem: str) -> list[dict]:
    """v18.13.1: atendimentos abertos que podem assumir a sala (mesmo dia/unidade).

    Nada de material muda de paciente: cada um fica com o seu."""
    at = buscar(id_origem)
    if not at:
        return []
    return db.consultar(
        """SELECT id_atendimento, prontuario, paciente, sala, especialidade, hora_inicio, sala_aberta_em
           FROM atendimentos
           WHERE status = 'aberto' AND id_atendimento <> ? AND unidade = ? AND data_procedimento = ?
           ORDER BY (sala <> ?), hora_inicio, criado_em""",
        (texto(id_origem), at["unidade"], at["data_procedimento"], texto(at["sala"])))


def passar_sala(id_origem: str, id_destino: str, usuario: str, motivo: str) -> tuple[bool, str]:
    """v18.13.1: entrou outro paciente na frente — a SALA passa para ele.

    Nenhum material muda de paciente: o que foi dispensado/recebido para quem saiu
    continua reservado para ele (status e vínculo intactos), só a *vez na sala* é
    que troca. Quem assume passa a poder bipar o uso; quem saiu volta a aguardar e,
    quando entrar, recebe a sala de volta pelo mesmo caminho. Fica registrado nos dois.
    """
    from ..domain import EM_SALA, TRANSITO_SALA
    origem, destino = buscar(id_origem), buscar(id_destino)
    motivo = texto(motivo)
    if not origem or not destino:
        return False, "Atendimento não encontrado."
    if origem["id_atendimento"] == destino["id_atendimento"]:
        return False, "Escolha o atendimento do paciente que vai entrar."
    if origem["status"] != "aberto" or destino["status"] != "aberto":
        return False, "Os dois atendimentos precisam estar abertos."
    if origem["unidade"] != destino["unidade"]:
        return False, "Os dois atendimentos precisam ser da mesma unidade."
    if len(motivo) < 5:
        return False, "Informe o motivo (ex.: médico antecipou este paciente)."
    if not texto(origem.get("sala_aberta_em")):
        return False, (f"A sala não está aberta com {origem['paciente'] or origem['prontuario']}. "
                       "Abra a sala do paciente que vai entrar pela ficha dele.")
    guardado = db.escalar(
        "SELECT COUNT(*) FROM unidades WHERE id_atendimento = ? AND status IN (?,?)",
        (texto(id_origem), TRANSITO_SALA, EM_SALA)) or 0
    sala = texto(origem.get("sala"))
    mudou_sala = texto(destino.get("sala")) != sala
    agora = db.agora()
    quem_o = origem["paciente"] or origem["prontuario"]
    quem_d = destino["paciente"] or destino["prontuario"]
    with db.transacao() as conn:
        # a vez na sala sai de quem estava — o material dele NÃO é tocado
        conn.execute("""UPDATE atendimentos SET sala_aberta_em = NULL, sala_aberta_por = NULL,
                                               sala_aberta_auto = 0
                        WHERE id_atendimento = ?""", (texto(id_origem),))
        if texto(destino.get("sala_aberta_em")):
            abertura = texto(destino["sala_aberta_em"])
            conn.execute("UPDATE atendimentos SET sala = ? WHERE id_atendimento = ?", (sala, texto(id_destino)))
        else:
            abertura = agora
            conn.execute("""UPDATE atendimentos SET sala = ?, sala_aberta_em = ?, sala_aberta_por = ?,
                                                   sala_aberta_auto = 0
                            WHERE id_atendimento = ?""", (sala, agora, usuario, texto(id_destino)))
        db.registrar_evento(conn, tipo="sala_passada", id_atendimento=id_origem, usuario=usuario, motivo=motivo,
                            observacao=f"Sala {sala} passou para {quem_d} (prontuário {destino['prontuario']}). "
                                       f"{guardado} item(ns) continuam reservados para este paciente.")
        db.registrar_evento(conn, tipo="sala_assumida", id_atendimento=id_destino, usuario=usuario, motivo=motivo,
                            observacao=f"Entrou na sala {sala} na frente de {quem_o} "
                                       f"(prontuário {origem['prontuario']}), cada um com o seu material.")
    reservado = (f" O material de {quem_o} ({guardado} item(ns)) continua reservado para ele — "
                 "nada voltou para a farmácia." if guardado else
                 f" {quem_o} não tem material com ele neste momento.")
    troca = (f" O atendimento de {quem_d} foi passado para a sala {sala}." if mudou_sala else "")
    return True, (f"A sala {sala} passou a atender {quem_d} (prontuário {destino['prontuario']}) "
                  f"às {abertura[11:16]}.{troca}{reservado} Quando {quem_o} entrar, abra a ficha "
                  "dele e clique em “Assumir a sala”.")


def historico_encerramento(id_atendimento: str) -> list[dict]:
    return db.consultar(
        """SELECT tipo, usuario, data_evento, motivo, observacao FROM eventos
           WHERE id_atendimento = ?
             AND tipo IN ('atendimento_encerrado','atendimento_reaberto','atendimento_cancelado')
           ORDER BY id_evento""", (id_atendimento,))


def cancelar(id_atendimento: str, usuario: str, motivo: str, detalhe: str = "",
             *, pela: str = "sala") -> tuple[bool, str]:
    """v17 — procedimento cancelado: cancela com motivo e devolve o material.

    Alimenta o indicador de cancelamento/troca de cirurgias. Não pode haver
    material registrado como utilizado — se houve bip por engano, exclua antes.
    Reabrir um cancelado é com a supervisão.

    v18: o que a farmácia dispensou e a sala AINDA NÃO recebeu volta direto para
    o estoque da farmácia (nunca saiu de lá). O que a sala JÁ RECEBEU (deu
    ciência) volta como devolução pendente: a farmácia precisa dar ciência de que
    o material voltou (Farmácia → Não utilizados — dar ciência).
    A dispensação pendente é encerrada como cancelada.

    `pela="farmacia"`: a farmácia só cancela enquanto a sala ainda não recebeu o
    material (nada "na sala"); depois disso, quem cancela é a sala.
    """
    from ..config import MOTIVOS_CANCELAMENTO
    from ..domain import EM_ESTOQUE_FARMACIA, estoque_de_volta
    atendimento = buscar(id_atendimento)
    if not atendimento:
        return False, "Atendimento não encontrado."
    if atendimento["status"] != "aberto":
        return False, "Só é possível cancelar um atendimento aberto."
    motivo, detalhe = texto(motivo), texto(detalhe)
    if motivo not in MOTIVOS_CANCELAMENTO:
        return False, "Escolha o motivo do cancelamento."
    if motivo == "Outro" and len(detalhe) < 5:
        return False, "Descreva o motivo quando escolher “Outro”."
    if texto(atendimento.get("uso_finalizado_em")):
        return False, ("Os materiais utilizados deste procedimento já foram finalizados: o que "
                       "sobrou já está na lista de não utilizados da farmácia.")
    usados = db.escalar(
        f"SELECT COUNT(*) FROM unidades WHERE id_atendimento = ? AND status = '{UTILIZADO}'",
        (id_atendimento,))
    if usados:
        return False, (f"Há {usados} material(is) registrado(s) como utilizado(s) neste "
                       "atendimento. Se foi engano, exclua os bips no registro de uso antes "
                       "de cancelar.")
    na_sala = db.escalar(
        f"SELECT COUNT(*) FROM unidades WHERE id_atendimento = ? AND status = '{EM_SALA}'",
        (id_atendimento,))
    if pela == "farmacia" and na_sala:
        return False, (f"A sala já confirmou o recebimento de {na_sala} item(ns) deste paciente. "
                       "Neste caso o cancelamento é feito pela sala de procedimento (o material "
                       "volta direto para a farmácia do mesmo jeito).")
    agora = db.agora()
    observacao_ev = (f"Procedimento cancelado ({motivo}"
                     + (f" — {detalhe}" if detalhe else "")
                     + f"), pela {'farmácia' if pela == 'farmacia' else 'sala de procedimento'}: "
                       "a sala não tinha recebido — voltou direto ao estoque da farmácia.")
    from . import devolucoes
    with db.transacao() as conn:
        devolver = [dict(r) for r in conn.execute(
            f"""SELECT id_unidade, status, id_caixa, farmacia FROM unidades
                WHERE id_atendimento = ? AND status = '{TRANSITO_SALA}'""",
            (id_atendimento,)).fetchall()]
        # v18: o que já estava na sala (com ciência) volta pela farmácia, com ciência.
        ja_na_sala = [dict(r) for r in conn.execute(
            f"""SELECT u.id_unidade, u.id_caixa FROM unidades u
                WHERE u.id_atendimento = ? AND u.status = '{EM_SALA}'
                  AND NOT EXISTS (SELECT 1 FROM devolucao_itens di JOIN devolucoes dv
                                    ON dv.id_devolucao = di.id_devolucao
                                  WHERE dv.status = 'pendente' AND di.situacao = 'pendente'
                                    AND (di.id_unidade = u.id_unidade
                                         OR (di.tipo = 'caixa' AND UPPER(di.id_caixa) = UPPER(COALESCE(u.id_caixa,'')))))""",
            (id_atendimento,)).fetchall()]
        soltos = [u["id_unidade"] for u in ja_na_sala if not texto(u["id_caixa"])]
        por_caixa: dict = {}
        for u in ja_na_sala:
            if texto(u["id_caixa"]):
                por_caixa[u["id_caixa"]] = por_caixa.get(u["id_caixa"], 0) + 1
        devolucoes.abrir_retorno(conn, id_atendimento, usuario, unidades=soltos, caixas=por_caixa,
                                 origem=f"Procedimento cancelado ({motivo})")
        for u in ja_na_sala:
            db.registrar_evento(
                conn, tipo="cancelado_aguarda_farmacia", id_unidade=u["id_unidade"],
                id_atendimento=id_atendimento, status_anterior=EM_SALA, status_novo=EM_SALA,
                usuario=usuario, motivo=motivo,
                observacao=(f"[{u['id_caixa']}] " if texto(u["id_caixa"]) else "")
                + "Procedimento cancelado com o material já na sala: aguardando a farmácia dar ciência da volta.")
        for u in devolver:
            conn.execute(
                """UPDATE unidades SET status = ?, id_atendimento = NULL,
                                       atualizado_em = ?, atualizado_por = ?
                   WHERE id_unidade = ?""",
                (estoque_de_volta(u["farmacia"]), agora, usuario, u["id_unidade"]))
            db.registrar_evento(
                conn, tipo="devolvido_por_cancelamento", id_unidade=u["id_unidade"],
                id_atendimento=id_atendimento, status_anterior=u["status"],
                status_novo=estoque_de_volta(u["farmacia"]), usuario=usuario, motivo=motivo,
                observacao=(f"[{u['id_caixa']}] " if texto(u["id_caixa"]) else "") + observacao_ev)
        conn.execute(
            f"""UPDATE caixas SET status = ?, id_atendimento = NULL, atualizado_em = ?, atualizado_por = ?
                WHERE id_atendimento = ? AND status = '{TRANSITO_SALA}'""",
            (EM_ESTOQUE_FARMACIA, agora, usuario, id_atendimento))
        # Dispensação que esperava a sala: encerrada como cancelada (sai das
        # listas de "aguardando a sala" e da trava do prontuário).
        conn.execute(
            """UPDATE dispensacao_itens SET situacao = 'cancelado', resolvido_em = ?, resolvido_por = ?
               WHERE situacao = 'pendente' AND id_dispensacao IN
                     (SELECT id_dispensacao FROM dispensacoes WHERE id_atendimento = ?)""",
            (agora, usuario, id_atendimento))
        conn.execute(
            "UPDATE dispensacoes SET status = 'cancelada' WHERE id_atendimento = ? AND status = 'pendente'",
            (id_atendimento,))
        conn.execute(
            """UPDATE solicitacoes SET cancelada_em = ?, cancelada_por = ?
               WHERE id_atendimento = ? AND COALESCE(cancelada_em,'') = ''""",
            (agora, usuario, id_atendimento))
        conn.execute(
            """UPDATE atendimentos SET status = 'cancelado', cancelado_em = ?, cancelado_por = ?,
                                       motivo_cancelamento = ?, detalhe_cancelamento = ?
               WHERE id_atendimento = ?""",
            (agora, usuario, motivo, detalhe, id_atendimento))
        db.registrar_evento(conn, tipo="atendimento_cancelado", id_atendimento=id_atendimento,
                            usuario=usuario, motivo=motivo,
                            observacao=(detalhe + (" · " if detalhe else "")
                                        + f"cancelado pela {'farmácia' if pela == 'farmacia' else 'sala'}"
                                        + (f"; {len(devolver)} item(ns) devolvido(s) à farmácia"
                                           if devolver else "")
                                        + (f"; {len(ja_na_sala)} item(ns) aguardando a ciência da farmácia"
                                           if ja_na_sala else "")))
    partes = []
    if devolver:
        partes.append(f"{len(devolver)} item(ns) que a sala ainda não tinha recebido voltaram direto "
                      "para o estoque da farmácia")
    if ja_na_sala:
        partes.append(f"{len(ja_na_sala)} item(ns) que já estavam na sala voltam para a farmácia, que "
                      "precisa dar ciência (Farmácia → Não utilizados — dar ciência)")
    return True, ("Procedimento cancelado. " + ("; ".join(partes) + ". " if partes else "")
                  + "O motivo entra no indicador de cancelamentos.")


def descancelar(id_atendimento: str, usuario: str, motivo: str = "") -> tuple[bool, str]:
    """v18.43: desfaz o cancelamento do procedimento feito por engano.

    Camila (20/11/2026): "se um procedimento for cancelado permitir
    descancelar, pois pode ter sido por engano."

    O procedimento volta a ficar aberto e a solicitação da sala volta a valer.
    O material NÃO volta sozinho para o paciente: o cancelamento mandou de volta
    para a farmácia o que estava em trânsito e abriu devolução do que já estava
    na sala. Isso fica como está — a farmácia dispensa de novo, bipando. Mexer
    no estoque para trás seria pior: a peça pode já ter ido para outro paciente.

    Diferente de `reabrir`, que é para procedimento ENCERRADO e exige a
    supervisão: aqui o engano costuma ser percebido na hora, por quem cancelou.
    """
    atendimento = buscar(id_atendimento)
    if not atendimento:
        return False, "Atendimento não encontrado."
    if atendimento["status"] != "cancelado":
        return False, ("Este procedimento não está cancelado."
                       if atendimento["status"] == "aberto"
                       else "Este procedimento está encerrado — a reabertura é com a supervisão.")
    motivo = texto(motivo)
    if len(motivo) < 5:
        return False, "Escreva o motivo (ex.: cancelado por engano, o paciente vai operar)."
    with db.transacao() as conn:
        conn.execute(
            """UPDATE atendimentos SET status = 'aberto', cancelado_em = NULL, cancelado_por = NULL,
                                       motivo_cancelamento = NULL, detalhe_cancelamento = NULL
               WHERE id_atendimento = ? AND status = 'cancelado'""", (id_atendimento,))
        # a solicitação da sala tinha sido cancelada junto: volta a valer
        voltou = conn.execute(
            """UPDATE solicitacoes SET cancelada_em = NULL, cancelada_por = NULL,
                                       motivo_cancelamento = NULL
               WHERE id_atendimento = ? AND COALESCE(cancelada_em,'') <> ''""",
            (id_atendimento,)).rowcount
        db.registrar_evento(
            conn, tipo="atendimento_descancelado", id_atendimento=id_atendimento, usuario=usuario,
            motivo=motivo,
            observacao=("Cancelamento desfeito (era: "
                        + texto(atendimento.get("motivo_cancelamento")) + ")"
                        + (", cancelado em " + data_hora_br(atendimento.get("cancelado_em"))
                           if texto(atendimento.get("cancelado_em")) else "")
                        + ("; a solicitação da sala voltou a valer" if voltou else "") + "."))
    em_estoque = db.escalar(
        """SELECT COUNT(*) FROM unidades WHERE id_atendimento IS NULL AND id_unidade IN
           (SELECT id_unidade FROM eventos WHERE id_atendimento = ?
              AND tipo IN ('devolvido_cancelamento','cancelado_aguarda_farmacia'))""",
        (id_atendimento,)) or 0
    aviso = (" O material que tinha voltado para a farmácia precisa ser dispensado de novo, bipando."
             if em_estoque else
             " Se algum material já tinha voltado para a farmácia, dispense de novo, bipando.")
    return True, ("Cancelamento desfeito: o procedimento está aberto outra vez." + aviso)


def devolvidos(id_atendimento: str) -> list[dict]:
    """v17 — o que voltou sem uso para a farmácia neste atendimento, e quem recebeu."""
    return db.consultar(
        """SELECT e.id_unidade, e.data_evento, e.usuario AS bipado_por,
                  u.xProd, u.descritivo_hospital, u.codigo_aghu, u.nLote, u.dVal,
                  COALESCE(e.recebido_por, (SELECT c.usuario FROM eventos c WHERE c.id_unidade = e.id_unidade
                     AND c.tipo = 'confirmar_devolver_nao_utilizado'
                     AND c.id_atendimento = e.id_atendimento AND c.id_evento > e.id_evento
                   ORDER BY c.id_evento LIMIT 1)) AS recebido_por,
                  COALESCE(e.devolvido_por, e.usuario) AS devolvido_por
           FROM eventos e JOIN unidades u ON u.id_unidade = e.id_unidade
           WHERE e.tipo = 'devolver_nao_utilizado' AND e.id_atendimento = ?
           ORDER BY e.id_evento""", (id_atendimento,))


def a_concluir(unidade: str = "") -> list[dict]:
    """v17 — atendimentos ainda abertos que já têm material (usado ou dispensado):
    falta "Concluir bipagem". De qualquer data, para nenhum ficar esquecido."""
    from ..domain import EM_SALA, TRANSITO_SALA, UTILIZADO
    condicoes = ["a.status = 'aberto'", "COALESCE(a.uso_finalizado_em,'') = ''",
                 f"a.unidade IN ({','.join('?' for _ in UNIDADES_ATIVAS)})"]
    params: list = list(UNIDADES_ATIVAS)
    if texto(unidade):
        condicoes.append("a.unidade = ?")
        params.append(padronizar_unidade(unidade))
    return db.consultar(
        f"""SELECT a.id_atendimento, a.prontuario, a.paciente, a.unidade, a.sala,
                   a.data_procedimento,
                   SUM(CASE WHEN u.status = '{UTILIZADO}' THEN 1 ELSE 0 END) AS usados,
                   SUM(CASE WHEN u.status IN ('{TRANSITO_SALA}','{EM_SALA}') THEN 1 ELSE 0 END)
                       AS dispensados
            FROM atendimentos a JOIN unidades u ON u.id_atendimento = a.id_atendimento
            WHERE {' AND '.join(condicoes)}
            GROUP BY a.id_atendimento
            HAVING (usados > 0 OR dispensados > 0)
               -- v18.4.5: com material ainda aguardando a confirmação da sala, o próximo
               -- passo é confirmar o recebimento — não aparece como "falta finalizar".
               AND SUM(CASE WHEN u.status = '{TRANSITO_SALA}' THEN 1 ELSE 0 END) = 0
            ORDER BY a.data_procedimento, a.unidade, a.sala""", tuple(params))


# ---------------------------------------------------------------------------
# v18.3 — "Abrir sala"
# ---------------------------------------------------------------------------

def abrir_sala(id_atendimento: str, usuario: str, *, automatico: bool = False) -> tuple[bool, str]:
    """Registra que a sala abriu para este procedimento (uma vez só).

    `automatico`: a sala deu ciência do material ou bipou sem ter clicado em
    "Abrir sala" — a abertura fica registrada naquele momento, marcada como
    automática (a Central mostra a diferença)."""
    at = buscar(id_atendimento)
    if not at:
        return False, "Atendimento não encontrado."
    if at.get("sala_aberta_em"):
        return (not automatico), f"A sala já foi aberta às {texto(at['sala_aberta_em'])[11:16]}."
    if at["status"] != "aberto":
        return False, "Este procedimento não está aberto."
    # v18.13.1: se a sala está com OUTRO paciente, a ciência/bipe deste não "rouba" a sala.
    # Quem entra na frente assume a sala por "Entrou outro paciente na frente?" (passar_sala).
    ocupada = db.consultar_um(
        """SELECT prontuario, paciente FROM atendimentos
           WHERE unidade = ? AND sala = ? AND id_atendimento <> ? AND status = 'aberto'
             AND COALESCE(sala_aberta_em, '') <> '' AND COALESCE(uso_finalizado_em, '') = ''
           ORDER BY sala_aberta_em DESC LIMIT 1""", (at["unidade"], at["sala"], at["id_atendimento"]))
    if automatico and ocupada:
        return False, f"A sala {at['sala']} está aberta com o prontuário {ocupada['prontuario']}."
    if not automatico and ocupada:
        # Uma sala atende um paciente por vez.
        return False, (f"A sala {at['sala']} ainda está aberta com o prontuário {ocupada['prontuario']}"
                       f"{' (' + ocupada['paciente'] + ')' if ocupada['paciente'] else ''}. "
                       "Finalize a sala desse paciente — ou, se ele entrou na frente, use “Entrou outro "
                       "paciente na frente?” na ficha dele para a sala passar para este.")
    agora = db.agora()
    with db.transacao() as conn:
        conn.execute("UPDATE atendimentos SET sala_aberta_em = ?, sala_aberta_por = ?, sala_aberta_auto = ? "
                     "WHERE id_atendimento = ? AND COALESCE(sala_aberta_em, '') = ''",
                     (agora, usuario, 1 if automatico else 0, at["id_atendimento"]))
        db.registrar_evento(conn, tipo="sala_aberta", id_atendimento=at["id_atendimento"], usuario=usuario,
                            observacao=("Registrada sozinha na 1ª ação da sala (não clicaram em “Abrir sala”)"
                                        if automatico else f"Sala {at['sala']} aberta"))
    return True, f"Sala aberta às {agora[11:16]}."


def garantir_sala_aberta(id_atendimento: str, usuario: str) -> None:
    """Chamado depois da ciência do material e do uso: abre sozinha se ninguém abriu."""
    try:
        if id_atendimento:
            abrir_sala(id_atendimento, usuario, automatico=True)
    except Exception:  # nunca atrapalha a operação principal
        pass
