"""Passos do robô na tela "Materiais Consumidos Cirurgia" do AGHU (Nota de Consumo).

Usado pelo robô instalado no computador (robo_nota_aghu.py, link do TraceOPME com
k = "consumo"). A pessoa abre a cirurgia no AGHU; o robô só inclui material e
quantidade e para antes de gravar.

`mod` é o módulo do robô (falar, sim, esperar_voce, digitar, escolher_sugestao…).
"""

from __future__ import annotations

import re


def _achar(mod, pagina):
    for f in pagina.frames:
        try:
            if f.query_selector(mod.sel("formMaterialConsumidoLista")):
                return f
        except Exception:
            continue
    return None


def _linha(mod, frame, codigo: str):
    for tr in frame.query_selector_all(f"{mod.sel('listaMaterial:resultList_data')} > tr"):
        tds = tr.query_selector_all(":scope > td")
        if len(tds) > 1 and re.match(rf"^0*{re.escape(codigo.lstrip('0'))}\s*-", (tds[1].inner_text() or "").strip()):
            ri = tr.get_attribute("data-ri")
            return int(ri) if ri and ri.isdigit() else None
    return None


def _numero(v) -> float:
    try:
        return float(str(v).replace(".", "").replace(",", ".") or 0)
    except ValueError:
        return 0.0


def mostrar_resumo(mod, at: dict, itens: list[dict]) -> None:
    mod.falar(f"Nota de consumo · prontuário {at.get('prontuario')} · {at.get('paciente') or ''} · {at.get('data_br') or ''}")
    mod.falar("-" * 78)
    for n, i in enumerate(itens, 1):
        mod.falar(f"{n:>2}. AGHU {i['codigo']:<8} qtd {i['quantidade']:>3}  {(i.get('descricao') or '')[:60]}")
    mod.falar("-" * 78)
    for d in at.get("sem_codigo") or []:
        mod.falar(f"ATENÇÃO: {d} está sem código AGHU no TraceOPME — lance à mão.")


def lancar(mod, pagina_atual, at: dict, itens: list[dict], parar=lambda: False) -> bool | None:
    """Preenche a lista. Devolve True se a pessoa gravou, False se não, None se parou antes."""
    data = at.get("data_br") or ""
    mod.esperar_voce(f"No navegador que abriu: faça o login, abra a Nota de Consumo, pesquise o prontuário "
                     f"{at.get('prontuario')}{' de ' + data if data else ''}, abra a cirurgia e clique em "
                     f"Materiais Consumidos")
    frame = _achar(mod, pagina_atual())
    while frame is None:
        mod.esperar_voce("Não achei a tela Materiais Consumidos Cirurgia. Abra a cirurgia do paciente e clique em "
                         "Materiais Consumidos")
        frame = _achar(mod, pagina_atual())
    nome_tela = mod.valor_campo(frame, "nomePaciente:nomePaciente:inputId")
    data_tela = mod.valor_campo(frame, "dataCirurgia:dataCirurgia:inputId")
    mod.falar(f"Cirurgia na tela: {nome_tela or '—'} · {data_tela or '—'}")
    nome_trace = mod.norm(at.get("paciente") or "")
    if nome_trace and mod.norm(nome_tela) and nome_trace.split()[0] != mod.norm(nome_tela).split()[0]:
        if not mod.sim(f"ATENÇÃO: o paciente da tela ({nome_tela}) parece diferente do TraceOPME "
                       f"({at.get('paciente')}). Continuar assim mesmo?"):
            return None
    if data and data_tela and data_tela.strip() != data:
        if not mod.sim(f"ATENÇÃO: a data da cirurgia na tela ({data_tela}) é diferente do TraceOPME ({data}). "
                       "Continuar assim mesmo?"):
            return None
    feitos, pulados = [], []
    for it in itens:
        if parar():
            raise KeyboardInterrupt
        cod, qtd = str(it["codigo"]).strip(), int(it["quantidade"])
        mod.falar(f"\n== Material {cod} — qtd {qtd} — {(it.get('descricao') or '')[:60]}")
        i = _linha(mod, frame, cod)
        if i is not None:
            campo = f"listaMaterial:resultList:{i}:quantidade_input"
            atual = mod.valor_campo(frame, campo)
            if _numero(atual) == qtd:
                mod.falar("   já está na lista com a mesma quantidade.")
                feitos.append(cod)
                continue
            if _numero(atual) and not mod.sim(f"   Na lista do AGHU o {cod} já está com {atual}. "
                                              f"No TraceOPME são {qtd}. Trocar para {qtd}?"):
                pulados.append(cod)
                continue
            mod.digitar(frame, campo, str(qtd))
            if mod.checar_erros(frame, "quantidade"):
                mod.falar(f"   já estava na lista do AGHU: quantidade preenchida ({qtd}).")
                feitos.append(cod)
            else:
                pulados.append(cod)
            continue
        ok, opcoes = mod.escolher_sugestao(
            frame, "suggestionMaterial", cod,
            lambda ops: next((k for k, (rot, _d) in enumerate(ops) if rot.lstrip("0") == cod.lstrip("0")), None))
        if not ok:
            vistos = ", ".join(r for r, _d in opcoes[:5]) or "nenhum"
            mod.falar(f"   ATENÇÃO: não achei o material {cod} no AGHU (opções: {vistos}). Pulei — lance à mão.")
            pulados.append(cod)
            continue
        mod.digitar(frame, "qtdMat:qtdMat:inputId_input", str(qtd), tab=False)
        frame.locator(mod.sel("btnAdicionarMaterial:button")).click()
        mod.esperar_ajax(frame)
        if not mod.checar_erros(frame, "adicionar"):
            pulados.append(cod)
            continue
        if _linha(mod, frame, cod) is None:
            mod.falar(f"   ATENÇÃO: o {cod} não apareceu na lista do AGHU. Confira.")
            pulados.append(cod)
        else:
            mod.falar(f"   adicionado (qtd {qtd}).")
            feitos.append(cod)
    mod.falar("\n" + "=" * 78)
    mod.falar(f"Na lista: {len(feitos)} material(is) {', '.join(feitos)}")
    if pulados:
        mod.falar(f"Para conferir / lançar à mão: {', '.join(pulados)}")
    mod.falar("CONFIRA a lista no AGHU e clique em GRAVAR você mesma. O robô não grava.")
    try:
        import os
        if os.environ.get("ROBO_TESTE"):
            print("MOCKLOG", frame.evaluate("JSON.stringify(window.LOG || [])"))
    except Exception:
        pass
    mod.esperar_voce("Confira a lista e clique em GRAVAR na tela do AGHU")
    return mod.sim("A lista de materiais foi GRAVADA no AGHU?")
