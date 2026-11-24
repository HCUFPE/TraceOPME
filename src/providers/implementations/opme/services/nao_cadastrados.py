"""v17 (out/2026) — material usado na sala que não foi cadastrado pelo almoxarifado.

É a exceção das exceções. A sala registra o uso direto no prontuário do paciente,
com os dados da etiqueta (lote e validade são o que garante o recall) e a
confirmação de que a etiqueta foi colada no prontuário físico.
O almoxarifado regulariza depois (AGHU, código de barras, NF, tipo de entrada) e
a farmácia dá ciência, como num uso sem dispensação. Cada caso entra no indicador.
"""

from __future__ import annotations

from .. import db
from ..domain import UTILIZADO
from ..utils import data_iso, decimal, gerar_id, inteiro, normalizar_codigo, texto
from . import alertas, atendimentos, materiais, usos_sem_dispensacao, usuarios

MOTIVOS = ("Urgência / emergência", "Material trazido pelo fornecedor na hora",
           "Material emprestado de outro serviço", "Outro")


SEM_IDENTIFICACAO = "MATERIAL NÃO IDENTIFICADO (ver etiqueta)"
TAMANHO_MAX_FOTO = 4 * 1024 * 1024


def _ler_foto(valor) -> tuple[bytes | None, str]:
    """nov/2026: foto opcional da etiqueta, enviada pela tela como data URL (JPEG/PNG)."""
    import base64
    bruto = texto(valor)
    if not bruto:
        return None, ""
    cabecalho, _, corpo = bruto.partition(",")
    if not cabecalho.startswith("data:image/") or ";base64" not in cabecalho or not corpo:
        return None, "A foto da etiqueta não veio em um formato de imagem válido. Tire a foto de novo."
    try:
        dados = base64.b64decode(corpo, validate=True)
    except Exception:
        return None, "Não consegui ler a foto da etiqueta. Tire a foto de novo."
    if len(dados) > TAMANHO_MAX_FOTO:
        return None, "A foto da etiqueta ficou grande demais. Tire a foto de novo."
    if not (dados[:3] == b"\xff\xd8\xff" or dados[:8] == b"\x89PNG\r\n\x1a\n"):
        return None, "A foto da etiqueta precisa ser JPEG ou PNG."
    return dados, ""


def pasta_fotos():
    from ..config import DATA_DIR
    pasta = DATA_DIR / "fotos_etiquetas"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _salvar_foto(dados: bytes) -> str:
    extensao = "png" if dados[:4] == b"\x89PNG" else "jpg"
    nome = f"{gerar_id('FOTO')}.{extensao}"
    (pasta_fotos() / nome).write_bytes(dados)
    return nome


def caminho_foto(nome: str):
    """Caminho seguro da foto (só o nome gerado pelo sistema, sem pastas)."""
    import re
    if not re.fullmatch(r"FOTO-[A-Za-z0-9]+\.(jpg|png)", texto(nome)):
        return None
    caminho = pasta_fotos() / nome
    return caminho if caminho.is_file() else None


def buscar_material(termo: str, limite: int = 25) -> list[dict]:
    """nov/2026: pesquisa pelo nome (ou código AGHU) para preencher a descrição,
    o fornecedor e a marca — na sala só falta digitar lote e validade.
    Procura no que já passou pelo estoque (traz fornecedor e marca) e no catálogo."""
    palavras = [p for p in texto(termo).upper().replace(",", " ").split() if p]
    if not palavras or len(" ".join(palavras)) < 3:
        return []
    cond = " AND ".join("(UPPER(COALESCE(NULLIF(descritivo_hospital,''), xProd) || ' ' || COALESCE(xProd,'')) LIKE ? "
                        "OR codigo_aghu LIKE ?)" for _ in palavras)
    params = tuple(x for p in palavras for x in (f"%{p}%", f"{p}%"))
    est = db.consultar(
        f"""SELECT COALESCE(NULLIF(descritivo_hospital,''), xProd) AS descricao, xProd, codigo_aghu, fornecedor,
                   marca_fabricante, MAX(criado_em) AS recente
            FROM unidades WHERE {cond}
            GROUP BY UPPER(COALESCE(NULLIF(descritivo_hospital,''), xProd)), codigo_aghu, UPPER(fornecedor)
            ORDER BY recente DESC LIMIT {int(limite)}""", params)
    saida, vistos = [], set()
    for r in est:
        chave = (texto(r["codigo_aghu"]), texto(r["descricao"]).upper(), texto(r["fornecedor"]).upper())
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append({"descricao": texto(r["descricao"]), "codigo_aghu": texto(r["codigo_aghu"]),
                      "fornecedor": texto(r["fornecedor"]), "marca_fabricante": texto(r["marca_fabricante"]),
                      "origem": "estoque"})
    cond_c = " AND ".join("(UPPER(descritivo_hospital) LIKE ? OR codigo_aghu LIKE ?)" for _ in palavras)
    ja = {s["codigo_aghu"] for s in saida if s["codigo_aghu"]}
    for r in db.consultar(f"SELECT codigo_aghu, descritivo_hospital FROM materiais_mestre WHERE {cond_c} "
                          f"ORDER BY descritivo_hospital LIMIT {int(limite)}", params):
        if texto(r["codigo_aghu"]) in ja:
            continue
        saida.append({"descricao": texto(r["descritivo_hospital"]), "codigo_aghu": texto(r["codigo_aghu"]),
                      "fornecedor": "", "marca_fabricante": "", "origem": "catálogo"})
    return saida[:limite]


def registrar(id_atendimento: str, dados: dict, usuario: dict) -> tuple[bool, str]:
    at = atendimentos.buscar(id_atendimento)
    if not at:
        return False, "Atendimento não encontrado."
    if at["status"] != "aberto":
        return False, ("Este atendimento está encerrado. Peça à supervisão para reabrir e registre "
                       "o material não cadastrado em seguida.")
    # nov/2026: na sala só lote e validade são obrigatórios; o material escolhido na
    # pesquisa é opcional — sem ele, o almoxarifado identifica pela etiqueta/foto.
    dados = dict(dados)
    dados["xProd"] = texto(dados.get("xProd")) or SEM_IDENTIFICACAO
    dados["fornecedor"] = texto(dados.get("fornecedor")) or "NÃO INFORMADO"
    obrig = {"nLote": "lote", "dVal": "validade", "motivo": "motivo"}
    faltando = [r for c, r in obrig.items() if not texto(dados.get(c))]
    if faltando:
        return False, "Preencha: " + ", ".join(faltando) + "."
    motivo = texto(dados.get("motivo"))
    if motivo not in MOTIVOS:
        return False, "Escolha o motivo."
    if motivo == "Outro" and len(texto(dados.get("detalhe"))) < 5:
        return False, "Descreva o motivo em “Detalhe”."
    validade = data_iso(dados.get("dVal"))
    if not validade:
        return False, "Validade inválida. Use DD/MM/AAAA."
    quantidade = inteiro(dados.get("quantidade"), 1)
    if quantidade < 1 or quantidade > 20:
        return False, "A quantidade precisa ser de 1 a 20."
    foto_bytes, erro_foto = _ler_foto(dados.get("foto_etiqueta"))
    if erro_foto:
        return False, erro_foto
    if not dados.get("etiqueta_no_prontuario") and not foto_bytes:
        return False, ("Confirme que a etiqueta do material foi colada no formulário de rastreabilidade "
                       "(ou tire a foto da etiqueta).")
    # nov/2026: não exige mais a senha da supervisão; fica registrado quem lançou.
    sup = {"username": usuario["username"], "nome": usuario.get("nome") or usuario["username"]}

    aghu = texto(dados.get("codigo_aghu"))
    descritivo = materiais.descritivo_hospital(aghu) if aghu else ""
    agora = db.agora()
    foto = _salvar_foto(foto_bytes) if foto_bytes else None
    ids = []
    with db.transacao() as conn:
        for _ in range(quantidade):
            id_unidade = gerar_id("U")
            ids.append(id_unidade)
            conn.execute(
                """INSERT INTO unidades
                   (id_unidade, codigo_barras, codigo_aghu, xProd, marca_fabricante, fornecedor,
                    nLote, numero_serie, dVal, vUnCom, origem, tipo_entrada, status, id_atendimento,
                    descritivo_hospital, criado_em, criado_por, atualizado_em, atualizado_por)
                   VALUES (?,?,?,?,?,?,?,?,?,0,'nao_cadastrado','consignado',?,?,?,?,?,?,?)""",
                (id_unidade, normalizar_codigo(dados.get("codigo_barras")), aghu,
                 texto(dados.get("xProd")), texto(dados.get("marca_fabricante")),
                 texto(dados.get("fornecedor")), texto(dados.get("nLote")),
                 texto(dados.get("numero_serie")), validade, UTILIZADO, id_atendimento,
                 descritivo, agora, usuario["username"], agora, usuario["username"]))
            obs = (f"MATERIAL NÃO CADASTRADO — registrado na sala por {usuario.get('nome') or usuario['username']}, "
                   f"sem autorização da supervisão; "
                   + ("etiqueta colada no formulário de rastreabilidade" if dados.get("etiqueta_no_prontuario") else "")
                   + (" e " if dados.get("etiqueta_no_prontuario") and foto else "")
                   + ("foto da etiqueta anexada" if foto else "")
                   + ". Aguardando regularização "
                   f"do almoxarifado.")
            db.registrar_evento(conn, tipo="uso_nao_cadastrado", id_unidade=id_unidade,
                                id_atendimento=id_atendimento, status_novo=UTILIZADO,
                                usuario=usuario["username"], motivo=motivo,
                                observacao=obs + (f" Detalhe: {texto(dados.get('detalhe'))}" if texto(dados.get("detalhe")) else ""))
            # Também é um uso: entra no prontuário, no consumo e nos indicadores de uso.
            db.registrar_evento(conn, tipo="registrar_uso", id_unidade=id_unidade,
                                id_atendimento=id_atendimento, status_novo=UTILIZADO,
                                usuario=usuario["username"], observacao="Material não cadastrado (exceção).")
            conn.execute(
                """INSERT INTO nao_cadastrados (id_unidade, id_atendimento, registrado_em, registrado_por,
                       autorizado_por, motivo, detalhe, etiqueta_no_prontuario, foto)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (id_unidade, id_atendimento, agora, usuario["username"], sup["username"], motivo,
                 texto(dados.get("detalhe")), 1 if dados.get("etiqueta_no_prontuario") else 0, foto))
            # Não passou pela farmácia: ela precisa dar ciência.
            usos_sem_dispensacao.registrar(conn, id_unidade=id_unidade, id_atendimento=id_atendimento,
                                           usuario=usuario["username"])
    alertas.criar(
        modulo_destino="almoxarifado",
        titulo="Material NÃO cadastrado usado na sala — regularizar",
        mensagem=(f"Prontuário {at['prontuario']}, sala {at['sala']}: {quantidade}× {texto(dados.get('xProd'))} "
                  f"(lote {texto(dados.get('nLote'))}, val. {texto(dados.get('dVal'))}, {texto(dados.get('fornecedor'))}). "
                  f"Motivo: {motivo}. Registrado por {sup['nome']}. Complete o cadastro (AGHU, NF, tipo de entrada)."),
        usuario=usuario["username"], id_atendimento=id_atendimento, ids_unidade=ids,
        link="/almoxarifado/nao-cadastrados")
    return True, (f"{quantidade} unidade(s) de material não cadastrado registrada(s) no prontuário "
                  f"{at['prontuario']}. O almoxarifado foi avisado para "
                  "regularizar e a farmácia dará ciência.")


def listar(situacao: str = "") -> list[dict]:
    filtro = "WHERE n.situacao = ?" if situacao else ""
    return db.consultar(
        f"""SELECT n.*, u.xProd, u.codigo_aghu, u.codigo_barras, u.fornecedor, u.marca_fabricante,
                   u.nLote, u.dVal, u.numero_nf, u.tipo_entrada, u.vUnCom,
                   a.prontuario, a.paciente, a.unidade, a.sala, a.data_procedimento
            FROM nao_cadastrados n
            LEFT JOIN unidades u ON u.id_unidade = n.id_unidade
            LEFT JOIN atendimentos a ON a.id_atendimento = n.id_atendimento
            {filtro} ORDER BY n.registrado_em DESC LIMIT 300""", ((situacao,) if situacao else ()))


def contar_pendentes() -> int:
    return db.escalar("SELECT COUNT(*) FROM nao_cadastrados WHERE situacao = 'pendente'") or 0


def regularizar(id_registro: int, dados: dict, usuario: str) -> tuple[bool, str]:
    from .estoque import normalizar_tipo_entrada
    reg = db.consultar_um("SELECT * FROM nao_cadastrados WHERE id = ?", (inteiro(id_registro, 0),))
    if not reg:
        return False, "Registro não encontrado."
    if reg["situacao"] != "pendente":
        return False, "Este material já foi regularizado."
    aghu = texto(dados.get("codigo_aghu"))
    if not aghu:
        return False, "Informe o código AGHU para regularizar."
    tipo = normalizar_tipo_entrada(dados.get("tipo_entrada"))
    agora = db.agora()
    # nov/2026: a sala pode registrar só lote e validade; o almoxarifado completa
    # descrição, fornecedor e marca pela etiqueta (ou pela foto).
    descricao = texto(dados.get("xProd")) or (materiais.descritivo_hospital(aghu) or "")
    if not descricao or descricao == SEM_IDENTIFICACAO:
        atual = db.escalar("SELECT xProd FROM unidades WHERE id_unidade = ?", (reg["id_unidade"],))
        if texto(atual) == SEM_IDENTIFICACAO and not descricao:
            return False, "Informe a descrição do material (está na etiqueta ou na foto)."
    with db.transacao() as conn:
        conn.execute(
            """UPDATE unidades SET xProd = CASE WHEN ? <> '' AND ? <> ? THEN ? ELSE xProd END,
                   fornecedor = COALESCE(NULLIF(?, ''), fornecedor),
                   marca_fabricante = COALESCE(NULLIF(?, ''), marca_fabricante) WHERE id_unidade = ?""",
            (descricao, descricao, SEM_IDENTIFICACAO, descricao, texto(dados.get("fornecedor")),
             texto(dados.get("marca_fabricante")), reg["id_unidade"]))
        conn.execute(
            """UPDATE unidades SET codigo_aghu = ?, codigo_barras = COALESCE(NULLIF(?, ''), codigo_barras),
                   numero_nf = ?, tipo_entrada = ?, vUnCom = ?, descritivo_hospital = COALESCE(NULLIF(?, ''), descritivo_hospital),
                   atualizado_em = ?, atualizado_por = ? WHERE id_unidade = ?""",
            (aghu, normalizar_codigo(dados.get("codigo_barras")), texto(dados.get("numero_nf")), tipo,
             decimal(dados.get("vUnCom")), materiais.descritivo_hospital(aghu) or "", agora, usuario,
             reg["id_unidade"]))
        conn.execute("""UPDATE nao_cadastrados SET situacao = 'regularizado', regularizado_em = ?,
                        regularizado_por = ?, observacao = ? WHERE id = ?""",
                     (agora, usuario, texto(dados.get("observacao")), reg["id"]))
        db.registrar_evento(conn, tipo="regularizar_nao_cadastrado", id_unidade=reg["id_unidade"],
                            id_atendimento=reg["id_atendimento"], usuario=usuario,
                            observacao=(f"Cadastro regularizado: AGHU {aghu}, NF {texto(dados.get('numero_nf')) or '—'}, "
                                        f"{tipo}. {texto(dados.get('observacao'))}").strip())
    if tipo == "consignado":
        try:
            from . import empenhos
            empenhos.vincular_automatico(reg["id_unidade"], usuario)
        except Exception:
            pass
    return True, "Material regularizado."
