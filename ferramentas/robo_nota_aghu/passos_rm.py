"""Passos do robô na REQUISIÇÃO DE MATERIAL (RM) do AGHU (v18.8).

Duas telas do AGHU:
  1. "Geração/Alteração de Requisição de Material" (geracaoRequisicaoMaterial.xhtml)
     A pessoa preenche o cabeçalho (CA, almoxarifado, grupo) e vincula o paciente.
     O robô inclui cada material com a quantidade (botão "Gravar" do item).
     A pessoa clica em "Confirmar" e depois em "Acessar Efetivação de RM".
  2. "Efetivar Requisição Material" (efetivarRequisicaoMaterial.xhtml)
     Para cada material, o robô seleciona o item, marca no "Controle de Validade" o
     LOTE usado no paciente (o que foi bipado no TraceOPME) e põe a quantidade atendida.
     A pessoa confere e clica em "Efetivar".

O robô não confirma nem efetiva: só preenche.
"""

from __future__ import annotations

import re


def _norm_lote(v) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(v or "").upper())


def _numero(v) -> float:
    try:
        return float(str(v).replace(".", "").replace(",", ".") or 0)
    except ValueError:
        return 0.0


def _achar(mod, pagina, form_id: str):
    for f in pagina.frames:
        try:
            if f.query_selector(mod.sel(form_id)):
                return f
        except Exception:
            continue
    return None


def _esperar_pagina(frame) -> None:
    """Os botões "Gravar" do AGHU recarregam a tela inteira (não é ajax)."""
    try:
        frame.page.wait_for_timeout(400)
        frame.wait_for_load_state("load", timeout=30_000)
    except Exception:
        pass


def _codigo_da_linha(texto_linha: str) -> str:
    m = re.search(r"(?:^|\|)\s*0*(\d+)\s*-\s", texto_linha)
    return m.group(1) if m else ""


def _linhas_itens_geracao(frame) -> list[str]:
    """Códigos já incluídos na RM (tabela de itens da tela de geração)."""
    cods = []
    for tr in frame.query_selector_all("#formRequisicaoMaterialItens tbody[id$='resultList_data'] > tr"):
        txt = " | ".join((td.inner_text() or "").strip() for td in tr.query_selector_all(":scope > td"))
        c = _codigo_da_linha(txt)
        if c:
            cods.append(c)
    return cods


def _saldo_do_lote(frame, ri_lote) -> float:
    lr = frame.query_selector(f"tbody[id$='tabelaControleValidade:resultList_data'] > tr[data-ri='{ri_lote}']")
    tds = lr.query_selector_all(":scope > td") if lr else []
    return _numero(tds[-1].inner_text()) if tds else 0.0


def _lote_da_linha(frame, ri_lote) -> str:
    lr = frame.query_selector(f"tbody[id$='tabelaControleValidade:resultList_data'] > tr[data-ri='{ri_lote}']")
    tds = lr.query_selector_all(":scope > td") if lr else []
    return (tds[1].inner_text() or "").strip() if len(tds) > 1 else "?"


def _quantidade_do_item(mod, frame, ri: str | int, quantidade: int) -> bool:
    """v18.12: Quantidade Entregue na linha do ITEM (sdTable…:resultList:{ri}:qtdeEntregue).

    É esse campo que o AGHU usa para preencher a Quantidade Atendida do lote.
    """
    campo = (frame.query_selector(f'[id$="sdTableItemRequisicaoMaterial:resultList:{ri}:qtdeEntregue"]')
             or frame.query_selector(f"tbody[id$='sdTableItemRequisicaoMaterial:resultList_data'] > "
                                     f"tr[data-ri='{ri}'] input[type=text]"))
    if campo is None or campo.is_disabled():
        return False
    campo.click(click_count=3)
    campo.fill(str(int(quantidade)))
    campo.press("Tab")
    mod.esperar_ajax(frame)
    return True


def mostrar_resumo(mod, at: dict, itens: list[dict]) -> None:
    mod.falar(f"Requisição de material (RM) · prontuário {at.get('prontuario')} · {at.get('paciente') or ''} · "
              f"{at.get('data_br') or ''}")
    mod.falar("-" * 78)
    for n, i in enumerate(itens, 1):
        lotes = ", ".join(f"{l['lote'] or 'sem lote'} val {l.get('validade') or '—'} ({l['quantidade']})" for l in i["lotes"])
        mod.falar(f"{n:>2}. AGHU {i['codigo']:<8} qtd {i['quantidade']:>3}  lotes: {lotes}")
        mod.falar(f"    {(i.get('descricao') or '')[:70]}")
    mod.falar("-" * 78)
    for d in at.get("sem_codigo") or []:
        mod.falar(f"ATENÇÃO: {d} está sem código AGHU no TraceOPME — lance à mão.")


def _conferir_paciente(mod, frame, at: dict, campo: str) -> bool:
    pront_tela = re.sub(r"\D", "", mod.valor_campo(frame, campo) or "")
    pront = re.sub(r"\D", "", str(at.get("prontuario") or ""))
    if pront_tela and pront and not (pront_tela == pront or pront_tela.startswith(pront) or pront.startswith(pront_tela)):
        return mod.sim(f"ATENÇÃO: o prontuário da tela ({pront_tela}) é diferente do TraceOPME ({pront}). "
                       "Continuar assim mesmo?")
    if not pront_tela:
        return mod.sim("A RM na tela ainda não tem paciente vinculado. Continuar assim mesmo?")
    return True


CABECALHO = (("sbCCReq", "CA Requisição"), ("sbCCAplicacao", "CA Aplicação"), ("sbAlmoxarifado", "Almoxarifado"))


def _faltando_cabecalho(mod, frame) -> list[str]:
    """Campos do cabeçalho que não foram ESCOLHIDOS na lista (só digitar não vale no AGHU)."""
    faltam = []
    for base, nome in CABECALHO:
        visivel = mod.valor_campo(frame, f"{base}:{base}:suggestion_input")
        escolhido = mod.valor_campo(frame, f"{base}:{base}:suggestion_hinput")
        if not visivel or not escolhido:
            faltam.append(nome)
    return faltam


def _material_liberado(mod, frame) -> bool:
    campo = frame.query_selector(mod.sel("sbMaterial:sbMaterial:suggestion_input"))
    return bool(campo) and not campo.is_disabled()


# Códigos do cabeçalho da RM por unidade (o que a farmácia usa no AGHU). Unidade sem código
# conhecido: o robô pede para a pessoa escolher aquele campo à mão.
PADRAO_CABECALHO = {
    # CA Requisição fica com a pessoa (ela escolhe à mão).
    "HEMODINAMICA": {"sbCCAplicacao": "31047", "sbAlmoxarifado": "12"},
}


def _codigos_cabecalho(mod, at: dict) -> dict:
    un = mod.norm(at.get("unidade") or "").upper().replace(" ", "")
    for chave, cods in PADRAO_CABECALHO.items():
        if chave in un:
            base = dict(cods)
            break
    else:
        base = {}
    try:  # config.ini [rm] cc_requisicao / cc_aplicacao / almoxarifado sobrepõe
        import configparser
        c = configparser.ConfigParser()
        c.read(mod.PASTA / "config.ini", encoding="utf-8")
        if c.has_section("rm"):
            for chave, campo in (("cc_requisicao", "sbCCReq"), ("cc_aplicacao", "sbCCAplicacao"),
                                 ("almoxarifado", "sbAlmoxarifado")):
                if c["rm"].get(chave, "").strip():
                    base[campo] = c["rm"][chave].strip()
    except Exception:
        pass
    return base


def _botao(frame, dentro: str, texto: str):
    loc = frame.locator(f'[id="{dentro}"] button:has-text("{texto}")')
    return loc.first if loc.count() else None


def _vincular_atendimento(mod, frame, at: dict) -> bool:
    """Prontuário → Buscar → escolhe o atendimento → Selecionar. False = não conseguiu (pessoa faz à mão)."""
    pront = re.sub(r"\D", "", str(at.get("prontuario") or ""))
    buscar = _botao(frame, "selecionaPaciente", "Buscar")
    if not pront or buscar is None:
        return False
    campo = frame.locator(mod.sel("prontuarioEdicao:prontuarioEdicao:inputId"))
    if campo.count() and campo.is_enabled():
        mod.digitar(frame, "prontuarioEdicao:prontuarioEdicao:inputId", pront)
    buscar.click()
    mod.esperar_ajax(frame)
    linhas = frame.locator('[id="tabelaVincularAtendimento:resultList_data"] > tr')
    try:
        linhas.first.wait_for(state="visible", timeout=15_000)
    except Exception:
        _e, outras = mod.mensagens(frame)
        if any("não possui atendimento" in m.lower() for m in outras + _e):
            mod.falar("   ATENÇÃO: o AGHU diz que este paciente NÃO TEM ATENDIMENTO para vincular.")
            mod.falar("   Sem atendimento o AGHU não deixa gravar material com o paciente informado.")
            mod.falar("   Resolva no AGHU (atendimento do procedimento) e vincule à mão: Buscar → Selecionar.")
        else:
            mod.falar("   O AGHU não mostrou a lista de atendimentos do paciente.")
        return False
    ops = []
    for i in range(linhas.count()):
        tds = [re.sub(r"\s+", " ", t).strip() for t in linhas.nth(i).locator(":scope > td").all_inner_texts()]
        tem_radio = linhas.nth(i).locator("input[type=radio]").count() > 0
        if len(tds) >= 4 and tds[1] and tem_radio:
            ops.append((i, tds[1], tds[2], tds[3], tds[4] if len(tds) > 4 else ""))
    if not ops:
        if linhas.count():
            mod.falar("   O AGHU mostra atendimento, mas SEM código e sem opção para selecionar "
                      "(acontece na homologação). Vincule à mão se der, ou teste com outro paciente.")
        else:
            mod.falar("   O paciente não tem atendimento para vincular no AGHU.")
        try:
            fechar = _botao(frame, "modalVincularAtendimentoRM", "Fechar")
            if fechar is not None:
                fechar.click()
                mod.esperar_ajax(frame)
        except Exception:
            pass
        return False
    escolha = ops[0]
    if len(ops) > 1:
        mod.falar("   Atendimentos do paciente no AGHU:")
        for n, (_i, cod, data, unid, orig) in enumerate(ops, 1):
            mod.falar(f"     {n}) {cod} · {data} · {unid} · {orig}")
        resp = mod.perguntar(f"   Número do atendimento para esta RM [1]: ").strip() or "1"
        if not resp.isdigit() or not 1 <= int(resp) <= len(ops):
            return False
        escolha = ops[int(resp) - 1]
    i, cod, data, unid, orig = escolha
    mod.falar(f"   vinculando o atendimento {cod} ({data} · {unid} · {orig})")
    linhas.nth(i).locator("input[type=radio]").check()
    mod.esperar_ajax(frame)
    sel_btn = _botao(frame, "modalVincularAtendimentoRM", "Selecionar")
    if sel_btn is None:
        return False
    try:
        frame.wait_for_function(
            """() => { const b=[...document.querySelectorAll('[id="modalVincularAtendimentoRM"] button')]
                       .find(x => x.innerText.includes('Selecionar')); return b && !b.disabled; }""", timeout=10_000)
    except Exception:
        pass
    sel_btn.click()
    mod.esperar_ajax(frame)
    return True


def _escolher_codigo(mod, frame, base: str, codigo: str) -> bool:
    """Deixa o campo de busca `base` com a opção `codigo` ESCOLHIDA na lista."""
    if mod.valor_campo(frame, f"{base}:{base}:suggestion_hinput").endswith(codigo) and \
            mod.valor_campo(frame, f"{base}:{base}:suggestion_input") == codigo:
        return True
    campo = frame.locator(mod.sel(f"{base}:{base}:suggestion_input"))
    if campo.count() and campo.is_disabled():
        limpar = frame.locator(mod.sel(f"{base}:{base}:sgClear"))
        if not limpar.count():
            return False
        limpar.first.click()
        mod.esperar_ajax(frame)
    ok, _ops = mod.escolher_sugestao(
        frame, base, codigo, lambda ops: next((k for k, (rot, _d) in enumerate(ops) if rot.strip() == codigo), None))
    return ok


def _preencher_cabecalho(mod, frame, at: dict) -> None:
    """O robô vincula o atendimento e escolhe CC/almoxarifado. O que não der, a pessoa faz à mão."""
    mod.falar("Preenchendo o cabeçalho da RM…")
    # v18.12: digitar o prontuário APAGA o CA Requisição (o AGHU dispara sgClear sozinho).
    # Guardo o que a pessoa escolheu para repor depois de vincular o atendimento.
    cods = _codigos_cabecalho(mod, at)
    ja_escolhido = mod.valor_campo(frame, "sbCCReq:sbCCReq:suggestion_input").strip()
    if ja_escolhido and not cods.get("sbCCReq"):
        cods["sbCCReq"] = ja_escolhido
    if _vincular_atendimento(mod, frame, at):
        mod.falar("   atendimento vinculado.")
    else:
        mod.falar("   Não consegui vincular o atendimento sozinho.")
    if ja_escolhido:
        mod.falar(f"   (o AGHU apaga o CA Requisição ao vincular o paciente — vou repor o {ja_escolhido})")
    for base, nome in CABECALHO:   # depois do vínculo (vincular troca o CA Aplicação)
        cod = cods.get(base)
        if not cod:
            continue
        if _escolher_codigo(mod, frame, base, cod):
            mod.falar(f"   {nome}: {cod}")
        else:
            mod.falar(f"   Não consegui escolher {nome} {cod}.")


def _preparar_cabecalho(mod, pagina_atual, at: dict, automatico: bool = True, inicio: bool = True):
    """Robô preenche o cabeçalho; a pessoa confere/completa. Devolve o frame ou None."""
    if inicio:
        mod.esperar_voce("No navegador: faça o login e abra Estoque → Requisição de Material → Nova Requisição "
                         "(tela em branco). NÃO precisa preencher nada: o robô põe o prontuário, vincula o "
                         "atendimento e escolhe CA Aplicação e Almoxarifado; o CA REQUISIÇÃO fica com você "
                         "(escolha na lista antes ou quando eu pedir)")
    tentou = False
    while True:
        frame = _achar(mod, pagina_atual(), "formItens")
        if frame is None:
            mod.esperar_voce("Não achei a tela Geração/Alteração de Requisição de Material. Abra a RM no navegador")
            continue
        if automatico and not tentou:
            tentou = True
            try:
                _preencher_cabecalho(mod, frame, at)
            except Exception as e:  # noqa: BLE001
                mod.falar(f"   Não consegui preencher tudo sozinho ({e.__class__.__name__}).")
            frame = _achar(mod, pagina_atual(), "formItens") or frame
        faltam = _faltando_cabecalho(mod, frame)
        if not faltam and _material_liberado(mod, frame):
            return frame
        if faltam:
            mod.falar(f"   Falta escolher NA LISTA: {', '.join(faltam)}.")
        else:
            mod.falar("   O campo Material ainda está bloqueado.")
        mod.falar("   Faça à mão NESTA ORDEM: prontuário → Buscar → selecione o atendimento → Selecionar; "
                  "só DEPOIS escolha na lista CA Requisição, CA Aplicação e Almoxarifado "
                  "(vincular o paciente apaga o CA Requisição).")
        resp = mod.perguntar("   Arrume na tela e aperte ENTER para eu conferir de novo (ou S para sair): ").upper()
        if resp.startswith("S"):
            return None


def incluir_itens(mod, pagina_atual, at: dict, itens: list[dict], parar=lambda: False) -> bool | None:
    """Tela 1 — Geração da RM: inclui material + quantidade. None = parou."""
    frame = _preparar_cabecalho(mod, pagina_atual, at)
    if frame is None:
        return None
    if not _conferir_paciente(mod, frame, at, "prontuarioEdicao:prontuarioEdicao:inputId"):
        return None
    feitos, pulados = [], []
    for it in itens:
        if parar():
            raise KeyboardInterrupt
        cod, qtd = str(it["codigo"]).strip(), int(it["quantidade"])
        mod.falar(f"\n== Material {cod} — qtd {qtd} — {(it.get('descricao') or '')[:60]}")
        for tentativa in range(3):
            frame = _achar(mod, pagina_atual(), "formItens") or frame
            if cod.lstrip("0") in [c.lstrip("0") for c in _linhas_itens_geracao(frame)]:
                mod.falar("   está na RM." if tentativa else "   já está na RM — não incluí de novo.")
                feitos.append(cod)
                break
            if _faltando_cabecalho(mod, frame) or not _material_liberado(mod, frame):
                frame = _preparar_cabecalho(mod, pagina_atual, at, inicio=False)
                if frame is None:
                    return None
            ok, opcoes = mod.escolher_sugestao(
                frame, "sbMaterial", cod,
                lambda ops: next((k for k, (rot, _d) in enumerate(ops) if rot.lstrip("0") == cod.lstrip("0")), None))
            if not ok:
                vistos = ", ".join(r for r, _d in opcoes[:5]) or "nenhum"
                mod.falar(f"   ATENÇÃO: não achei o material {cod} neste almoxarifado (opções: {vistos}). Pulei — lance à mão.")
                pulados.append(cod)
                break
            mod.limpar_mensagens(frame)
            mod.digitar(frame, "qtd:qtd:inputId_input", str(qtd), tab=False)
            frame.locator(mod.sel("btGravarItem:button")).click()
            _esperar_pagina(frame)
            frame = _achar(mod, pagina_atual(), "formItens") or frame
            erros, _o = mod.mensagens(frame)
            if any("atendimento" in e.lower() for e in erros):
                for e in erros:
                    mod.falar(f"   ERRO DO AGHU: {e}")
                mod.falar("   Vou vincular o atendimento do paciente e tentar este material de novo.")
                try:
                    _vincular_atendimento(mod, frame, at)
                except Exception:
                    pass
                continue
            if any("obrigat" in e.lower() for e in erros):
                for e in erros:
                    mod.falar(f"   ERRO DO AGHU: {e}")
                mod.falar("   O AGHU perdeu um campo do cabeçalho. Vou pedir para conferir e tento este material de novo.")
                continue
            if not mod.checar_erros(frame, "gravar item"):
                pulados.append(cod)
                break
            if cod.lstrip("0") in [c.lstrip("0") for c in _linhas_itens_geracao(frame)]:
                mod.falar(f"   incluído (qtd {qtd}).")
                feitos.append(cod)
            else:
                mod.falar(f"   ATENÇÃO: o {cod} não apareceu nos itens da RM. Confira.")
                pulados.append(cod)
            break
        else:
            mod.falar(f"   Não consegui incluir o {cod} depois de 3 tentativas. Lance à mão.")
            pulados.append(cod)
    mod.falar("\n" + "=" * 78)
    mod.falar(f"Na RM: {len(feitos)} material(is) {', '.join(feitos)}")
    if pulados:
        mod.falar(f"Para conferir / lançar à mão: {', '.join(pulados)}")
    return True


def _esperar_efetivacao(mod, pagina_atual, segundos: int = 240):
    """v18.12: espera a tela "Efetivar Requisição Material" abrir sozinha (sem pedir ENTER).

    No AGHU o caminho é: Confirmar → modal "Sim" → Efetivar. Enquanto a pessoa faz isso,
    o robô fica olhando a tela; assim ela não precisa voltar à janela preta.
    """
    mod.falar("\nAgora NA TELA DO AGHU: clique em CONFIRMAR, depois em SIM e, por fim, em EFETIVAR.")
    mod.falar("Estou esperando a tela “Efetivar Requisição Material” abrir…")
    for _ in range(max(1, segundos // 2)):
        frame = _achar(mod, pagina_atual(), "formControleValidade")
        if frame is not None:
            mod.falar("   tela de efetivação aberta.")
            return frame
        try:
            pagina_atual().wait_for_timeout(2000)
        except Exception:
            break
    while True:
        mod.esperar_voce("Não achei a tela Efetivar Requisição Material. Abra a efetivação da RM")
        frame = _achar(mod, pagina_atual(), "formControleValidade")
        if frame is not None:
            return frame


def marcar_lotes(mod, pagina_atual, itens: list[dict], parar=lambda: False) -> list[str]:
    """Tela 2 — Efetivação: em cada material, marca o lote usado e a quantidade atendida."""
    frame = _esperar_efetivacao(mod, pagina_atual)
    por_codigo = {str(i["codigo"]).lstrip("0"): i for i in itens}
    problemas: list[str] = []
    n_itens = len(frame.query_selector_all("tbody[id$='sdTableItemRequisicaoMaterial:resultList_data'] > tr"))
    for ri in range(n_itens):
        if parar():
            raise KeyboardInterrupt
        frame = _achar(mod, pagina_atual(), "formControleValidade") or frame
        tr = frame.query_selector(f"tbody[id$='sdTableItemRequisicaoMaterial:resultList_data'] > tr[data-ri='{ri}']")
        if tr is None:
            continue
        txt = " | ".join((td.inner_text() or "").strip() for td in tr.query_selector_all(":scope > td"))
        cod = _codigo_da_linha(txt)
        it = por_codigo.get(cod.lstrip("0"))
        mod.falar(f"\n== Efetivação · material {cod or '?'}")
        if not it:
            mod.falar("   este material não está no TraceOPME para este paciente — deixei para você.")
            continue
        # seleciona o item (o AGHU mostra os lotes dele no Controle de Validade)
        caixa = tr.query_selector(".ui-radiobutton-box") or tr.query_selector(".ui-chkbox-box") \
            or tr.query_selector("input[type=radio], input[type=checkbox]")
        if caixa is None:
            mod.falar("   não achei onde selecionar este item. Selecione à mão.")
            problemas.append(f"{cod} (selecionar item)")
            continue
        caixa.click()
        mod.esperar_ajax(frame)
        frame = _achar(mod, pagina_atual(), "formControleValidade") or frame
        linhas = frame.query_selector_all("tbody[id$='tabelaControleValidade:resultList_data'] > tr")
        mapa, validades = {}, {}
        for lr in linhas:
            tds = lr.query_selector_all(":scope > td")
            if len(tds) > 3:
                chave = _norm_lote(tds[1].inner_text())
                val = (tds[3].inner_text() or "").strip()
                # mesmo lote em duas linhas: fica a de validade igual à do TraceOPME (resolvido abaixo)
                mapa.setdefault(chave, []).append(lr.get_attribute("data-ri"))
                validades[lr.get_attribute("data-ri")] = val
        # v18.12 (HAR 16/11): o AGHU preenche a "Quantidade Atendida" do lote sozinho
        # quando a QUANTIDADE ENTREGUE é digitada na LINHA DO ITEM. Então: marca o(s)
        # lote(s) → digita a quantidade do item → só ajusta o lote se houver mais de um.
        marcados = []
        for l in it["lotes"]:
            lote, q, val = l["lote"], int(l["quantidade"]), (l.get("validade") or "").strip()
            candidatos = mapa.get(_norm_lote(lote), []) if lote else []
            ri_lote = next((r for r in candidatos if val and validades.get(r) == val), None) or \
                (candidatos[0] if candidatos else None)
            if ri_lote is not None and val and validades.get(ri_lote) and validades[ri_lote] != val:
                mod.falar(f"   ATENÇÃO: lote {lote} — validade no AGHU {validades[ri_lote]}, no TraceOPME {val}. Confira.")
                problemas.append(f"{cod} lote {lote} (validade)")
            if ri_lote is None:
                # v18.12: lote do TraceOPME que não existe no AGHU (lote cadastrado errado,
                # material trocado na ponta…) — o robô pega OUTRO lote para a RM não travar,
                # preferindo um com saldo suficiente, e avisa para a pessoa conferir.
                livres = [(r, _saldo_do_lote(frame, r)) for rs in mapa.values() for r in rs
                          if r not in [m[0] for m in marcados]]
                livres.sort(key=lambda x: (x[1] < q, -x[1]))
                if not livres:
                    mod.falar(f"   ATENÇÃO: o material não tem nenhum lote no estoque do AGHU. Resolva à mão.")
                    problemas.append(f"{cod} lote {lote or '—'} (sem lote no AGHU)")
                    continue
                ri_lote = livres[0][0]
                outro = _lote_da_linha(frame, ri_lote)
                disp = ", ".join(k for k in mapa if k) or "nenhum"
                mod.falar(f"   ATENÇÃO: o lote {lote or '(sem lote)'} NÃO existe no AGHU para este material "
                          f"(lotes no AGHU: {disp}).")
                mod.falar(f"   Usei o lote {outro} (validade {validades.get(ri_lote) or '—'}) para a RM sair. "
                          f"CONFIRA antes de efetivar.")
                problemas.append(f"{cod}: lote {lote or '—'} não existe — usei {outro}")
            base = f"tbody[id$='tabelaControleValidade:resultList_data'] > tr[data-ri='{ri_lote}']"
            lr = frame.query_selector(base)
            tds = lr.query_selector_all(":scope > td")
            saldo = _numero(tds[-1].inner_text()) if tds else 0
            if saldo and saldo < q:
                mod.falar(f"   ATENÇÃO: o lote {lote} tem só {int(saldo)} no AGHU; no TraceOPME são {q}.")
                problemas.append(f"{cod} lote {lote} (saldo)")
            marcado = lr.query_selector("input[type=checkbox]")
            if not (marcado and marcado.is_checked()):
                (lr.query_selector(".ui-chkbox-box") or marcado).click()
                mod.esperar_ajax(frame)
                frame = _achar(mod, pagina_atual(), "formControleValidade") or frame
            marcados.append((ri_lote, lote, q, validades.get(ri_lote) or val))

        if not marcados:
            continue

        # quantidade entregue do item (soma dos lotes marcados)
        total = sum(q for _ri, _lote, q, _v in marcados)
        if not _quantidade_do_item(mod, frame, ri, total):
            mod.falar(f"   ATENÇÃO: não achei onde pôr a Quantidade Entregue do material {cod}. Preencha à mão.")
            problemas.append(f"{cod} (quantidade entregue)")
            continue
        frame = _achar(mod, pagina_atual(), "formControleValidade") or frame

        # com mais de um lote o AGHU não tem como repartir sozinho: digita lote a lote
        if len(marcados) > 1:
            for ri_lote, lote, q, _v in marcados:
                base = f"tbody[id$='tabelaControleValidade:resultList_data'] > tr[data-ri='{ri_lote}']"
                campo = frame.query_selector(f"{base} input[type=text]:not([readonly])")
                if campo is None:
                    mod.falar(f"   ATENÇÃO: a Quantidade Atendida do lote {lote} está travada. Preencha à mão.")
                    problemas.append(f"{cod} lote {lote}")
                    continue
                campo.click(click_count=3)
                campo.fill(str(q))
                campo.press("Tab")
                mod.esperar_ajax(frame)
                frame = _achar(mod, pagina_atual(), "formControleValidade") or frame
        if mod.checar_erros(frame, "quantidade"):
            for _ri, lote, q, v in marcados:
                mod.falar(f"   lote {lote} · validade {v or '—'}: {q} marcado(s).")
        else:
            problemas.append(f"{cod} (quantidade)")

    mod.falar("\n" + "=" * 78)
    if problemas:
        mod.falar(f"Para conferir à mão: {'; '.join(problemas)}")
    mod.falar("CONFIRA os lotes e quantidades e clique em EFETIVAR você mesma. O robô não efetiva.")
    return problemas


def lancar(mod, pagina_atual, at: dict, itens: list[dict], parar=lambda: False) -> bool | None:
    if incluir_itens(mod, pagina_atual, at, itens, parar) is None:
        return None
    marcar_lotes(mod, pagina_atual, itens, parar)
    try:
        import os
        if os.environ.get("ROBO_TESTE"):
            f = _achar(mod, pagina_atual(), "formControleValidade")
            print("MOCKLOG", f.evaluate("JSON.stringify(window.LOG || [])") if f else "[]")
    except Exception:
        pass
    mod.esperar_voce("Confira os lotes e as quantidades e clique em EFETIVAR (e depois em Sim) na tela do AGHU")
    return mod.sim("A RM foi EFETIVADA no AGHU?")
