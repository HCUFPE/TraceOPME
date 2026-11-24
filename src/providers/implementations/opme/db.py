"""Acesso a dados do TraceOPME (Provider). Banco único, transações explícitas.

A conexão em si é aberta pela camada Resource (``src/resources/opme_sqlite.py``).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable

from ....resources.opme_sqlite import conectar as _conectar_resource
from ....resources.opme_sqlite import registrar_funcao_sql
from .config import DB_PATH  # noqa: F401  (mantido para quem importava daqui)
from .gs1 import gtin, lote_normalizado

# v17: `gtin()` compara códigos de barras ignorando zeros à esquerda do GTIN
# (o cEAN da NF e a etiqueta da embalagem nem sempre vêm com 14 dígitos).
registrar_funcao_sql("gtin", 1, gtin)
registrar_funcao_sql("lote_norm", 1, lote_normalizado)

# =========================================================
# CONEXÃO (camada Resource: src/resources/opme_sqlite.py)
# =========================================================


def conectar() -> sqlite3.Connection:
    """Conexão com o opme.db, aberta pela camada Resource do framework."""
    return _conectar_resource()


@contextmanager
def transacao():
    """Bloco atômico: ou tudo é gravado, ou nada é.

    Na versão anterior um envio de kit podia gravar metade das transferências
    e falhar no meio, deixando o estoque inconsistente.
    """
    from . import log

    from .erros import ErroDeNegocio

    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except ErroDeNegocio:
        # Recusa esperada: desfaz sem poluir o log técnico. Quem chamou registra
        # o caso com o contexto certo, se fizer sentido.
        conn.execute("ROLLBACK")
        raise
    except Exception as falha:
        conn.execute("ROLLBACK")
        log.erro(f"transação desfeita: {type(falha).__name__}", excecao=falha)
        raise
    finally:
        conn.close()


def consultar(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
    finally:
        conn.close()


def consultar_um(sql: str, params: Iterable[Any] = ()) -> dict | None:
    linhas = consultar(sql, params)
    return linhas[0] if linhas else None


def escalar(sql: str, params: Iterable[Any] = (), padrao: Any = 0) -> Any:
    conn = conectar()
    try:
        linha = conn.execute(sql, tuple(params)).fetchone()
        if linha is None:
            return padrao
        valor = linha[0]
        return padrao if valor is None else valor
    finally:
        conn.close()


def executar(sql: str, params: Iterable[Any] = ()) -> int:
    conn = conectar()
    try:
        cur = conn.execute(sql, tuple(params))
        return cur.rowcount
    finally:
        conn.close()


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# =========================================================
# ESQUEMA
# =========================================================

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    username      TEXT PRIMARY KEY,
    senha_hash    TEXT NOT NULL,
    nome          TEXT NOT NULL,
    email         TEXT,
    setor         TEXT,
    papel         TEXT NOT NULL DEFAULT 'consulta',
    status        TEXT NOT NULL DEFAULT 'pendente',
    criado_em     TEXT NOT NULL,
    ultimo_acesso TEXT,
    tentativas_falhas INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate TEXT
);

CREATE TABLE IF NOT EXISTS notas_fiscais (
    chave_nf        TEXT PRIMARY KEY,
    numero_nf       TEXT,
    fornecedor      TEXT,
    fornecedor_cnpj TEXT,
    data_importacao TEXT NOT NULL,
    usuario         TEXT
);

CREATE TABLE IF NOT EXISTS nf_itens (
    id_item      TEXT PRIMARY KEY,
    chave_nf     TEXT NOT NULL REFERENCES notas_fiscais(chave_nf) ON DELETE CASCADE,
    xProd        TEXT,
    cEAN         TEXT,
    nLote        TEXT,
    dFab         TEXT,
    dVal         TEXT,
    vUnCom       REAL DEFAULT 0,
    qtd_total    INTEGER DEFAULT 0,
    qtd_pendente INTEGER DEFAULT 0,
    criado_em    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS atendimentos (
    id_atendimento    TEXT PRIMARY KEY,
    prontuario        TEXT NOT NULL,
    paciente          TEXT,
    unidade           TEXT NOT NULL DEFAULT 'BLOCO CIRURGICO',
    sala              TEXT NOT NULL,
    especialidade     TEXT NOT NULL,
    data_procedimento TEXT NOT NULL,
    hora_inicio       TEXT,
    codigo_cirurgia   TEXT,
    opme_solicitado   TEXT,
    observacao        TEXT,
    -- 'agenda' quando veio do CSV do AGHU, 'manual' quando alguém cadastrou na
    -- tela. Atendimento cadastrado à mão nunca pode ser escondido por filtro:
    -- se alguém digitou, é porque precisa dele.
    origem            TEXT NOT NULL DEFAULT 'agenda',
    status            TEXT NOT NULL DEFAULT 'aberto',
    criado_em         TEXT NOT NULL,
    criado_por        TEXT,
    encerrado_em      TEXT,
    encerrado_por     TEXT,
    UNIQUE (prontuario, unidade, sala, especialidade, data_procedimento)
);

CREATE TABLE IF NOT EXISTS unidades (
    id_unidade       TEXT PRIMARY KEY,
    codigo_barras    TEXT NOT NULL,
    codigo_aghu      TEXT,
    xProd            TEXT NOT NULL,
    marca_fabricante TEXT,
    fornecedor       TEXT,
    nLote            TEXT,
    numero_serie     TEXT,
    dFab             TEXT,
    dVal             TEXT,
    vUnCom           REAL DEFAULT 0,
    cEAN             TEXT,
    origem           TEXT NOT NULL DEFAULT 'manual',
    chave_nf         TEXT,
    numero_nf        TEXT,
    id_item_nf       TEXT,
    tipo_entrada     TEXT NOT NULL DEFAULT 'aquisicao_propria',
    -- Farmácia satélite de destino, definida no envio pelo almoxarifado.
    -- Os estoques das duas farmácias são separados: ver config.FARMACIAS.
    farmacia         TEXT,
    -- Caixa que contém este item agora, ou NULL quando ele está solto.
    -- Ver a tabela `caixas` e `services/caixas.py`.
    id_caixa         TEXT,
    -- Caixa a que este item se destina, enquanto ainda está a caminho dela.
    caixa_destino    TEXT,
    status           TEXT NOT NULL,
    id_atendimento   TEXT REFERENCES atendimentos(id_atendimento),
    criado_em        TEXT NOT NULL,
    criado_por       TEXT,
    atualizado_em    TEXT,
    atualizado_por   TEXT
);

-- Caixa da especialidade: o estoque que anda em conjunto.
--
-- Uma caixa por especialidade (ortopedia, vascular…), montada uma vez e
-- completada continuamente à medida que o fornecedor repõe. Ela circula
-- almoxarifado → farmácia → sala e volta, e só é aberta na sala, no uso.
--
-- A caixa é um CONTÊINER, não um item novo: as unidades lá dentro continuam
-- tendo o seu próprio `status`, exatamente como as soltas. Bipar a caixa aplica
-- a operação a todas elas numa transação só.
--
-- Foi essa a escolha de projeto porque o contrário — dar estado à caixa e deixar
-- os itens "suspensos" enquanto ela está fechada — apagaria justamente a
-- resposta que um recall precisa: onde está o material do lote X agora.
CREATE TABLE IF NOT EXISTS caixas (
    id_caixa       TEXT PRIMARY KEY,
    nome           TEXT NOT NULL,
    especialidade  TEXT NOT NULL,
    farmacia       TEXT,
    -- Espelha o status das unidades de dentro. É gravado, não derivado, e por
    -- construção não diverge: a única forma de uma unidade mudar de estado
    -- sozinha é sair da caixa.
    status         TEXT NOT NULL,
    id_atendimento TEXT REFERENCES atendimentos(id_atendimento),
    observacao     TEXT,
    criado_em      TEXT NOT NULL,
    criado_por     TEXT,
    atualizado_em  TEXT,
    atualizado_por TEXT,
    encerrada_em   TEXT,
    encerrada_por  TEXT
);

-- Composição esperada da caixa: quantos itens de cada produto ela deve ter
-- quando está completa. É daqui que sai a lista de reposição — sem uma meta,
-- "o que falta" não teria como ser respondido, só "o que saiu".
--
-- A grade muda com o tempo, conforme a demanda real; por isso toda alteração
-- passa por `caixa_grade_historico`, com motivo.
CREATE TABLE IF NOT EXISTS caixa_grade (
    id_caixa      TEXT NOT NULL REFERENCES caixas(id_caixa),
    codigo_aghu   TEXT NOT NULL,
    descricao     TEXT NOT NULL,
    quantidade    INTEGER NOT NULL,
    observacao    TEXT,
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT,
    PRIMARY KEY (id_caixa, codigo_aghu)
);

CREATE TABLE IF NOT EXISTS caixa_grade_historico (
    id_registro         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_caixa            TEXT NOT NULL,
    codigo_aghu         TEXT NOT NULL,
    descricao           TEXT,
    quantidade_anterior INTEGER,
    quantidade_nova     INTEGER,
    motivo              TEXT,
    data_registro       TEXT NOT NULL,
    usuario             TEXT
);

-- Histórico de quais unidades passaram por qual caixa. É esta tabela que
-- responde "quais lotes já estiveram na caixa de ortopedia" — a pergunta que um
-- recall faz quando a caixa já rodou dezenas de cirurgias.
CREATE TABLE IF NOT EXISTS caixa_itens (
    id_caixa     TEXT NOT NULL REFERENCES caixas(id_caixa),
    id_unidade   TEXT NOT NULL REFERENCES unidades(id_unidade),
    entrou_em    TEXT NOT NULL,
    entrou_por   TEXT,
    saiu_em      TEXT,
    saiu_por     TEXT,
    motivo_saida TEXT,
    PRIMARY KEY (id_caixa, id_unidade, entrou_em)
);

CREATE TABLE IF NOT EXISTS eventos (
    id_evento       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_unidade      TEXT REFERENCES unidades(id_unidade),
    id_atendimento  TEXT,
    tipo            TEXT NOT NULL,
    status_anterior TEXT,
    status_novo     TEXT,
    usuario         TEXT,
    data_evento     TEXT NOT NULL,
    motivo          TEXT,
    observacao      TEXT,
    -- v17: auditoria da devolução — quem entregou (sala) e quem recebeu (farmácia).
    devolvido_por   TEXT,
    recebido_por    TEXT
);

-- v17: devolução em duas etapas. A sala bipa o que voltou sem uso (na sala ou
-- na porta da farmácia) e a farmácia confirma com a senha — na hora ou depois,
-- em Farmácia → Devoluções a confirmar. Até a confirmação nada é "devolvido".
CREATE TABLE IF NOT EXISTS devolucoes (
    id_devolucao    TEXT PRIMARY KEY,
    id_atendimento  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pendente',   -- pendente | confirmada
    devolvido_por   TEXT,
    criado_por      TEXT,
    criado_em       TEXT NOT NULL,
    confirmada_em   TEXT,
    confirmada_por  TEXT,
    recebido_por    TEXT,
    observacao      TEXT
);

CREATE TABLE IF NOT EXISTS devolucao_itens (
    id_item         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_devolucao    TEXT NOT NULL REFERENCES devolucoes(id_devolucao),
    tipo            TEXT NOT NULL DEFAULT 'item',        -- item | caixa
    id_unidade      TEXT,
    id_caixa        TEXT,
    quantidade      INTEGER,
    devolvido_por   TEXT,
    bipado_por      TEXT,
    bipado_em       TEXT NOT NULL,
    situacao        TEXT NOT NULL DEFAULT 'pendente',    -- pendente | recebido | nao_recebido | removido | ignorado
    resolvido_em    TEXT,
    resolvido_por   TEXT,
    motivo          TEXT
);

-- v17: dispensação da farmácia para a sala, por paciente. A farmácia bipa o
-- que separou; o operador da sala confirma o recebimento só com a senha.
-- Solicitação de OPME feita pela sala (o papel "Requisição de material"),
-- uma por atendimento. A farmácia vê na tela de dispensar e cada bip dá
-- "check" na linha do mesmo código AGHU. O dispensado é calculado a partir
-- dos itens da dispensação, então tirar/desfazer um bip já atualiza a lista.
CREATE TABLE IF NOT EXISTS solicitacoes (
    id_solicitacao      TEXT PRIMARY KEY,
    id_atendimento      TEXT NOT NULL UNIQUE,
    criado_por          TEXT,
    criado_em           TEXT NOT NULL,
    atualizado_por      TEXT,
    atualizado_em       TEXT,
    observacao          TEXT,
    -- "Finalizar dispensa" com item faltando exige o motivo.
    finalizada_em       TEXT,
    finalizada_por      TEXT,
    motivo_faltas       TEXT,
    -- v18.43: rodada atual (sobe quando a sala pede de novo depois de a
    -- farmácia ter finalizado) — ver solicitacao_itens.rodada.
    rodada              INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS solicitacao_itens (
    id_item             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_solicitacao      TEXT NOT NULL REFERENCES solicitacoes(id_solicitacao),
    formulario          TEXT NOT NULL,          -- chave do formulário, ou 'avulso'
    linha               INTEGER NOT NULL DEFAULT 0,
    codigos             TEXT NOT NULL DEFAULT '',  -- códigos AGHU separados por espaço
    descricao           TEXT NOT NULL,
    especificacao       TEXT,                   -- tipo/tamanho escrito pela sala
    quantidade          INTEGER NOT NULL,
    -- linha sem código AGHU: a farmácia marca à mão que atendeu
    atendido_manual_em  TEXT,
    atendido_manual_por TEXT,
    -- v18.43: a farmácia marca a linha que não tem como atender.
    falta_em            TEXT,
    falta_por           TEXT,
    falta_motivo        TEXT,
    -- v18.43: pedidos feitos depois de a farmácia finalizar ficam em rodadas
    -- separadas, para não se misturarem na tela de quem dispensa.
    rodada              INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_solic_itens ON solicitacao_itens(id_solicitacao);

-- Linha COM código AGHU atendida por material bipado com OUTRO código (código
-- mudou, cadastro com código errado…). A farmácia vincula, com motivo.
CREATE TABLE IF NOT EXISTS solicitacao_vinculos (
    id_vinculo      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_item         INTEGER NOT NULL REFERENCES solicitacao_itens(id_item),
    id_unidade      TEXT NOT NULL,
    motivo          TEXT NOT NULL,
    vinculado_por   TEXT,
    vinculado_em    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_solic_vinc ON solicitacao_vinculos(id_item);

-- Carga de estoque a partir da planilha de lotes do AGHU (cod_material,
-- material, marca_comercial, lote, validade, quantidade). Cada linha fica
-- pendente até o almoxarifado bipar o material: só no bip a unidade entra no
-- estoque (com o código de barras lido).
CREATE TABLE IF NOT EXISTS cargas_planilha (
    id_carga        TEXT PRIMARY KEY,
    arquivo         TEXT,
    criado_por      TEXT,
    criado_em       TEXT NOT NULL,
    linhas          INTEGER NOT NULL DEFAULT 0,
    unidades        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS carga_itens (
    id_item         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_carga        TEXT NOT NULL REFERENCES cargas_planilha(id_carga),
    codigo_aghu     TEXT NOT NULL,
    material        TEXT NOT NULL,
    marca           TEXT,
    lote            TEXT,
    serie           TEXT,
    dVal            TEXT,
    qtd_total       INTEGER NOT NULL,
    qtd_pendente    INTEGER NOT NULL,
    codigo_barras   TEXT,          -- aprendido no primeiro bip deste lote
    situacao        TEXT NOT NULL DEFAULT 'pendente'   -- pendente | concluido | cancelado
);
CREATE INDEX IF NOT EXISTS idx_carga_itens ON carga_itens(id_carga, situacao);
CREATE INDEX IF NOT EXISTS idx_carga_itens_cod ON carga_itens(codigo_barras);

-- Envio do almoxarifado para a farmácia (Bloco ou Hemodinâmica). O almoxarifado
-- bipa e finaliza o envio; a farmácia confere (lista ou bipando) e dá ciência.
-- O que não foi recebido vira pendência, com tratativa.
-- Caixa de consignado emprestada a uma SALA pelo dia (turno): a farmácia envia,
-- a sala dá ciência da caixa, bipa o uso de cada item no paciente e devolve a
-- caixa até as 23:59; a farmácia confere a caixa no retorno e reabastece.
CREATE TABLE IF NOT EXISTS caixa_turnos (
    id_turno        TEXT PRIMARY KEY,
    id_caixa        TEXT NOT NULL,
    unidade         TEXT NOT NULL,
    sala            TEXT NOT NULL,
    data            TEXT NOT NULL,
    prazo           TEXT NOT NULL,
    status          TEXT NOT NULL,   -- enviada | na_sala | devolvida | conferida | divergente | cancelada
    qtd_enviada     INTEGER NOT NULL DEFAULT 0,
    qtd_usada       INTEGER,
    qtd_voltou      INTEGER,
    qtd_faltou      INTEGER,
    enviada_em      TEXT NOT NULL,
    enviada_por     TEXT,
    recebida_em     TEXT,
    recebida_por    TEXT,
    recebida_nome   TEXT,
    devolvida_em    TEXT,
    devolvida_por   TEXT,
    devolvida_nome  TEXT,
    conferida_em    TEXT,
    conferida_por   TEXT,
    conferida_nome  TEXT,
    observacao      TEXT
);
CREATE TABLE IF NOT EXISTS caixa_turno_itens (
    id_turno        TEXT NOT NULL REFERENCES caixa_turnos(id_turno),
    id_unidade      TEXT NOT NULL,
    situacao        TEXT NOT NULL DEFAULT 'na_caixa',  -- na_caixa | usado | voltou | faltou
    id_atendimento  TEXT,
    PRIMARY KEY (id_turno, id_unidade)
);

CREATE TABLE IF NOT EXISTS remessas (
    id_remessa      TEXT PRIMARY KEY,
    farmacia        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'aberta',   -- aberta | enviada | conferida
    criado_por      TEXT,
    criado_em       TEXT NOT NULL,
    enviada_por     TEXT,
    enviada_em      TEXT,
    conferida_por   TEXT,
    conferida_nome  TEXT,
    conferida_em    TEXT,
    modo_conferencia TEXT,
    observacao      TEXT
);

CREATE TABLE IF NOT EXISTS remessa_itens (
    id_item         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_remessa      TEXT NOT NULL REFERENCES remessas(id_remessa),
    id_unidade      TEXT NOT NULL,
    bipado_por      TEXT,
    bipado_em       TEXT NOT NULL,
    situacao        TEXT NOT NULL DEFAULT 'pendente',  -- pendente | recebido | nao_recebido | removido
    resolvido_em    TEXT,
    resolvido_por   TEXT,
    tratativa       TEXT,      -- recebido_depois | voltou_almoxarifado | divergencia
    tratativa_motivo TEXT,
    conferido_em    TEXT,      -- v18.35: bipado na conferência, antes de dar ciência
    conferido_por   TEXT
);
CREATE INDEX IF NOT EXISTS idx_remessa_itens ON remessa_itens(id_remessa, situacao);
CREATE INDEX IF NOT EXISTS idx_remessa_itens_un ON remessa_itens(id_unidade, situacao);

CREATE TABLE IF NOT EXISTS dispensacoes (
    id_dispensacao  TEXT PRIMARY KEY,
    id_atendimento  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pendente',   -- pendente | confirmada
    criado_por      TEXT,
    criado_em       TEXT NOT NULL,
    confirmada_em   TEXT,
    confirmada_por  TEXT,
    recebido_por    TEXT
);

CREATE TABLE IF NOT EXISTS dispensacao_itens (
    id_item         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_dispensacao  TEXT NOT NULL REFERENCES dispensacoes(id_dispensacao),
    id_unidade      TEXT NOT NULL,
    id_caixa        TEXT,
    bipado_por      TEXT,
    bipado_em       TEXT NOT NULL,
    situacao        TEXT NOT NULL DEFAULT 'pendente',    -- pendente | recebido | removido
    resolvido_em    TEXT,
    resolvido_por   TEXT
);

-- v17 (out/2026): exceção das exceções — material usado na sala que NÃO estava
-- cadastrado pelo almoxarifado. A sala registra (com a senha da supervisão e a
-- etiqueta colada no prontuário); o almoxarifado regulariza depois.
CREATE TABLE IF NOT EXISTS nao_cadastrados (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_unidade              TEXT NOT NULL,
    id_atendimento          TEXT,
    registrado_em           TEXT NOT NULL,
    registrado_por          TEXT,
    autorizado_por          TEXT,
    motivo                  TEXT,
    detalhe                 TEXT,
    etiqueta_no_prontuario  INTEGER NOT NULL DEFAULT 0,
    situacao                TEXT NOT NULL DEFAULT 'pendente',   -- pendente | regularizado
    regularizado_em         TEXT,
    regularizado_por        TEXT,
    observacao              TEXT
);

-- v17: uso na sala sem dispensação — a farmácia precisa dar ciência.
CREATE TABLE IF NOT EXISTS usos_sem_dispensacao (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_unidade      TEXT NOT NULL,
    id_atendimento  TEXT,
    usado_em        TEXT NOT NULL,
    usado_por       TEXT,
    situacao        TEXT NOT NULL DEFAULT 'pendente',   -- pendente | ciente | cancelado
    ciente_em       TEXT,
    ciente_por      TEXT,
    ciente_nome     TEXT,
    observacao      TEXT
);

CREATE TABLE IF NOT EXISTS solicitacoes_acesso (
    id_solicitacao TEXT PRIMARY KEY,
    tipo           TEXT NOT NULL,
    username       TEXT NOT NULL,
    nome           TEXT,
    email          TEXT,
    setor          TEXT,
    papel          TEXT,
    senha_hash     TEXT,
    status         TEXT NOT NULL DEFAULT 'pendente',
    observacao     TEXT,
    criada_em      TEXT NOT NULL,
    atendida_em    TEXT,
    atendida_por   TEXT
);

CREATE TABLE IF NOT EXISTS metas (
    codigo        TEXT PRIMARY KEY,
    meta          REAL,
    atencao       REAL,
    atualizado_em TEXT,
    atualizado_por TEXT
);

CREATE TABLE IF NOT EXISTS empenhos (
    id_empenho       TEXT PRIMARY KEY,
    numero           TEXT NOT NULL,
    fornecedor       TEXT NOT NULL,
    -- "material" é a família coberta pelo empenho (ex.: "Cateter balão"), não um
    -- produto único — um empenho costuma cobrir várias medidas/especificações
    -- do mesmo material, todas debitando do mesmo saldo.
    material         TEXT NOT NULL,
    data_empenho     TEXT,
    quantidade_total INTEGER NOT NULL,
    valor_unitario   REAL NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'ativo',
    observacao       TEXT,
    criado_em        TEXT NOT NULL,
    criado_por       TEXT,
    encerrado_em     TEXT,
    encerrado_por    TEXT
);

CREATE TABLE IF NOT EXISTS empenho_vinculos (
    id_vinculo           TEXT PRIMARY KEY,
    id_empenho           TEXT NOT NULL REFERENCES empenhos(id_empenho),
    id_unidade           TEXT NOT NULL REFERENCES unidades(id_unidade),
    status               TEXT NOT NULL DEFAULT 'ativo',
    data_vinculo         TEXT NOT NULL,
    usuario              TEXT,
    observacao           TEXT,
    motivo_cancelamento  TEXT,
    cancelado_em         TEXT,
    cancelado_por        TEXT
);

-- v17: códigos AGHU cobertos por um empenho. O uso de uma unidade com um
-- desses códigos debita o saldo sozinho (ver empenhos.vincular_automatico).
CREATE TABLE IF NOT EXISTS empenho_aghu (
    id_empenho   TEXT NOT NULL REFERENCES empenhos(id_empenho),
    codigo_aghu  TEXT NOT NULL,
    PRIMARY KEY (id_empenho, codigo_aghu)
);

-- nov/2026: associação código consignado (do fornecedor/contrato) ↔ código
-- AGHU. Um código consignado aponta para um AGHU; vários consignados (de
-- fornecedores diferentes) podem apontar para o mesmo AGHU.
CREATE TABLE IF NOT EXISTS consignado_aghu (
    codigo_consignado TEXT PRIMARY KEY,
    codigo_aghu       TEXT NOT NULL,
    fornecedor        TEXT,
    descricao         TEXT,
    criado_em         TEXT NOT NULL,
    criado_por        TEXT,
    atualizado_em     TEXT,
    atualizado_por    TEXT
);
CREATE INDEX IF NOT EXISTS idx_consignado_aghu ON consignado_aghu(codigo_aghu);

-- nov/2026: códigos consignados cobertos por um empenho (com o AGHU associado
-- no momento do cadastro). O uso de uma unidade com esse código consignado
-- debita o saldo. `empenho_aghu` continua preenchida com os AGHU associados.
CREATE TABLE IF NOT EXISTS empenho_consignado (
    id_empenho        TEXT NOT NULL REFERENCES empenhos(id_empenho),
    codigo_consignado TEXT NOT NULL,
    codigo_aghu       TEXT,
    PRIMARY KEY (id_empenho, codigo_consignado)
);
CREATE INDEX IF NOT EXISTS idx_empenho_consignado ON empenho_consignado(codigo_consignado);

CREATE TABLE IF NOT EXISTS lotes_bloqueados (
    id_bloqueio   TEXT PRIMARY KEY,
    -- Identificação do lote afetado. `codigo_aghu` vazio bloqueia o lote em
    -- qualquer produto; preenchido, restringe ao produto daquele código.
    nLote         TEXT NOT NULL,
    codigo_aghu   TEXT,
    fornecedor    TEXT,
    motivo        TEXT NOT NULL,
    referencia    TEXT,
    status        TEXT NOT NULL DEFAULT 'ativo',
    criado_em     TEXT NOT NULL,
    criado_por    TEXT,
    liberado_em   TEXT,
    liberado_por  TEXT,
    motivo_liberacao TEXT
);

CREATE TABLE IF NOT EXISTS alertas (
    id_alerta      TEXT PRIMARY KEY,
    modulo_destino TEXT NOT NULL,
    titulo         TEXT NOT NULL,
    mensagem       TEXT NOT NULL,
    id_atendimento TEXT,
    id_unidade     TEXT,
    ids_unidade    TEXT,
    -- Caminho interno opcional (ex.: "/consignados/empenhos/EMP-123") para o
    -- alerta linkar direto ao registro que originou o aviso, quando não é uma
    -- unidade individual (como o alerta de saldo de empenho).
    link           TEXT,
    status         TEXT NOT NULL DEFAULT 'aberto',
    criado_em      TEXT NOT NULL,
    criado_por     TEXT,
    resolvido_em   TEXT,
    resolvido_por  TEXT
);

-- Histórico de marca/fabricante já vistos para um código de barras (cEAN).
-- NÃO é fonte de verdade e nunca preenche nada sozinho: o "fornecedor" da NF-e
-- é quase sempre um distribuidor ou operador logístico, não o fabricante, e o
-- mesmo código de compra pode ser atendido por marcas diferentes a cada
-- pregão/lote. Guardar aqui serve só para oferecer as marcas já vistas como
-- sugestão (autocomplete) — quem recebe sempre confere e digita/escolhe a
-- marca real desta entrega.
CREATE TABLE IF NOT EXISTS historico_produtos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo           TEXT NOT NULL,
    xProd            TEXT,
    codigo_aghu      TEXT,
    marca_fabricante TEXT NOT NULL,
    fornecedor_cnpj  TEXT,
    fornecedor       TEXT,
    criado_em        TEXT NOT NULL,
    criado_por       TEXT,
    UNIQUE(codigo, marca_fabricante, codigo_aghu)
);
CREATE INDEX IF NOT EXISTS idx_hist_produtos_codigo ON historico_produtos(codigo);

-- Catálogo mestre de materiais do hospital: liga o código AGHU ao nome
-- oficial do material (planilha de licitações vigentes, ex.: MasterTools).
-- Esse nome é diferente do texto que o fornecedor usa na NF-e (`xProd`) — é
-- o descritivo que o hospital usa nos próprios relatórios. Ao contrário de
-- marca/fabricante, um código AGHU tem um único descritivo aqui, então pode
-- ser preenchido sozinho quando o código é reconhecido.
-- v17: códigos AGHU cuja caixa/embalagem precisa ser recolhida e entregue ao
-- paciente. Ao bipar o uso de um desses, a tela mostra um aviso vermelho e
-- quem bipou dá ciência (evento `ciencia_entrega_paciente`).
CREATE TABLE IF NOT EXISTS aghu_entrega_paciente (
    codigo_aghu  TEXT PRIMARY KEY,
    observacao   TEXT,
    criado_em    TEXT NOT NULL,
    criado_por   TEXT
);

-- nov/2026: "Reportar problema" — chamados abertos por qualquer usuário e
-- tratados pela Administração.
CREATE TABLE IF NOT EXISTS chamados (
    id_chamado    INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em     TEXT NOT NULL,
    criado_por    TEXT NOT NULL,
    criado_nome   TEXT,
    pagina        TEXT,
    versao        TEXT,
    descricao     TEXT NOT NULL,
    imagem        TEXT,
    status        TEXT NOT NULL DEFAULT 'aberto',
    resposta      TEXT,
    atualizado_em TEXT,
    atualizado_por TEXT
);

-- v18: devolução ao fornecedor com número (um fornecedor por devolução).
CREATE TABLE IF NOT EXISTS devolucoes_fornecedor (
    id_devolucao   TEXT PRIMARY KEY,
    ano            INTEGER NOT NULL,
    numero         INTEGER NOT NULL,
    fornecedor     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'aberta',   -- aberta | finalizada | cancelada
    criada_em      TEXT NOT NULL,
    criada_por     TEXT,
    finalizada_em  TEXT,
    finalizada_por TEXT,
    cancelada_em   TEXT,
    cancelada_por  TEXT,
    motivo_cancelamento TEXT,
    legado         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS devolucao_fornecedor_itens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_devolucao    TEXT NOT NULL REFERENCES devolucoes_fornecedor(id_devolucao),
    id_unidade      TEXT NOT NULL,
    status_anterior TEXT,
    farmacia_anterior TEXT,
    motivo          TEXT,
    adicionado_em   TEXT NOT NULL,
    adicionado_por  TEXT,
    situacao        TEXT NOT NULL DEFAULT 'ativo',    -- ativo | cancelado | desfeito
    cancelado_em    TEXT,
    cancelado_por   TEXT,
    motivo_cancelamento TEXT
);

-- v18.3: chamados da sala (maqueiro / limpeza) para o QG da enfermagem.
CREATE TABLE IF NOT EXISTS chamados_sala (
    id_chamado      TEXT PRIMARY KEY,
    tipo            TEXT NOT NULL,                       -- maqueiro | limpeza
    motivo          TEXT,
    observacao      TEXT,
    unidade         TEXT NOT NULL,
    sala            TEXT NOT NULL,
    id_atendimento  TEXT,
    status          TEXT NOT NULL DEFAULT 'aberto',      -- aberto | direcionado | atendido | cancelado
    criado_em       TEXT NOT NULL,
    criado_por      TEXT,
    direcionado_em  TEXT,
    direcionado_por TEXT,
    responsavel     TEXT,
    atendido_em     TEXT,
    atendido_por    TEXT,
    cancelado_em    TEXT,
    cancelado_por   TEXT,
    motivo_cancelamento TEXT
);
CREATE INDEX IF NOT EXISTS idx_chamados_status ON chamados_sala(status, criado_em);

CREATE TABLE IF NOT EXISTS materiais_mestre (
    codigo_aghu             TEXT PRIMARY KEY,
    codigo_master           TEXT,
    descritivo_hospital     TEXT NOT NULL,
    valor_unitario_licitado REAL,
    atualizado_em           TEXT NOT NULL,
    atualizado_por          TEXT
);

-- Contagem periódica de inventário. Cada contagem cobre UM local (o
-- almoxarifado ou uma das farmácias), porque é assim que ela acontece
-- fisicamente: a pessoa está de pé em um estoque só.
--
-- O inventário NÃO move material. Ele compara o que foi bipado com o que o
-- sistema esperava ali e entrega a lista de pendências; corrigir é decisão de
-- quem lê o relatório, feita depois pelas operações normais, com motivo. Por
-- isso não há evento em `eventos` vindo daqui: nada mudou de estado.
CREATE TABLE IF NOT EXISTS inventarios (
    id_inventario TEXT PRIMARY KEY,
    local         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'aberto',
    observacao    TEXT,
    criado_em     TEXT NOT NULL,
    criado_por    TEXT,
    encerrado_em  TEXT,
    encerrado_por TEXT
);

-- Uma linha por leitura, na ordem em que aconteceram. `id_unidade` fica nulo
-- quando o código bipado não corresponde a material nenhum do cadastro.
CREATE TABLE IF NOT EXISTS inventario_leituras (
    id_leitura        INTEGER PRIMARY KEY AUTOINCREMENT,
    id_inventario     TEXT NOT NULL REFERENCES inventarios(id_inventario) ON DELETE CASCADE,
    codigo_lido       TEXT NOT NULL,
    id_unidade        TEXT,
    situacao          TEXT NOT NULL,
    status_no_sistema TEXT,
    lido_em           TEXT NOT NULL,
    lido_por          TEXT
);

"""

# Os índices ficam separados do esquema de propósito: eles só podem ser criados
# depois de `_migrar`, porque alguns apontam para colunas que só existem em
# bancos novos. Num banco criado por uma versão anterior, o CREATE TABLE IF NOT
# EXISTS não acrescenta a coluna nova — quem acrescenta é o ALTER TABLE do
# `_migrar`. Criar o índice antes disso quebrava a abertura do banco com
# "no such column".
INDICES = """
CREATE INDEX IF NOT EXISTS idx_uni_codigo     ON unidades(codigo_barras);
CREATE INDEX IF NOT EXISTS idx_uni_status     ON unidades(status);
CREATE INDEX IF NOT EXISTS idx_uni_atend      ON unidades(id_atendimento);
CREATE INDEX IF NOT EXISTS idx_uni_farmacia   ON unidades(farmacia, status);
CREATE INDEX IF NOT EXISTS idx_uni_lote       ON unidades(codigo_barras, nLote);
CREATE INDEX IF NOT EXISTS idx_uni_val        ON unidades(dVal);
CREATE INDEX IF NOT EXISTS idx_ev_unidade     ON eventos(id_unidade);
CREATE INDEX IF NOT EXISTS idx_ev_atend       ON eventos(id_atendimento);
CREATE INDEX IF NOT EXISTS idx_ev_data        ON eventos(data_evento);
CREATE INDEX IF NOT EXISTS idx_atend_data     ON atendimentos(data_procedimento);
CREATE INDEX IF NOT EXISTS idx_atend_pront    ON atendimentos(prontuario);
CREATE INDEX IF NOT EXISTS idx_nfi_chave      ON nf_itens(chave_nf);
CREATE INDEX IF NOT EXISTS idx_alerta_modulo  ON alertas(modulo_destino, status);
CREATE INDEX IF NOT EXISTS idx_emp_fornecedor ON empenhos(fornecedor);
CREATE INDEX IF NOT EXISTS idx_emp_status     ON empenhos(status);
CREATE INDEX IF NOT EXISTS idx_vin_empenho    ON empenho_vinculos(id_empenho, status);
CREATE INDEX IF NOT EXISTS idx_vin_unidade    ON empenho_vinculos(id_unidade, status);
CREATE INDEX IF NOT EXISTS idx_bloq_lote      ON lotes_bloqueados(nLote, status);
CREATE INDEX IF NOT EXISTS idx_dev_atend      ON devolucoes(id_atendimento, status);
CREATE INDEX IF NOT EXISTS idx_devi_dev       ON devolucao_itens(id_devolucao, situacao);
CREATE INDEX IF NOT EXISTS idx_devi_unidade   ON devolucao_itens(id_unidade, situacao);
CREATE INDEX IF NOT EXISTS idx_disp_atend     ON dispensacoes(id_atendimento, status);
CREATE INDEX IF NOT EXISTS idx_dispi_disp     ON dispensacao_itens(id_dispensacao, situacao);
CREATE INDEX IF NOT EXISTS idx_dispi_unidade  ON dispensacao_itens(id_unidade, situacao);

CREATE INDEX IF NOT EXISTS idx_uni_caixa      ON unidades(id_caixa);
CREATE INDEX IF NOT EXISTS idx_uni_cx_destino  ON unidades(caixa_destino);
CREATE INDEX IF NOT EXISTS idx_caixa_status   ON caixas(status);
CREATE INDEX IF NOT EXISTS idx_caixa_espec    ON caixas(especialidade);
CREATE INDEX IF NOT EXISTS idx_cxi_caixa      ON caixa_itens(id_caixa);

CREATE INDEX IF NOT EXISTS idx_inv_status     ON inventarios(status, criado_em);
CREATE INDEX IF NOT EXISTS idx_invl_inv       ON inventario_leituras(id_inventario);
CREATE INDEX IF NOT EXISTS idx_invl_unidade   ON inventario_leituras(id_inventario, id_unidade);

-- O invariante que segura o modelo inteiro: uma unidade está em no máximo uma
-- caixa aberta. Sem isto, um erro de operação poderia colocar o mesmo item em
-- duas caixas e as duas se moveriam achando que o têm.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cxi_unidade_aberta
    ON caixa_itens(id_unidade) WHERE saiu_em IS NULL;

-- Uma unidade não pode ter dois vínculos ativos de empenho ao mesmo tempo. A
-- regra também é checada no serviço, mas só o banco garante isso quando duas
-- pessoas vinculam o mesmo item no mesmo instante.
CREATE UNIQUE INDEX IF NOT EXISTS idx_vin_unico
    ON empenho_vinculos(id_unidade) WHERE status = 'ativo';
"""


COLUNAS_NOVAS = {
    # nov/2026: foto da etiqueta tirada pela câmera (opcional) no material não cadastrado.
    "nao_cadastrados": [("foto", "TEXT")],
    # nov/2026: a mesma estrutura serve ao envio almoxarifado → farmácia e à
    # devolução farmácia → almoxarifado; e quem enviou pode cancelar antes da ciência.
    # nov/2026: a NF trouxe o número de série no campo lote (um lote por unidade).
    "nf_itens": [("lote_e_serie", "INTEGER DEFAULT 0")],
    # v18.35: conferência do recebimento gravada bipe a bipe, para a farmácia
    # poder parar no meio e continuar depois (ou outra pessoa continuar).
    "remessa_itens": [("conferido_em", "TEXT"), ("conferido_por", "TEXT")],
    "remessas": [("sentido", "TEXT NOT NULL DEFAULT 'almox_farmacia'"), ("cancelada_em", "TEXT"),
                 ("cancelada_por", "TEXT"), ("motivo_cancelamento", "TEXT"),
                 # v18: transferência entre farmácias — de qual farmácia saiu.
                 ("farmacia_origem", "TEXT")],
    # Solicitação de OPME cancelada junto com o procedimento.
    "solicitacoes": [("cancelada_em", "TEXT"), ("cancelada_por", "TEXT"),
                     # v18.43: rodada atual do pedido (ver solicitacao_itens.rodada)
                     ("rodada", "INTEGER NOT NULL DEFAULT 1"),
                     # v18.7.3: a sala pode cancelar a solicitação (com motivo)
                     ("motivo_cancelamento", "TEXT")],
    # v18.43: falta de estoque por linha e rodada do pedido (ver CREATE TABLE).
    "solicitacao_itens": [("falta_em", "TEXT"), ("falta_por", "TEXT"), ("falta_motivo", "TEXT"),
                          ("rodada", "INTEGER NOT NULL DEFAULT 1")],
    # v18.4.5: conferência do "não recebido" pela farmácia (a divergência inicial fica registrada).
    "dispensacao_itens": [("tratativa", "TEXT"), ("tratativa_em", "TEXT"), ("tratativa_por", "TEXT")],
    # v17: auditoria da devolução — nomes de quem devolveu e de quem recebeu.
    "eventos": [
        ("devolvido_por", "TEXT"),
        ("recebido_por", "TEXT"),
    ],
    # v17: caixas de consignado — fornecedor e bloqueio por divergência na devolução.
    # nov/2026: `local` (almoxarifado | transito | farmacia; vazio = farmácia, como
    # antes) e o envio da caixa do almoxarifado para a farmácia, com a ciência.
    "caixas": [("local", "TEXT"), ("envio_farmacia", "TEXT"), ("enviada_em", "TEXT"), ("enviada_por", "TEXT"),
               ("recebida_em", "TEXT"), ("recebida_por", "TEXT"), ("recebida_nome", "TEXT"),
        ("fornecedor", "TEXT"),
        ("bloqueada", "INTEGER NOT NULL DEFAULT 0"),
        ("bloqueio_motivo", "TEXT"),
        ("bloqueio_atendimento", "TEXT"),
        ("bloqueada_em", "TEXT"),
        ("bloqueada_por", "TEXT"),
    ],
    # v17: saldo (em unidades) a partir do qual o sistema pede novo empenho.
    "empenhos": [
        ("limite_seguranca", "INTEGER"),
        # v17: dados da licitação (cadastro manual ou planilha).
        ("vigencia_inicio", "TEXT"),
        ("vigencia_fim", "TEXT"),
        ("numero_processo", "TEXT"),
        ("numero_pregao", "TEXT"),
        ("numero_registro", "TEXT"),
    ],
    "atendimentos": [
        # v18.6: Nota de Consumo no AGHU (farmácia lança o que foi usado no paciente).
        ("aghu_consumo_status", "TEXT NOT NULL DEFAULT ''"),
        ("aghu_consumo_iniciado_em", "TEXT"),
        ("aghu_consumo_iniciado_por", "TEXT"),
        ("aghu_consumo_lancado_em", "TEXT"),
        ("aghu_consumo_lancado_por", "TEXT"),
        # v18.7: robô no computador de quem lança — código de uso único do link
        ("aghu_consumo_token", "TEXT"),
        ("aghu_consumo_token_expira", "TEXT"),
        # v18.8: Requisição de Material (RM) no AGHU — situação própria, separada da nota de consumo
        ("aghu_rm_status", "TEXT NOT NULL DEFAULT ''"),
        ("aghu_rm_iniciado_em", "TEXT"), ("aghu_rm_iniciado_por", "TEXT"),
        ("aghu_rm_lancado_em", "TEXT"), ("aghu_rm_lancado_por", "TEXT"),
        ("aghu_rm_token", "TEXT"), ("aghu_rm_token_expira", "TEXT"),
        # v18.3: a sala registra quando ABRIU (botão "Abrir sala"). `sala_aberta_auto`
        # = 1 quando a abertura foi registrada sozinha (a sala deu ciência ou bipou
        # sem ter clicado em "Abrir sala").
        ("sala_aberta_em", "TEXT"),
        ("sala_aberta_por", "TEXT"),
        ("sala_aberta_auto", "INTEGER NOT NULL DEFAULT 0"),
        # v17 (out/2026): a sala finaliza os materiais utilizados; o encerramento
        # é da farmácia, depois da ciência dos não utilizados.
        ("uso_finalizado_em", "TEXT"),
        ("uso_finalizado_por", "TEXT"),
        ("unidade", "TEXT NOT NULL DEFAULT 'BLOCO CIRURGICO'"),
        ("hora_inicio", "TEXT"),
        ("codigo_cirurgia", "TEXT"),
        ("opme_solicitado", "TEXT"),
        ("origem", "TEXT NOT NULL DEFAULT 'agenda'"),
        # v17: procedimento previsto que não aconteceu.
        ("cancelado_em", "TEXT"),
        ("cancelado_por", "TEXT"),
        ("motivo_cancelamento", "TEXT"),
        ("detalhe_cancelamento", "TEXT"),
    ],
    "unidades": [
        ("farmacia", "TEXT"),
        # Nome oficial do material segundo o catálogo mestre do hospital
        # (materiais_mestre), pelo código AGHU — separado de `xProd`, que é a
        # descrição que o fornecedor usa na NF-e ou que foi digitada no
        # cadastro manual.
        ("descritivo_hospital", "TEXT"),
        # Atalho para a caixa que contém o item agora (NULL = solto). A verdade
        # histórica está em `caixa_itens`; esta coluna existe para a bipagem
        # poder recusar item que está dentro de caixa sem um JOIN a cada leitura.
        ("id_caixa", "TEXT"),
        # Caixa para a qual este item foi separado, mas em que ele ainda não
        # entrou fisicamente — ele está a caminho. Sem isto, o almoxarifado
        # veria a mesma falta duas vezes e mandaria material repetido.
        ("caixa_destino", "TEXT"),
        # nov/2026: código do consignado (informado na entrada quando a
        # classificação é "Consignado").
        ("codigo_consignado", "TEXT"),
    ],
    "usuarios": [
        ("tentativas_falhas", "INTEGER NOT NULL DEFAULT 0"),
        ("bloqueado_ate", "TEXT"),
    ],
    "notas_fiscais": [
        ("fornecedor_cnpj", "TEXT"),
        # nov/2026: lançamento da NF no AGHU pelo robô (ou à mão) — situação e quem lançou.
        ("aghu_status", "TEXT"), ("aghu_iniciado_em", "TEXT"), ("aghu_iniciado_por", "TEXT"),
        ("aghu_lancada_em", "TEXT"), ("aghu_lancada_por", "TEXT"), ("aghu_nr", "TEXT"),
        ("aghu_token", "TEXT"), ("aghu_token_expira", "TEXT"),
    ],
    "alertas": [
        # Bancos criados antes desta coluna existir tinham só uma unidade por
        # alerta (ou nenhuma) — sem isto, o alerta avisava mas não dava para
        # abrir o item específico para tratar.
        ("ids_unidade", "TEXT"),
        ("link", "TEXT"),
    ],
}


def _descricao_consignado(conn: sqlite3.Connection) -> None:
    """v18.11.5 (uma vez): consignado já cadastrado passa a mostrar a descrição do
    próprio material (relação consignado × AGHU ou a da NF/cadastro), não a do AGHU."""
    conn.execute("CREATE TABLE IF NOT EXISTS migracoes_feitas (nome TEXT PRIMARY KEY, feita_em TEXT)")
    if conn.execute("SELECT 1 FROM migracoes_feitas WHERE nome = 'v18_11_5_desc_consignado'").fetchone():
        return
    conn.execute("""UPDATE unidades SET descritivo_hospital = COALESCE(
                        NULLIF((SELECT c.descricao FROM consignado_aghu c
                                WHERE c.codigo_consignado = unidades.codigo_consignado), ''),
                        NULLIF(xProd, ''), descritivo_hospital)
                    WHERE tipo_entrada = 'consignado'""")
    conn.execute("INSERT INTO migracoes_feitas VALUES ('v18_11_5_desc_consignado', datetime('now'))")
    conn.commit()


def _padronizar_lotes(conn: sqlite3.Connection) -> None:
    """v18.11: lote não diferencia maiúscula de minúscula ("SP77…" = "sp77…").
    Guarda tudo em MAIÚSCULA, como no AGHU e nas NF (e sem espaço nas pontas) — os antigos e os novos (gatilhos)."""
    conn.executescript("""
        UPDATE unidades SET nLote = UPPER(TRIM(nLote)) WHERE nLote IS NOT NULL AND nLote <> UPPER(TRIM(nLote));
        UPDATE carga_itens SET lote = UPPER(TRIM(lote)) WHERE lote IS NOT NULL AND lote <> UPPER(TRIM(lote));
        CREATE TRIGGER IF NOT EXISTS trg_lote_mai_ins AFTER INSERT ON unidades
          WHEN NEW.nLote IS NOT NULL AND NEW.nLote <> UPPER(TRIM(NEW.nLote))
          BEGIN UPDATE unidades SET nLote = UPPER(TRIM(NEW.nLote)) WHERE rowid = NEW.rowid; END;
        CREATE TRIGGER IF NOT EXISTS trg_lote_mai_upd AFTER UPDATE OF nLote ON unidades
          WHEN NEW.nLote IS NOT NULL AND NEW.nLote <> UPPER(TRIM(NEW.nLote))
          BEGIN UPDATE unidades SET nLote = UPPER(TRIM(NEW.nLote)) WHERE rowid = NEW.rowid; END;
        CREATE TRIGGER IF NOT EXISTS trg_carga_lote_mai_ins AFTER INSERT ON carga_itens
          WHEN NEW.lote IS NOT NULL AND NEW.lote <> UPPER(TRIM(NEW.lote))
          BEGIN UPDATE carga_itens SET lote = UPPER(TRIM(NEW.lote)) WHERE rowid = NEW.rowid; END;
    """)
    conn.commit()


def _migrar(conn: sqlite3.Connection) -> None:
    """Acrescenta colunas novas a bancos criados por versões anteriores.

    O CREATE TABLE IF NOT EXISTS não altera tabela existente, então uma base já
    em uso não ganharia as colunas novas sem isto.
    """
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = {linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")}
        if not existentes:
            continue
        for nome, definicao in colunas:
            if nome not in existentes:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")

    _padronizar_especialidades(conn)

    # "recebimento" virou "almoxarifado" e "bloco" virou "sala-procedimento" na
    # versão 15. Sem isto, quem já tinha login perderia o acesso ao próprio módulo.
    from .security import PAPEIS_RENOMEADOS
    for antigo, novo in PAPEIS_RENOMEADOS.items():
        conn.execute("UPDATE usuarios SET papel = ? WHERE papel = ?", (novo, antigo))


def _padronizar_especialidades(conn: sqlite3.Connection) -> None:
    """Regrava com o nome padronizado as especialidades já gravadas ("CIR GERAL",
    "CARDIO"…). Roda a cada início, mas só altera o que ainda estiver fora do padrão.
    Se a troca colidir com um atendimento idêntico já existente (mesmo prontuário,
    sala, unidade e data), aquele registro fica como está para não perder nada."""
    from .utils import padronizar_especialidade
    for tabela in ("atendimentos", "caixas"):
        existentes = {linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")}
        if "especialidade" not in existentes:
            continue
        for (atual,) in conn.execute(
                f"SELECT DISTINCT especialidade FROM {tabela}").fetchall():
            novo = padronizar_especialidade(atual)
            if novo and novo != atual:
                conn.execute(f"UPDATE OR IGNORE {tabela} SET especialidade = ? "
                             f"WHERE especialidade = ?", (novo, atual))


def _descartar_caixas_da_previa(conn: sqlite3.Connection) -> None:
    """Descarta a primeira modelagem de caixa, que não chegou a ser usada.

    A versão inicial tratava a caixa como um evento (montada, lacrada, enviada,
    reaberta, com `ciclo`). O desenho correto é outro: a caixa é da
    especialidade, existe uma vez e é completada continuamente. `tipo`, `ciclo` e
    `lacrada` não têm mais sentido.

    O CREATE TABLE IF NOT EXISTS não altera tabela existente, então a estrutura
    antiga sobreviveria com as colunas erradas. Aqui ela é derrubada — mas
    **somente se estiver vazia**. Com dados dentro, o banco é deixado como está e
    um aviso vai para o log: descartar movimentação de material registrada seria
    inaceitável, mesmo em estrutura obsoleta.
    """
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='caixas'").fetchone()
    if not existe:
        return
    colunas = {linha[1] for linha in conn.execute("PRAGMA table_info(caixas)")}
    if not {"tipo", "ciclo", "lacrada"} & colunas:
        return  # já está no formato novo

    if conn.execute("SELECT COUNT(*) FROM caixas").fetchone()[0]:
        from . import log
        log.aviso(
            "a tabela `caixas` está na modelagem antiga (tipo/ciclo/lacrada) e tem "
            "dados: nada foi descartado. Migre à mão antes de usar as caixas novas.")
        return

    conn.execute("DROP TABLE IF EXISTS caixa_itens")
    conn.execute("DROP TABLE IF EXISTS caixas")


def inicializar() -> None:
    """Cria ou atualiza o banco. A ordem das etapas importa.

    A estrutura obsoleta de caixa sai primeiro, senão o CREATE TABLE IF NOT
    EXISTS a manteria intacta. Depois as tabelas, depois as colunas novas em
    bancos antigos, e só então os índices — que podem depender dessas colunas.
    """
    conn = conectar()
    try:
        _descartar_caixas_da_previa(conn)
        conn.executescript(ESQUEMA)
        _migrar(conn)
        conn.executescript(INDICES)
        _travas_de_duplicidade(conn)
        _limpar_codigo_master(conn)
        _padronizar_lotes(conn)
        _descricao_consignado(conn)
    finally:
        conn.close()
    _criar_admin_inicial()


def _limpar_codigo_master(conn) -> None:
    """v18.4.7: código master importado com ponto ("1.234", "22.") fica sem o ponto."""
    import re as _re
    for codigo_aghu, master in conn.execute(
            "SELECT codigo_aghu, codigo_master FROM materiais_mestre WHERE codigo_master LIKE '%.%'").fetchall():
        limpo = str(master).strip()
        if _re.fullmatch(r"\d+\.0+", limpo):
            limpo = limpo.split(".")[0]
        limpo = _re.sub(r"[.\s]", "", limpo)
        conn.execute("UPDATE materiais_mestre SET codigo_master = ? WHERE codigo_aghu = ?", (limpo, codigo_aghu))


def _travas_de_duplicidade(conn) -> None:
    """v18.4.1: o próprio banco recusa a mesma unidade duas vezes "em aberto".

    É a segunda linha de defesa contra cliques simultâneos (a primeira é a
    conferência dentro da transação, nos serviços). Se o banco já tiver
    duplicidade antiga, o índice não é criado e fica o aviso no log."""
    from . import log
    travas = {
        "ux_remessa_item_pendente":
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_remessa_item_pendente ON remessa_itens(id_unidade) "
            "WHERE situacao = 'pendente'",
        "ux_devolucao_item_pendente":
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_devolucao_item_pendente ON devolucao_itens(id_unidade) "
            "WHERE situacao = 'pendente' AND id_unidade IS NOT NULL",
    }
    for nome, sql in travas.items():
        try:
            conn.execute(sql)
        except sqlite3.IntegrityError:
            log.erro(f"índice {nome} não criado: já há duplicidade antiga no banco (ver diagnóstico)")


def _criar_admin_inicial() -> None:
    from .config import ADMIN_PADRAO, SENHA_ADMIN_PADRAO
    from .security import gerar_hash

    if escalar("SELECT COUNT(*) FROM usuarios") > 0:
        # nov/2026: com o AD ligado, o login de rede em OPME_ADMIN sempre tem
        # acesso de administrador — mesmo num banco que já tem outros usuários
        # (ex.: instalação nova em outro computador). Se já existe, nada muda.
        from ....config import settings
        login = (ADMIN_PADRAO or "").strip()
        if settings.ad_configurado() and login and login != "admin" and not escalar(
                "SELECT COUNT(*) FROM usuarios WHERE username = ?", (login,)):
            executar(
                """INSERT INTO usuarios (username, senha_hash, nome, email, setor, papel, status, criado_em)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (login, gerar_hash(SENHA_ADMIN_PADRAO), login, "", "", "admin", "ativo", agora()))
        return

    executar(
        """INSERT INTO usuarios (username, senha_hash, nome, email, setor, papel, status, criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (ADMIN_PADRAO, gerar_hash(SENHA_ADMIN_PADRAO), "Administrador",
         "", "TI", "admin", "ativo", agora()),
    )


def registrar_evento(
    conn: sqlite3.Connection,
    *,
    tipo: str,
    id_unidade: str | None = None,
    id_atendimento: str | None = None,
    status_anterior: str | None = None,
    status_novo: str | None = None,
    usuario: str = "",
    motivo: str = "",
    observacao: str = "",
    devolvido_por: str = "",
    recebido_por: str = "",
) -> None:
    conn.execute(
        """INSERT INTO eventos
           (id_unidade, id_atendimento, tipo, status_anterior, status_novo,
            usuario, data_evento, motivo, observacao, devolvido_por, recebido_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (id_unidade, id_atendimento, tipo, status_anterior, status_novo,
         usuario, agora(), motivo, observacao, devolvido_por or None, recebido_por or None),
    )
