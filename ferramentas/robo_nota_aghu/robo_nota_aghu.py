"""Robô — Nota de Recebimento sem AF no AGHU, a partir da planilha do TraceOPME.

v18.7: o mesmo robô também lança a NOTA DE CONSUMO do paciente (tela Materiais
Consumidos Cirurgia), quando aberto pelo botão "Lançar no AGHU" da Farmácia →
Nota de consumo (passos em passos_consumo.py).

Como funciona (resumo):
  1. Lê a planilha "NF_xxx_entrada_AGHU.xlsx" que o TraceOPME gera depois da
     entrada pela nota fiscal e agrupa por material + marca.
  2. Abre o navegador no AGHU. VOCÊ faz o login, abre
     Estoque → Gerar Nota de Recebimento sem AF e escolhe a nota fiscal
     (o cadastro da NF continua manual). Depois aperta ENTER aqui.
  3. O robô inclui cada material (material, marca, quantidade,
     unidade UN, valor total) e os lotes/validades de cada um.
  4. Ele NÃO grava a nota: no fim mostra o resumo e você confere e clica em
     "Gravar" no AGHU.

O robô não guarda nem digita senha. Se algo sair do esperado (marca não
encontrada, mensagem de erro do AGHU, nota diferente da planilha), ele para e
pergunta o que fazer.
"""

from __future__ import annotations

import configparser
import datetime as dt
import re
import sys
import unicodedata
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PASTA = Path(__file__).resolve().parent
LOG: list[str] = []
ARGS = None          # argumentos quando o robô é aberto pelo TraceOPME
RETORNO_FEITO = False

COLUNAS_OBRIGATORIAS = ["Código AGHU", "Lote", "Validade", "Marca", "Quantidade", "Nº NF", "Valor total"]
TEMPO_AJAX = 30_000  # ms


# ---------------------------------------------------------------- utilitários

def falar(msg: str = "") -> None:
    print(msg, flush=True)
    LOG.append(f"{dt.datetime.now():%H:%M:%S} {msg}")


def perguntar(msg: str) -> str:
    LOG.append(f"{dt.datetime.now():%H:%M:%S} ? {msg}")
    resp = input(msg)
    LOG.append(f"{dt.datetime.now():%H:%M:%S}   resposta: {resp}")
    return resp.strip()


def sim(msg: str) -> bool:
    return perguntar(f"{msg} (S/N): ").upper().startswith("S")


def norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def dinheiro(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s or "0").quantize(Decimal("0.01"), ROUND_HALF_UP)


def br(v: Decimal) -> str:
    """1234.5 → '1234,50' (sem separador de milhar, para digitar no campo)."""
    return f"{v:.2f}".replace(".", ",")


def br_mostrar(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(v) -> str:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.strftime("%d/%m/%Y")
    s = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return s


def ler_argumentos():
    """Aberto pelo TraceOPME: planilha + --chave/--token/--retorno (para avisar no fim)."""
    import argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("planilha", nargs="?")
    p.add_argument("--chave", default="")
    p.add_argument("--token", default="")
    p.add_argument("--retorno", default="")
    p.add_argument("--aghu-url", default="")
    p.add_argument("--navegador", default="")
    p.add_argument("--link", default="")
    args, _ = p.parse_known_args()
    args.tipo, args.consumo = "nf", None
    # nov/2026: aberto pelo botão "Lançar no AGHU" do TraceOPME (link traceopme-aghu://lancar/<bloco>).
    link = args.link or (args.planilha if (args.planilha or "").lower().startswith("traceopme-aghu:") else "")
    if link:
        import base64
        import json
        bloco = link.strip().strip('"').split("lancar/", 1)[-1].strip("/")
        bloco += "=" * (-len(bloco) % 4)
        dados = json.loads(base64.urlsafe_b64decode(bloco.encode()).decode())
        servidor = dados["s"].rstrip("/")
        args.chave, args.token = dados["c"], dados["t"]
        args.retorno = f"{servidor}/api/robo-aghu/retorno"
        args.aghu_url = args.aghu_url or dados.get("a", "")
        args.navegador = args.navegador or dados.get("b", "")
        if dados.get("k") in ("consumo", "rm"):     # v18.7: nota de consumo · v18.8: requisição de material
            args.tipo = dados["k"]
            args.consumo = baixar_consumo(servidor, args.chave, args.token, args.tipo)
        else:
            args.planilha = str(baixar_planilha(servidor, args.chave, args.token, dados.get("n", "")))
    return args


def _abrir_url(req, timeout=30):
    """Fala direto com o servidor da rede interna (sem passar pelo proxy de internet)."""
    import urllib.request
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)


def _motivo_http(e) -> str:
    """v18.7.2: o motivo que o TraceOPME mandou junto com a recusa (403/400)."""
    try:
        import json
        corpo = e.read().decode("utf-8", "ignore")
        return json.loads(corpo).get("mensagem") or corpo[:200]
    except Exception:
        return ""


def baixar_planilha(servidor: str, chave: str, token: str, numero: str) -> Path:
    import urllib.parse
    url = f"{servidor}/api/robo-aghu/planilha?" + urllib.parse.urlencode({"chave": chave, "token": token})
    import urllib.error
    try:
        with _abrir_url(url) as r:
            conteudo = r.read()
    except urllib.error.HTTPError as e:
        motivo = _motivo_http(e) or str(e)
        raise SystemExit(f"O TraceOPME recusou o pedido do robô: {motivo}\n"
                         "Feche esta janela e clique UMA vez em “Lançar no AGHU agora” na tela da NF.")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Não consegui baixar a planilha da NF do TraceOPME ({servidor}): {e}\n"
                         "Confira se o TraceOPME está no ar e clique de novo em “Lançar no AGHU”.")
    # v18.7.1: se a planilha anterior estiver aberta no Excel (o Windows trava o arquivo) ou a
    # pasta não deixar gravar, salva com outro nome / na pasta temporária em vez de parar.
    import tempfile
    nome = f"NF_{re.sub(r'[^0-9A-Za-z]', '', numero) or 'nf'}_entrada_AGHU"
    carimbo = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta = PASTA / "planilhas"
    tentativas = [pasta / f"{nome}.xlsx", pasta / f"{nome}_{carimbo}.xlsx",
                  Path(tempfile.gettempdir()) / f"{nome}_{carimbo}.xlsx"]
    for destino in tentativas:
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
            if destino != tentativas[0]:
                falar(f"(A planilha anterior estava aberta ou travada; usei {destino.name}.)")
            return destino
        except OSError:
            continue
    raise SystemExit("Não consegui salvar a planilha da NF neste computador. Feche o Excel e clique de novo "
                     "em “Lançar no AGHU”.")


def baixar_consumo(servidor: str, chave: str, token: str, tipo: str = "consumo") -> dict:
    """v18.7: materiais usados no paciente (JSON) para a nota de consumo.
    v18.8: tipo "rm" — requisição de material, com os lotes de cada material."""
    import json
    import urllib.parse
    url = f"{servidor}/api/robo-aghu/consumo?" + urllib.parse.urlencode({"chave": chave, "token": token, "tipo": tipo})
    import urllib.error
    try:
        with _abrir_url(url) as r:
            dados = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"O TraceOPME recusou o pedido do robô: {_motivo_http(e) or e}\n"
                         "Feche esta janela e clique UMA vez no botão do AGHU na Farmácia → Nota de consumo e RM.")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Não consegui baixar os materiais do paciente no TraceOPME ({servidor}): {e}\n"
                         "Confira se o TraceOPME está no ar e clique de novo em “Lançar no AGHU”.")
    if not dados.get("ok"):
        raise SystemExit(dados.get("mensagem") or "O TraceOPME não liberou este lançamento.")
    return dados


def avisar_traceopme(gravou: bool, numero_nr: str = "") -> None:
    """nov/2026: conta ao TraceOPME se a nota foi gravada no AGHU (só quando aberto por ele)."""
    global RETORNO_FEITO
    if RETORNO_FEITO or not ARGS or not ARGS.retorno or not ARGS.token:
        return
    RETORNO_FEITO = True
    import json
    import urllib.request
    corpo = json.dumps({"chave": ARGS.chave, "token": ARGS.token, "gravou": bool(gravou),
                        "numero_nr": numero_nr, "tipo": getattr(ARGS, "tipo", "nf")}).encode()
    try:
        req = urllib.request.Request(ARGS.retorno, data=corpo, headers={"Content-Type": "application/json"})
        with _abrir_url(req, timeout=15) as r:
            resposta = json.loads(r.read().decode() or "{}")
        falar(f"TraceOPME: {resposta.get('mensagem', 'avisado')}")
    except Exception as e:  # noqa: BLE001
        onde = "na Farmácia → Nota de consumo e RM" if getattr(ARGS, "tipo", "nf") in ("consumo", "rm") else "na tela da NF"
        falar(f"Não consegui avisar o TraceOPME ({e}). Marque à mão {onde}: “Já lancei no AGHU”.")


def config() -> configparser.SectionProxy:
    c = configparser.ConfigParser()
    c.read(PASTA / "config.ini", encoding="utf-8")
    if "aghu" not in c:
        c["aghu"] = {}
    s = c["aghu"]
    s.setdefault("url", "http://10.34.0.64:8080/aghu/")
    s.setdefault("navegador", "msedge")
    s.setdefault("unidade", "UN")
    if ARGS and ARGS.aghu_url:
        s["url"] = ARGS.aghu_url
    if ARGS and ARGS.navegador:
        s["navegador"] = ARGS.navegador
    return s


# ---------------------------------------------------------------- planilha

def ler_planilha(caminho: Path) -> tuple[str, str, list[dict]]:
    """Devolve (nº NF, série, itens). Cada item = UM material (código AGHU), com todos os seus lotes.

    nov/2026: o mesmo material com vários lotes entra UMA vez no AGHU, com os lotes
    embaixo dele (antes a chave era material + marca)."""
    from openpyxl import load_workbook

    ws = load_workbook(caminho, data_only=True).active
    cab = [str(c.value or "").strip() for c in ws[1]]
    falta = [c for c in COLUNAS_OBRIGATORIAS if c not in cab]
    if falta:
        raise SystemExit(f"A planilha não tem as colunas: {', '.join(falta)}.\n"
                         "Baixe de novo no TraceOPME (versão 17.3.21 ou mais nova).")
    idx = {c: cab.index(c) for c in cab}
    itens: "OrderedDict[tuple, dict]" = OrderedDict()
    nfs, series = set(), set()
    for n, linha in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(linha):
            continue
        val = lambda col: linha[idx[col]] if col in idx else None  # noqa: E731
        aghu = str(val("Código AGHU") or "").strip()
        if aghu.endswith(".0"):
            aghu = aghu[:-2]
        # v18.8.1: na Nota de Recebimento o material é procurado pelo CÓDIGO AGHU (a
        # coluna "Código master" da planilha fica só para consulta).
        master = str(val("Código master") or "").strip()
        if master.endswith(".0"):
            master = master[:-2]
        codigo = aghu
        qtd = int(Decimal(str(val("Quantidade") or 0)))
        if not codigo or qtd <= 0:
            raise SystemExit(f"Linha {n} da planilha sem código AGHU ou quantidade.")
        nfs.add(str(val("Nº NF") or "").strip())
        series.add(str(val("Série") or "").strip())
        marca = str(val("Marca") or "").strip()
        chave = codigo.lstrip("0") or codigo
        it = itens.setdefault(chave, {"codigo": codigo, "aghu": aghu, "master": master, "marca": marca, "quantidade": 0,
                                      "valor": Decimal("0"), "lotes": [], "marcas": set()})
        if marca:
            it["marcas"].add(norm(marca))
            if not it["marca"]:
                it["marca"] = marca
        it["quantidade"] += qtd
        it["valor"] += dinheiro(val("Valor total"))
        it["lotes"].append({"lote": str(val("Lote") or "").strip(), "validade": data_br(val("Validade")),
                            "quantidade": qtd})
    if not itens:
        raise SystemExit("A planilha está vazia.")
    for it in itens.values():
        if len(it["marcas"]) > 1:
            falar(f"ATENÇÃO: o material {it['codigo']} aparece com marcas diferentes na planilha "
                  f"({', '.join(sorted(it['marcas']))}). Vou usar “{it['marca']}” — confira no AGHU.")
    if len(nfs) > 1:
        raise SystemExit(f"A planilha tem mais de uma NF ({', '.join(sorted(nfs))}). Use uma planilha por nota.")
    return nfs.pop(), (series.pop() if len(series) == 1 else ""), list(itens.values())


def mostrar_resumo(nf: str, serie: str, itens: list[dict]) -> Decimal:
    total = sum((i["valor"] for i in itens), Decimal("0"))
    falar(f"\nNF {nf}{' série ' + serie if serie else ''} — {len(itens)} material(is), total R$ {br_mostrar(total)}")
    falar("-" * 78)
    for n, i in enumerate(itens, 1):
        rot = f"AGHU {i['codigo']}"
        falar(f"{n:>2}. {rot:<15} marca {i['marca'][:22]:<22} qtd {i['quantidade']:>4}  "
              f"R$ {br_mostrar(i['valor']):>12}")
        for l in i["lotes"]:
            falar(f"      lote {l['lote']:<20} validade {l['validade']:<10} qtd {l['quantidade']}")
    falar("-" * 78)
    return total


# ---------------------------------------------------------------- AGHU (tela)

def sel(id_: str) -> str:
    """Seletor por id (os ids do AGHU têm ':' e não funcionam com '#')."""
    return f'[id="{id_}"]'


def esperar_ajax(frame) -> None:
    try:
        frame.wait_for_function(
            "() => !window.PrimeFaces || !PrimeFaces.ajax || !PrimeFaces.ajax.Queue || PrimeFaces.ajax.Queue.isEmpty()",
            timeout=TEMPO_AJAX)
    except Exception:
        pass
    frame.page.wait_for_timeout(250)


def achar_frame(page):
    for f in page.frames:
        try:
            if f.query_selector(sel("formGerarNotaRecebimento")):
                return f
        except Exception:
            continue
    return None


def mensagens(frame) -> tuple[list[str], list[str]]:
    """(erros, outras) visíveis na tela agora."""
    erros, outras = [], []
    for css, lista in ((".ui-messages-error-summary, .ui-messages-error-detail, .ui-growl-message-error, "
                        ".ui-message-error-detail", erros),
                       (".ui-messages-info-summary, .ui-messages-warn-summary, .ui-growl-message-info, "
                        ".ui-growl-message-warn", outras)):
        for el in frame.query_selector_all(css):
            try:
                if el.is_visible():
                    t = re.sub(r"\s+", " ", el.inner_text()).strip()
                    if t and t not in lista:
                        lista.append(t)
            except Exception:
                pass
    return erros, outras


def limpar_mensagens(frame) -> None:
    """Some com as mensagens antigas da tela, para não confundir com as da próxima ação."""
    try:
        frame.evaluate("""() => document.querySelectorAll(
            '.ui-messages-error-summary,.ui-messages-error-detail,.ui-growl-message-error,.ui-message-error-detail,'
            + '.ui-messages-info-summary,.ui-messages-warn-summary,.ui-growl-message-info,.ui-growl-message-warn'
          ).forEach(e => e.remove())""")
    except Exception:
        pass


def valor_campo(frame, id_: str) -> str:
    el = frame.query_selector(sel(id_))
    return (el.input_value() if el else "").strip()


def digitar(frame, id_: str, texto: str, tab: bool = True) -> None:
    campo = frame.locator(sel(id_))
    campo.click()
    campo.press("Control+A")
    campo.press("Delete")
    campo.type(texto, delay=40)
    if tab:
        campo.press("Tab")
    esperar_ajax(frame)


def escolher_sugestao(frame, base: str, texto: str, escolher) -> tuple[bool, list[tuple[str, str]]]:
    """Digita no campo de busca do AGHU e clica na opção que `escolher` aprovar.

    `escolher(rotulo, descricao, opcoes)` devolve o índice da opção ou None.
    Devolve (escolheu?, opções vistas)."""
    campo_id = f"{base}:{base}:suggestion_input"
    painel = sel(f"{base}:{base}:suggestion_panel")
    campo = frame.locator(sel(campo_id))
    campo.click()
    campo.press("Control+A")
    campo.press("Delete")
    campo.type(texto, delay=60)
    linhas = frame.locator(f"{painel} tr.ui-autocomplete-item")
    try:
        linhas.first.wait_for(state="visible", timeout=15_000)
    except Exception:
        return False, []
    esperar_ajax(frame)
    opcoes = []
    for i in range(linhas.count()):
        lin = linhas.nth(i)
        rotulo = (lin.get_attribute("data-item-label") or "").strip()
        celulas = [re.sub(r"\s+", " ", c).strip() for c in lin.locator("td").all_inner_texts()]
        descricao = celulas[1] if len(celulas) > 1 else ""
        opcoes.append((rotulo, descricao))
    i = escolher(opcoes)
    if i is None:
        return False, opcoes
    linhas.nth(i).click()
    esperar_ajax(frame)
    return True, opcoes


def abrir_aghu(pagina, url: str) -> None:
    """Abre o AGHU; se a rede oscilar (ERR_NETWORK_CHANGED etc.), tenta de novo."""
    for tentativa in range(4):
        try:
            pagina.goto(url)
            return
        except Exception as e:  # noqa: BLE001
            if "net::" not in str(e) or tentativa == 3:
                raise
            falar("   A rede oscilou ao abrir o AGHU. Tentando de novo…")
            pagina.wait_for_timeout(3000)


def esperar_voce(msg: str) -> None:
    perguntar(f"\n>>> {msg}\n    Quando terminar, aperte ENTER aqui... ")


def checar_erros(frame, etapa: str) -> bool:
    """True se pode seguir. Mostra mensagens do AGHU e, em caso de erro, pergunta."""
    erros, outras = mensagens(frame)
    for m in outras:
        falar(f"   AGHU: {m}")
    if not erros:
        return True
    for m in erros:
        falar(f"   ERRO DO AGHU ({etapa}): {m}")
    resp = perguntar("   Corrija na tela se precisar. [C]ontinuar, [P]ular este material ou [S]air? ").upper()
    if resp.startswith("S"):
        raise KeyboardInterrupt
    return not resp.startswith("P")


def linha_do_material(frame, codigo: str) -> int | None:
    for el in frame.query_selector_all('[id^="tabelaDocumentosFiscaisEntrada:resultList:"][id$=":materialCodigoNome"]'):
        texto = (el.inner_text() or "").strip()
        if re.match(rf"^0*{re.escape(codigo.lstrip('0'))}\s*-", texto):
            m = re.search(r"resultList:(\d+):materialCodigoNome", el.get_attribute("id") or "")
            if m:
                return int(m.group(1))
    return None


def incluir_material(frame, item: dict, cfg) -> bool:
    codigo, marca = item["codigo"], item["marca"]
    falar(f"\n== Material {codigo} — marca {marca} — qtd {item['quantidade']} — R$ {br_mostrar(item['valor'])}")
    limpar_mensagens(frame)

    ok, opcoes = escolher_sugestao(
        frame, "sbMaterial", codigo,
        lambda ops: next((i for i, (r, _d) in enumerate(ops) if r.lstrip("0") == codigo.lstrip("0")), None))
    if not ok:
        falar(f"   Não achei o material {codigo} no AGHU." + (f" Opções: {opcoes[:5]}" if opcoes else ""))
        esperar_voce(f"Escolha o material {codigo} na tela (campo Material), ou deixe em branco para pular")
        if not valor_campo(frame, "sbMaterial:sbMaterial:suggestion_input"):
            return False
    if not checar_erros(frame, "material"):
        return False

    def marca_certa(ops):
        alvo = norm(marca)
        exatos = [i for i, (_r, d) in enumerate(ops) if norm(d) == alvo]
        if len(exatos) == 1:
            return exatos[0]
        if len(ops) == 1 and alvo and (alvo in norm(ops[0][1]) or norm(ops[0][1]) in alvo):
            return 0
        return None

    ok, opcoes = escolher_sugestao(frame, "sbMarcaComercial", marca[:30], marca_certa)
    if not ok:
        falar(f"   A marca “{marca}” não bateu com uma única marca do AGHU."
              + (f" Opções vistas: {', '.join(d for _r, d in opcoes[:8])}" if opcoes else " Nenhuma opção apareceu."))
        esperar_voce(f"Escolha a marca do material {codigo} na tela (campo Marca Comercial)")

    # nov/2026: o almoxarifado de entrada fica em branco (o AGHU decide).

    digitar(frame, "quantidadeReceber:quantidadeReceber:inputId_input", str(item["quantidade"]))

    unidade = cfg["unidade"]
    if valor_campo(frame, "sbUnidadeMedida:sbUnidadeMedida:suggestion_input").upper() != unidade.upper():
        ok, _ = escolher_sugestao(frame, "sbUnidadeMedida", unidade,
                                  lambda ops: next((i for i, (r, _d) in enumerate(ops) if r.upper() == unidade.upper()), None))
        if not ok:
            esperar_voce(f"Escolha a unidade {unidade} (UNIDADE) na tela")

    digitar(frame, "valorTotal:valorTotal:inputId_input", br(item["valor"]))

    limpar_mensagens(frame)
    frame.locator(sel("bt_adicionar:button")).click()
    esperar_ajax(frame)
    if not checar_erros(frame, "adicionar material"):
        return False
    if linha_do_material(frame, codigo) is None:
        falar("   Não vi o material na lista de itens depois de adicionar.")
        esperar_voce("Confira na tela se o material entrou na lista (se não, inclua à mão)")
    return True


def lotes_na_tela(frame) -> set[str]:
    """Lotes já incluídos no Controle de Validade do item marcado."""
    lotes = set()
    for linha in frame.query_selector_all('[id="tabelaControleValidade:resultList_data"] tr[data-ri]'):
        celulas = [re.sub(r"\s+", " ", c.inner_text()).strip() for c in linha.query_selector_all("td")]
        if len(celulas) > 1 and celulas[1]:
            lotes.add(norm(celulas[1]))
    return lotes


def incluir_lotes(frame, item: dict) -> None:
    codigo = item["codigo"]
    n = linha_do_material(frame, codigo)
    if n is None:
        esperar_voce(f"Não achei o material {codigo} na lista. Marque o item dele (bolinha à esquerda) na tela")
    else:
        frame.locator(f'[id="tabelaDocumentosFiscaisEntrada:resultList:{n}:idRadio"] .ui-radiobutton-box').click()
        esperar_ajax(frame)
    try:
        frame.locator(sel("lote:lote:inputId")).wait_for(state="visible", timeout=15_000)
    except Exception:
        esperar_voce("Não apareceu a área de Controle de Validade. Marque o item na lista")
    ja = lotes_na_tela(frame)
    for l in item["lotes"]:
        if norm(l["lote"]) in ja:
            falar(f"   lote {l['lote']} já está neste material — pulei")
            continue
        falar(f"   lote {l['lote']} · validade {l['validade']} · qtd {l['quantidade']}")
        digitar(frame, "lote:lote:inputId", l["lote"])
        digitar(frame, "data:data:inputId_input", l["validade"])
        digitar(frame, "tamanho:tamanho:inputId_input", str(l["quantidade"]))
        limpar_mensagens(frame)
        frame.locator(sel("bt_adicionar_controle_validade:button")).click()
        esperar_ajax(frame)
        checar_erros(frame, f"lote {l['lote']}")


# ---------------------------------------------------------------- principal

def escolher_planilha() -> Path:
    if ARGS and ARGS.planilha:
        return Path(ARGS.planilha)
    try:
        import tkinter as tk
        from tkinter import filedialog
        raiz = tk.Tk()
        raiz.withdraw()
        caminho = filedialog.askopenfilename(title="Planilha do TraceOPME (NF_..._entrada_AGHU.xlsx)",
                                             filetypes=[("Excel", "*.xlsx")])
        raiz.destroy()
        if caminho:
            return Path(caminho)
    except Exception:
        pass
    return Path(perguntar("Caminho da planilha .xlsx: ").strip('"'))


def abrir_navegador(pw, cfg):
    import os
    if os.environ.get("ROBO_TESTE"):  # só para o teste automático (tela simulada)
        return pw.chromium.launch(headless=True)
    try:
        return pw.chromium.launch(channel=cfg["navegador"], headless=False)
    except Exception:
        return pw.chromium.launch(channel="chrome", headless=False)


def main_consumo(cfg) -> None:
    """v18.7: nota de consumo do paciente (Materiais Consumidos Cirurgia).
    v18.8: também a requisição de material (RM), com lotes (passos_rm.py)."""
    sys.path.insert(0, str(PASTA))
    if ARGS.tipo == "rm":
        import passos_rm as pc
        pergunta = "Lançar estes materiais na requisição de material (RM) do AGHU?"
    else:
        import passos_consumo as pc
        pergunta = "Lançar estes materiais na nota de consumo do AGHU?"
    eu = sys.modules[__name__]
    at, itens = ARGS.consumo["atendimento"], ARGS.consumo["itens"]
    pc.mostrar_resumo(eu, at, itens)
    if not itens:
        raise SystemExit("Nenhum material com código AGHU para lançar neste paciente.")
    if not sim(pergunta):
        avisar_traceopme(False)
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        navegador = abrir_navegador(pw, cfg)
        contexto = navegador.new_context(viewport=None)
        pagina = contexto.new_page()
        abrir_aghu(pagina, cfg["url"])
        gravou = pc.lancar(eu, lambda: [p for p in contexto.pages if not p.is_closed()][-1], at, itens)
        avisar_traceopme(bool(gravou))
        perguntar("Aperte ENTER para fechar o navegador... ")
        navegador.close()


def main() -> None:
    global ARGS
    ARGS = ler_argumentos()
    cfg = config()
    if ARGS.tipo in ("consumo", "rm"):
        main_consumo(cfg)
        return
    planilha = escolher_planilha()
    if not planilha.is_file():
        raise SystemExit(f"Não achei a planilha: {planilha}")
    falar(f"Planilha: {planilha.name}")
    nf, serie, itens = ler_planilha(planilha)
    total = mostrar_resumo(nf, serie, itens)
    if not sim("Lançar estes itens no AGHU?"):
        avisar_traceopme(False)
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        import os
        navegador = abrir_navegador(pw, cfg)
        pagina = navegador.new_context(viewport=None).new_page()
        abrir_aghu(pagina, cfg["url"])
        esperar_voce(f"No navegador que abriu: faça o login, abra Estoque → Gerar Nota de Recebimento sem AF "
                     f"e escolha a NF {nf} (botão Nota Fiscal)")
        frame = achar_frame(pagina)
        while frame is None:
            esperar_voce("Não achei a tela Gerar Nota de Recebimento sem AF. Abra a tela e escolha a NF")
            frame = achar_frame(pagina)

        nf_tela = valor_campo(frame, "numero:numero:inputId_input")
        serie_tela = valor_campo(frame, "serie:serie:inputId")
        if not nf_tela:
            esperar_voce("A tela ainda não tem nota fiscal escolhida. Clique em Nota Fiscal e escolha a NF")
            nf_tela = valor_campo(frame, "numero:numero:inputId_input")
        falar(f"Nota na tela: {nf_tela} série {serie_tela or '—'} · valor da NF R$ "
              f"{valor_campo(frame, 'valorTotalNota:valorTotalNota:inputId_input') or '—'}")
        if re.sub(r"\D", "", nf_tela).lstrip("0") != re.sub(r"\D", "", nf).lstrip("0"):
            if not sim(f"ATENÇÃO: a nota da tela ({nf_tela}) é diferente da planilha ({nf}). Continuar assim mesmo?"):
                avisar_traceopme(False)
                return
        valor_nf = valor_campo(frame, "valorTotalNota:valorTotalNota:inputId_input")
        if valor_nf and dinheiro(valor_nf) != total:
            falar(f"ATENÇÃO: valor da NF no AGHU (R$ {valor_nf}) é diferente da soma da planilha "
                  f"(R$ {br_mostrar(total)}). O AGHU não vai deixar gravar se não bater.")
            if not sim("Continuar assim mesmo?"):
                avisar_traceopme(False)
                return

        feitos, pulados = [], []
        for item in itens:
            if linha_do_material(frame, item["codigo"]) is not None:
                # nov/2026: material já incluído → não inclui de novo; só completa os lotes dele.
                falar(f"\n== Material {item['codigo']} já está na lista da nota — não incluo de novo, "
                      "só confiro e adiciono os lotes que faltam.")
                incluir_lotes(frame, item)
                feitos.append(item["codigo"])
                continue
            if incluir_material(frame, item, cfg):
                incluir_lotes(frame, item)
                feitos.append(item["codigo"])
            else:
                pulados.append(item["codigo"])

        falar("\n" + "=" * 78)
        falar(f"Incluídos: {len(feitos)} material(is) {', '.join(feitos)}")
        if pulados:
            falar(f"Pulados / para conferir: {', '.join(pulados)}")
        falar(f"Soma dos itens na tela: R$ {valor_campo(frame, 'valorTotalItensField:valorTotalItens') or '—'} · "
              f"planilha R$ {br_mostrar(total)}")
        falar("CONFIRA a nota no AGHU (itens, lotes e validades) e clique em GRAVAR você mesma.")
        falar("O robô não grava a nota.")
        if os.environ.get("ROBO_TESTE"):
            print("MOCKLOG", frame.evaluate("JSON.stringify(window.LOG || [])"))
        esperar_voce("Confira e GRAVE a nota no AGHU")
        if ARGS and ARGS.retorno:
            if sim("A nota foi GRAVADA no AGHU?"):
                nr = perguntar("Número da nota de recebimento que o AGHU gerou (ENTER se não souber): ")
                avisar_traceopme(True, nr)
            else:
                avisar_traceopme(False)
        perguntar("Aperte ENTER para fechar o navegador... ")
        navegador.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        falar("\nParado por você. Nada foi gravado pelo robô — confira a tela do AGHU.")
        avisar_traceopme(False)
    except SystemExit as e:
        if e.code not in (None, 0):
            falar(f"\n{e.code}")
    except Exception as e:  # noqa: BLE001
        if "has been closed" in str(e) or e.__class__.__name__ == "TargetClosedError":
            falar("\nO navegador do robô foi fechado, então o robô parou. Nada foi gravado pelo robô.")
            falar("Para continuar, clique de novo no botão do TraceOPME.")
        else:
            falar(f"\nO robô parou por um erro inesperado: {e.__class__.__name__}: {e}")
            falar("Nada foi gravado pelo robô. Mande o arquivo de log para a Camila.")
        avisar_traceopme(False)
    finally:
        try:
            nome = PASTA / "logs" / f"robo_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
            nome.parent.mkdir(exist_ok=True)
            nome.write_text("\n".join(LOG), encoding="utf-8")
            print(f"\nLog salvo em {nome}")
        except Exception:
            pass
        try:
            input("\nAperte ENTER para fechar esta janela...")
        except Exception:
            pass
