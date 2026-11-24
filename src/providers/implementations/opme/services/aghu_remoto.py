"""v18.5 — robô do AGHU rodando NO SERVIDOR, com a tela do AGHU dentro do TraceOPME.

Antes o robô precisava ser instalado (Python + janela preta) no computador de quem
lança a nota. Agora ele roda no servidor: a pessoa abre "Lançar no AGHU" na tela da
NF e vê, numa página do TraceOPME,

  - a tela do AGHU (imagem atualizada várias vezes por segundo), onde ela clica e
    digita como se fosse o próprio navegador — é assim que faz o login;
  - o passo atual / a pergunta do robô, com botões (Continuar, Sim/Não…);
  - o log de tudo o que o robô fez.

Os passos de preenchimento são os MESMOS do robô instalado
(`ferramentas/robo_nota_aghu/robo_nota_aghu.py`): o módulo é carregado uma vez por
lançamento, e só a "conversa" (falar / perguntar / esperar você) é trocada pela página.

Senha: o que a pessoa digita na tela do AGHU vai direto para o navegador do servidor.
Não é gravado em log, em banco nem na auditoria (as chamadas de teclado não são
auditadas), e o robô continua sem digitar senha nenhuma.
"""

from __future__ import annotations

import importlib.util
import os
import queue
import secrets
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from .. import db, log
from ..utils import texto

RAIZ = Path(__file__).resolve().parents[5]
ROBO = RAIZ / "ferramentas" / "robo_nota_aghu" / "robo_nota_aghu.py"

LARGURA, ALTURA = 1366, 768          # tamanho padrão da tela do AGHU no servidor
# v18.5.1: a tela do AGHU no servidor tem o tamanho da área da página (1:1, nítida).
LIMITES = {"largura": (1000, 2560), "altura": (560, 1440)}
MAX_SIMULTANEOS = int(os.getenv("AGHU_ROBO_MAX", "3") or 3)
MINUTOS_SEM_USO = 40                  # sem ninguém olhando a página: encerra
INTERVALO_QUADRO = 0.35               # s entre imagens enquanto espera a pessoa
TECLAS = {"Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
          "Home", "End", "PageUp", "PageDown", "F5"}

_sessoes: dict[str, "Sessao"] = {}
_trava = threading.Lock()


class Cancelado(Exception):
    pass


def _agora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _carregar_robo():
    """Uma cópia própria do módulo do robô para cada lançamento (globais separadas)."""
    nome = f"robo_nota_aghu_{secrets.token_hex(4)}"
    spec = importlib.util.spec_from_file_location(nome, ROBO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tamanho(largura, altura) -> tuple[int, int]:
    def lim(v, padrao, chave):
        try:
            v = int(float(v))
        except (TypeError, ValueError):
            return padrao
        a, b = LIMITES[chave]
        return max(a, min(b, v))
    return lim(largura, LARGURA, "largura"), lim(altura, ALTURA, "altura")


def _tipo_pergunta(msg: str) -> tuple[str, list[dict]]:
    if "(S/N)" in msg:
        return "opcoes", [{"rotulo": "Sim", "valor": "S"}, {"rotulo": "Não", "valor": "N"}]
    if "[C]ontinuar" in msg:
        return "opcoes", [{"rotulo": "Continuar", "valor": "C"}, {"rotulo": "Pular este material", "valor": "P"},
                          {"rotulo": "Parar", "valor": "S"}]
    if "Número da nota" in msg:
        return "texto", []
    return "texto", []


class Sessao:
    def __init__(self, chave: str, numero_nf: str, usuario: str, nome: str = "",
                 largura: int = LARGURA, altura: int = ALTURA, tipo: str = "nf"):
        self.id = secrets.token_urlsafe(16)
        # tipo "nf": nota fiscal de entrada (chave = chave da NF);
        # tipo "consumo" (v18.6): nota de consumo do paciente (chave = "consumo:<id_atendimento>").
        self.tipo = tipo
        self.largura, self.altura = _tamanho(largura, altura)
        self._mudou = threading.Condition()
        self._cdp = None
        self._transmitindo = False
        self.chave, self.numero_nf, self.usuario, self.nome = chave, numero_nf, usuario, nome or usuario
        self.status = "iniciando"     # iniciando | trabalhando | sua_vez | concluido | erro | cancelado
        self.resultado = ""
        self.log: list[str] = []
        self.pergunta: dict | None = None
        self.quadro: bytes | None = None
        self.versao = 0
        self.criado = time.time()
        self.visto = time.time()      # última vez que a página consultou
        self._respostas: "queue.Queue[str]" = queue.Queue()
        self._entradas: "queue.Queue[dict]" = queue.Queue()
        self._cancelar = threading.Event()
        self._ultimo_quadro = 0.0
        self.page = None
        self.thread = threading.Thread(target=self._rodar, name=f"robo-aghu-{self.id[:6]}", daemon=True)

    # ------------------------------------------------------------ o que a página vê
    def estado(self, desde: int = 0) -> dict:
        self.visto = time.time()
        return {"ok": True, "sessao": self.id, "status": self.status, "resultado": self.resultado,
                "pergunta": self.pergunta, "versao": self.versao, "total_log": len(self.log),
                "log": self.log[max(0, int(desde or 0)):], "numero_nf": self.numero_nf, "chave": self.chave,
                "tipo": self.tipo,
                "largura": self.largura, "altura": self.altura, "ativo": self.thread.is_alive()}

    def responder(self, resposta: str) -> None:
        self.visto = time.time()
        self._respostas.put(texto(resposta))

    def entrada(self, ev: dict) -> bool:
        """Clique / tecla / texto / rolagem na tela do AGHU. Só vale na vez da pessoa."""
        self.visto = time.time()
        if self.status != "sua_vez":
            return False
        self._entradas.put(ev)
        return True

    def cancelar(self) -> None:
        self._cancelar.set()
        self._respostas.put("S")

    # ------------------------------------------------------------ conversa do robô
    def falar(self, msg: str = "") -> None:
        for linha in str(msg).split("\n"):
            if linha.strip() and set(linha.strip()) <= {"-", "="}:
                linha = "─" * 24           # separadores curtos (cabem no painel)
            if linha.strip():
                self.log.append(f"{_agora()} {linha.rstrip()}")
        if len(self.log) > 3000:
            del self.log[:500]
        self._atualizar_quadro()

    def perguntar(self, msg: str, tipo: str = "", opcoes: list | None = None) -> str:
        msg = str(msg).strip()
        if not tipo:
            tipo, opcoes = _tipo_pergunta(msg)
        limpo = (msg.replace("Quando terminar, aperte ENTER aqui...", "").replace("(S/N):", "").replace(">>>", "")
                 .replace("[C]ontinuar, [P]ular este material ou [S]air?", "").strip())
        self.log.append(f"{_agora()} ? {limpo}")
        while not self._respostas.empty():
            self._respostas.get_nowait()
        self.pergunta = {"texto": limpo, "tipo": tipo, "opcoes": opcoes or []}
        self.status = "sua_vez"
        self._atualizar_quadro(forcar=True)
        try:
            while True:
                if self._cancelar.is_set():
                    raise Cancelado()
                if time.time() - self.visto > MINUTOS_SEM_USO * 60:
                    self.falar(f"Ninguém acompanhou a página por {MINUTOS_SEM_USO} minutos: encerrei o robô.")
                    raise Cancelado()
                self._processar_entradas()
                self._atualizar_quadro()
                p = self._pagina()
                try:
                    if p is not None:
                        p.wait_for_timeout(30)      # também entrega os quadros da tela
                        resp = self._respostas.get_nowait()
                    else:
                        resp = self._respostas.get(timeout=0.1)
                except queue.Empty:
                    continue
                except Exception:
                    time.sleep(0.05)
                    continue
                if self._cancelar.is_set():
                    raise Cancelado()
                if tipo != "senha":
                    self.log.append(f"{_agora()}   resposta: {resp or '(continuar)'}")
                return resp
        finally:
            self.pergunta = None
            self.status = "trabalhando"

    def esperar_voce(self, msg: str) -> None:
        self.perguntar(msg.strip(), tipo="continuar", opcoes=[{"rotulo": "Pronto, continuar", "valor": ""}])

    # ------------------------------------------------------------ tela
    def _pagina(self):
        p = self.page
        try:
            if p is not None and not p.is_closed():
                if self._cdp is not None and getattr(self, "_pagina_transmitida", None) is not p:
                    self._pagina_transmitida = p
                    self._ligar_transmissao(p)
                return p
            abertas = [x for x in p.context.pages if not x.is_closed()] if p is not None else []
            self.page = abertas[-1] if abertas else None
            if self.page is not None:
                self._ligar_transmissao(self.page)
        except Exception:
            self.page = None
        return self.page

    def _novo_quadro(self, conteudo: bytes) -> None:
        with self._mudou:
            self.quadro = conteudo
            self.versao += 1
            self._ultimo_quadro = time.time()
            self._mudou.notify_all()

    def _ligar_transmissao(self, page) -> None:
        """v18.5.1: o navegador do servidor manda um quadro só quando a tela muda
        (screencast), em vez de tirar foto a cada instante."""
        import base64
        try:
            if self._cdp is not None:
                try:
                    self._cdp.detach()
                except Exception:
                    pass
            cdp = page.context.new_cdp_session(page)

            def quadro(params):
                try:
                    self._novo_quadro(base64.b64decode(params["data"]))
                finally:
                    try:
                        cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
                    except Exception:
                        pass

            cdp.on("Page.screencastFrame", quadro)
            self._pagina_transmitida = page
            cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 72, "maxWidth": self.largura,
                                              "maxHeight": self.altura, "everyNthFrame": 1})
            self._cdp, self._transmitindo = cdp, True
        except Exception:
            self._cdp, self._transmitindo = None, False   # sem screencast: fotos periódicas
        self._atualizar_quadro(forcar=True)

    def _atualizar_quadro(self, forcar: bool = False) -> None:
        if self._transmitindo and not forcar:
            return
        if not forcar and time.time() - self._ultimo_quadro < INTERVALO_QUADRO:
            return
        p = self.page
        if p is None:
            return
        try:
            self._novo_quadro(p.screenshot(type="jpeg", quality=72, timeout=5000))
        except Exception:
            pass

    def fluxo(self):
        """Quadros da tela para a página: 4 bytes de tamanho + JPEG. Tamanho 0 = "ainda aqui"."""
        ultima = -1
        inicio = time.time()
        while time.time() - inicio < 2 * 3600:
            with self._mudou:
                if self.versao == ultima:
                    self._mudou.wait(timeout=8)
                q, v = self.quadro, self.versao
            self.visto = time.time()
            if q and v != ultima:
                ultima = v
                yield len(q).to_bytes(4, "big") + q
                time.sleep(0.03)        # no máximo ~30 quadros por segundo
            else:
                yield b"\0\0\0\0"
            if not self.thread.is_alive() and v == ultima:
                break

    def _processar_entradas(self) -> None:
        p = self._pagina()
        mexeu = False
        while True:
            try:
                ev = self._entradas.get_nowait()
            except queue.Empty:
                break
            if p is None:
                continue
            try:
                t = ev.get("t")
                x, y = float(ev.get("x", .5)) * self.largura, float(ev.get("y", .5)) * self.altura
                if t == "clique":
                    p.mouse.click(x, y, click_count=2 if ev.get("duplo") else 1)
                elif t == "mover":
                    p.mouse.move(x, y)
                elif t == "texto":
                    p.keyboard.type(str(ev.get("v", ""))[:500])
                elif t == "tecla":
                    k = str(ev.get("k", ""))
                    base = k.split("+")[-1]
                    if base in TECLAS or (("Control+" in k or "Shift+" in k) and len(base) == 1):
                        p.keyboard.press(k)
                elif t == "rolar":
                    p.mouse.move(x, y)
                    p.mouse.wheel(0, max(-2000, min(2000, float(ev.get("dy", 0)))))
                elif t == "tamanho":
                    self.largura, self.altura = _tamanho(ev.get("largura"), ev.get("altura"))
                    p.set_viewport_size({"width": self.largura, "height": self.altura})
                    self._ligar_transmissao(p)
                mexeu = True
            except Exception:
                pass
        if mexeu and not self._transmitindo:
            try:
                p.wait_for_timeout(100)
            except Exception:
                pass
            self._atualizar_quadro(forcar=True)

    # ------------------------------------------------------------ o lançamento
    def _rodar(self) -> None:
        from . import aghu_robo, planilha_aghu
        mod = None
        arquivo = None
        try:
            mod = _carregar_robo()
            mod.falar = self.falar
            mod.perguntar = self.perguntar
            mod.esperar_voce = self.esperar_voce
            mod.sim = lambda m: self.perguntar(f"{m} (S/N): ").upper().startswith("S")
            self.status = "trabalhando"
            if self.tipo == "consumo":
                preparo = self._preparar_consumo(mod)
            else:
                conteudo, nome = planilha_aghu.xlsx(self.chave)
                if not conteudo:
                    raise SystemExit(nome or "Nenhum item desta nota deu entrada ainda.")
                arquivo = Path(tempfile.mkstemp(prefix="nf_aghu_", suffix=".xlsx")[1])
                arquivo.write_bytes(conteudo)
                self.falar(f"Robô do AGHU no servidor · NF {self.numero_nf} · aberto por {self.nome}")
                nf, serie, itens = mod.ler_planilha(arquivo)
                total = mod.mostrar_resumo(nf, serie, itens)
                preparo = (nf, total, itens) if mod.sim("Lançar estes itens no AGHU?") else None
            if preparo is None:
                self._encerrar(aghu_robo, False, "cancelado", "Lançamento cancelado antes de abrir o AGHU.")
                return
            cfg = mod.config()
            url = os.getenv("AGHU_URL", "") or cfg["url"]
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise SystemExit("O servidor ainda não tem o componente do robô (playwright). "
                                 "Veja LEIA-ME: “Robô do AGHU no servidor”.")
            with sync_playwright() as pw:
                navegador = self._abrir_navegador(pw)
                contexto = navegador.new_context(viewport={"width": self.largura, "height": self.altura},
                                                 locale="pt-BR", ignore_https_errors=True)
                contexto.on("page", lambda pg: setattr(self, "page", pg))   # janela nova: _pagina() religa
                self.page = contexto.new_page()
                self.page.on("dialog", lambda d: d.accept())
                self._ligar_transmissao(self.page)
                self.falar(f"Abrindo o AGHU ({url})…")
                try:
                    self.page.goto(url, timeout=45_000)
                except Exception as e:  # noqa: BLE001
                    raise SystemExit(f"O servidor não conseguiu abrir o AGHU em {url} ({e.__class__.__name__}). "
                                     "Confira com a TI se o servidor do TraceOPME acessa o AGHU.")
                if self.tipo == "consumo":
                    self._lancar_consumo(mod, *preparo)
                else:
                    self._lancar(mod, cfg, *preparo, aghu_robo)
                try:
                    navegador.close()
                except Exception:
                    pass
        except Cancelado:
            self._encerrar(aghu_robo, False, "cancelado", "Parado. Nada foi gravado pelo robô — confira a tela do AGHU.")
        except KeyboardInterrupt:
            self._encerrar(aghu_robo, False, "cancelado", "Parado por você. Nada foi gravado pelo robô.")
        except SystemExit as e:
            self._encerrar(aghu_robo, False, "erro", str(e.code or "O robô parou."))
        except Exception as e:  # noqa: BLE001
            log.erro("robô do AGHU (servidor) parou", self.usuario, e)
            self._encerrar(aghu_robo, False, "erro",
                           f"O robô parou por um erro inesperado: {e.__class__.__name__}: {e}. Nada foi gravado pelo robô.")
        finally:
            self.pergunta = None
            if arquivo:
                try:
                    arquivo.unlink()
                except OSError:
                    pass

    def _abrir_navegador(self, pw):
        """No servidor, sem janela. Usa o Edge/Chrome instalado (não precisa baixar nada);
        se não houver, o Chromium do próprio Playwright."""
        preferido = os.getenv("AGHU_NAVEGADOR_SERVIDOR", "msedge").strip()
        tentativas = [preferido] if preferido else []
        tentativas += [c for c in ("msedge", "chrome", "") if c not in tentativas]
        erro = None
        for canal in tentativas:
            try:
                return pw.chromium.launch(channel=canal or None, headless=True)
            except Exception as e:  # noqa: BLE001
                erro = e
        raise SystemExit("Não encontrei navegador no servidor para o robô (Edge, Chrome ou Chromium). "
                         f"Detalhe: {erro}")

    def _lancar(self, mod, cfg, nf, total, itens, aghu_robo) -> None:
        """Mesmo roteiro do robô instalado (main), sem a janela preta."""
        import re
        mod.esperar_voce(f"Na tela do AGHU: faça o login, abra Estoque → Gerar Nota de Recebimento sem AF "
                         f"e escolha a NF {nf} (botão Nota Fiscal).")
        frame = mod.achar_frame(self._pagina())
        while frame is None:
            mod.esperar_voce("Não achei a tela Gerar Nota de Recebimento sem AF. Abra a tela e escolha a NF.")
            frame = mod.achar_frame(self._pagina())
        nf_tela = mod.valor_campo(frame, "numero:numero:inputId_input")
        serie_tela = mod.valor_campo(frame, "serie:serie:inputId")
        if not nf_tela:
            mod.esperar_voce("A tela ainda não tem nota fiscal escolhida. Clique em Nota Fiscal e escolha a NF.")
            nf_tela = mod.valor_campo(frame, "numero:numero:inputId_input")
        valor_nf = mod.valor_campo(frame, "valorTotalNota:valorTotalNota:inputId_input")
        self.falar(f"Nota na tela: {nf_tela} série {serie_tela or '—'} · valor da NF R$ {valor_nf or '—'}")
        if re.sub(r"\D", "", nf_tela).lstrip("0") != re.sub(r"\D", "", nf).lstrip("0"):
            if not mod.sim(f"ATENÇÃO: a nota da tela ({nf_tela}) é diferente da planilha ({nf}). Continuar assim mesmo?"):
                self._encerrar(aghu_robo, False, "cancelado", "Parado: a nota da tela não é a desta NF.")
                return
        if valor_nf and mod.dinheiro(valor_nf) != total:
            self.falar(f"ATENÇÃO: valor da NF no AGHU (R$ {valor_nf}) é diferente da soma da planilha "
                       f"(R$ {mod.br_mostrar(total)}). O AGHU não vai deixar gravar se não bater.")
            if not mod.sim("Continuar assim mesmo?"):
                self._encerrar(aghu_robo, False, "cancelado", "Parado: o valor da NF não bate.")
                return
        feitos, pulados = [], []
        for item in itens:
            if self._cancelar.is_set():
                raise Cancelado()
            if mod.linha_do_material(frame, item["codigo"]) is not None:
                self.falar(f"== Material {item['codigo']} já está na lista da nota — só confiro e adiciono os lotes que faltam.")
                mod.incluir_lotes(frame, item)
                feitos.append(item["codigo"])
                continue
            if mod.incluir_material(frame, item, cfg):
                mod.incluir_lotes(frame, item)
                feitos.append(item["codigo"])
            else:
                pulados.append(item["codigo"])
        self.falar("=" * 40)
        self.falar(f"Incluídos: {len(feitos)} material(is) {', '.join(feitos)}")
        if pulados:
            self.falar(f"Pulados / para conferir: {', '.join(pulados)}")
        self.falar(f"Soma dos itens na tela: R$ {mod.valor_campo(frame, 'valorTotalItensField:valorTotalItens') or '—'} · "
                   f"planilha R$ {mod.br_mostrar(total)}")
        self.falar("CONFIRA a nota no AGHU (itens, lotes e validades) e clique em GRAVAR você mesma, na tela do AGHU.")
        self.falar("O robô não grava a nota.")
        mod.esperar_voce("Confira e GRAVE a nota no AGHU (botão Gravar, na tela do AGHU).")
        if mod.sim("A nota foi GRAVADA no AGHU?"):
            nr = self.perguntar("Número da nota de recebimento que o AGHU gerou (deixe em branco se não souber):",
                                tipo="texto")
            self._encerrar(aghu_robo, True, "concluido", "Lançamento concluído. A NF foi marcada como lançada no AGHU.", nr)
        else:
            self._encerrar(aghu_robo, False, "concluido", "Robô encerrado. A NF continua como não lançada no AGHU.")

    # ------------------------------------------------------------ v18.6: nota de consumo
    def _preparar_consumo(self, mod):
        from . import nota_consumo
        id_at = self.chave.split(":", 1)[1]
        at = nota_consumo.atendimento(id_at)
        if not at:
            raise SystemExit("Atendimento não encontrado.")
        itens = nota_consumo.itens(id_at)
        self.falar(f"Robô do AGHU no servidor · Nota de consumo · prontuário {at['prontuario']} · "
                   f"{at.get('paciente') or ''} · aberto por {self.nome}")
        com_codigo = [i for i in itens if i["codigo_aghu"]]
        sem_codigo = [i for i in itens if not i["codigo_aghu"]]
        self.falar("─" * 24)
        for n, i in enumerate(com_codigo, 1):
            self.falar(f"{n:>2}. AGHU {i['codigo_aghu']:<8} qtd {i['quantidade']:>3}  {(i['descricao'] or '')[:70]}")
        self.falar("─" * 24)
        for i in sem_codigo:
            self.falar(f"ATENÇÃO: {i['descricao']} está sem código AGHU no TraceOPME — lance à mão.")
        if not com_codigo:
            raise SystemExit("Nenhum material com código AGHU para lançar neste paciente.")
        if not mod.sim("Lançar estes materiais na nota de consumo do AGHU?"):
            return None
        return (at, com_codigo)

    def _lancar_consumo(self, mod, at: dict, itens: list[dict]) -> None:
        """Tela "Materiais Consumidos Cirurgia" (materialPorCirurgiaCRUD) do AGHU."""
        import re
        from ..utils import data_br
        data = data_br(at.get("data_procedimento")) if at.get("data_procedimento") else ""

        def achar():
            for f in self._pagina().frames:
                try:
                    if f.query_selector(mod.sel("formMaterialConsumidoLista")):
                        return f
                except Exception:
                    continue
            return None

        def linha(frame, codigo: str):
            for tr in frame.query_selector_all(f"{mod.sel('listaMaterial:resultList_data')} > tr"):
                tds = tr.query_selector_all(":scope > td")
                if len(tds) > 1 and re.match(rf"^0*{re.escape(codigo.lstrip('0'))}\s*-", (tds[1].inner_text() or "").strip()):
                    ri = tr.get_attribute("data-ri")
                    return int(ri) if ri and ri.isdigit() else None
            return None

        def numero(v) -> float:
            try:
                return float(str(v).replace(".", "").replace(",", ".") or 0)
            except ValueError:
                return 0.0

        mod.esperar_voce(f"Na tela do AGHU: faça o login, abra a Nota de Consumo, pesquise o prontuário "
                         f"{at['prontuario']}{' de ' + data if data else ''}, abra a cirurgia e clique em "
                         f"Materiais Consumidos.")
        frame = achar()
        while frame is None:
            mod.esperar_voce("Não achei a tela Materiais Consumidos Cirurgia. Abra a cirurgia do paciente e clique em "
                             "Materiais Consumidos.")
            frame = achar()
        nome_tela = mod.valor_campo(frame, "nomePaciente:nomePaciente:inputId")
        data_tela = mod.valor_campo(frame, "dataCirurgia:dataCirurgia:inputId")
        self.falar(f"Cirurgia na tela: {nome_tela or '—'} · {data_tela or '—'}")
        nome_trace = mod.norm(at.get("paciente") or "")
        if nome_trace and mod.norm(nome_tela) and nome_trace.split()[0] != mod.norm(nome_tela).split()[0]:
            if not mod.sim(f"ATENÇÃO: o paciente da tela ({nome_tela}) parece diferente do TraceOPME "
                           f"({at.get('paciente')}). Continuar assim mesmo?"):
                self._encerrar(None, False, "cancelado", "Parado: o paciente da tela não é o deste atendimento.")
                return
        if data and data_tela and data_tela.strip() != data:
            if not mod.sim(f"ATENÇÃO: a data da cirurgia na tela ({data_tela}) é diferente do TraceOPME ({data}). "
                           "Continuar assim mesmo?"):
                self._encerrar(None, False, "cancelado", "Parado: a data da cirurgia não bate.")
                return
        feitos, pulados = [], []
        for it in itens:
            if self._cancelar.is_set():
                raise Cancelado()
            cod, qtd = str(it["codigo_aghu"]).strip(), int(it["quantidade"])
            self.falar(f"== Material {cod} — qtd {qtd} — {(it['descricao'] or '')[:60]}")
            i = linha(frame, cod)
            if i is not None:
                campo = f"listaMaterial:resultList:{i}:quantidade_input"
                atual = mod.valor_campo(frame, campo)
                if numero(atual) == qtd:
                    self.falar("   já está na lista com a mesma quantidade.")
                    feitos.append(cod)
                    continue
                if numero(atual) and not mod.sim(f"   Na lista do AGHU o {cod} já está com {atual}. "
                                                 f"No TraceOPME são {qtd}. Trocar para {qtd}?"):
                    pulados.append(cod)
                    continue
                mod.digitar(frame, campo, str(qtd))
                if mod.checar_erros(frame, "quantidade"):
                    self.falar(f"   já estava na lista do AGHU: quantidade preenchida ({qtd}).")
                    feitos.append(cod)
                else:
                    pulados.append(cod)
                continue
            ok, opcoes = mod.escolher_sugestao(
                frame, "suggestionMaterial", cod,
                lambda ops: next((k for k, (rot, _d) in enumerate(ops) if rot.lstrip("0") == cod.lstrip("0")), None))
            if not ok:
                vistos = ", ".join(r for r, _d in opcoes[:5]) or "nenhum"
                self.falar(f"   ATENÇÃO: não achei o material {cod} no AGHU (opções: {vistos}). Pulei — lance à mão.")
                pulados.append(cod)
                continue
            mod.digitar(frame, "qtdMat:qtdMat:inputId_input", str(qtd), tab=False)
            frame.locator(mod.sel("btnAdicionarMaterial:button")).click()
            mod.esperar_ajax(frame)
            if not mod.checar_erros(frame, "adicionar"):
                pulados.append(cod)
                continue
            if linha(frame, cod) is None:
                self.falar(f"   ATENÇÃO: o {cod} não apareceu na lista do AGHU. Confira.")
                pulados.append(cod)
            else:
                self.falar(f"   adicionado (qtd {qtd}).")
                feitos.append(cod)
        self.falar("─" * 24)
        self.falar(f"Na lista: {len(feitos)} material(is) {', '.join(feitos)}")
        if pulados:
            self.falar(f"Para conferir / lançar à mão: {', '.join(pulados)}")
        self.falar("CONFIRA a lista no AGHU e clique em GRAVAR você mesma. O robô não grava.")
        mod.esperar_voce("Confira a lista e clique em GRAVAR na tela do AGHU.")
        if mod.sim("A lista de materiais foi GRAVADA no AGHU?"):
            self._encerrar(None, True, "concluido", "Nota de consumo lançada. O atendimento foi marcado como lançado no AGHU.")
        else:
            self._encerrar(None, False, "concluido", "Robô encerrado. A nota de consumo continua como não lançada.")

    def _encerrar(self, aghu_robo, gravou: bool, status: str, mensagem: str, nr: str = "") -> None:
        if self.status in ("concluido", "erro", "cancelado"):
            return
        try:
            if self.tipo == "consumo":
                from . import nota_consumo
                nota_consumo.marcar(self.chave.split(":", 1)[1], "lancada" if gravou else "", self.usuario)
            elif gravou:
                aghu_robo.marcar(self.chave, "lancada", self.usuario, nr)
            else:
                n = db.consultar_um("SELECT aghu_status FROM notas_fiscais WHERE chave_nf = ?", (self.chave,))
                if n and texto(n["aghu_status"]) == "em_lancamento":
                    db.executar("UPDATE notas_fiscais SET aghu_status = '' WHERE chave_nf = ?", (self.chave,))
        except Exception as e:  # noqa: BLE001
            log.erro("robô do AGHU: falha ao atualizar a situação", self.usuario, e)
        self.falar(mensagem)
        self.resultado = mensagem
        self.status = status
        log.info(f"robô do AGHU (servidor) · {self.tipo} {self.numero_nf} · {status}", self.usuario)


# ---------------------------------------------------------------- uso pelas telas

def _limpar_antigas() -> None:
    agora = time.time()
    for sid, s in list(_sessoes.items()):
        if not s.thread.is_alive() and agora - s.visto > 2 * 3600:
            _sessoes.pop(sid, None)


def ativa_da_nota(chave: str) -> "Sessao | None":
    with _trava:
        _limpar_antigas()
        for s in _sessoes.values():
            if s.chave == texto(chave) and s.thread.is_alive():
                return s
    return None


def iniciar(chave: str, usuario: str, nome: str = "", largura: int = LARGURA,
            altura: int = ALTURA) -> tuple[bool, str, str]:
    """Começa o lançamento no servidor. Devolve (ok, mensagem, id da sessão)."""
    from . import planilha_aghu
    nota = db.consultar_um("SELECT * FROM notas_fiscais WHERE chave_nf = ?", (texto(chave),))
    if not nota:
        return False, "Nota fiscal não encontrada.", ""
    if texto(nota.get("aghu_status")) == "lancada":
        return False, "Esta NF já está marcada como lançada no AGHU.", ""
    if not planilha_aghu.linhas(chave):
        return False, "Nenhum item desta nota deu entrada ainda.", ""
    if not ROBO.is_file():
        return False, "Os passos do robô não estão no servidor (ferramentas/robo_nota_aghu).", ""
    with _trava:
        _limpar_antigas()
        for s in _sessoes.values():
            if s.chave == nota["chave_nf"] and s.thread.is_alive():
                if s.usuario == usuario:
                    return True, "Continuando o lançamento que já estava aberto.", s.id
                return False, f"{s.nome} já está lançando esta NF no AGHU agora.", ""
        if sum(1 for s in _sessoes.values() if s.thread.is_alive()) >= MAX_SIMULTANEOS:
            return False, (f"Já há {MAX_SIMULTANEOS} lançamentos no AGHU abertos no servidor. "
                           "Espere um terminar e tente de novo."), ""
        s = Sessao(nota["chave_nf"], texto(nota["numero_nf"]), usuario, nome, largura, altura)
        _sessoes[s.id] = s
    db.executar("""UPDATE notas_fiscais SET aghu_status = 'em_lancamento', aghu_iniciado_em = ?, aghu_iniciado_por = ?
                   WHERE chave_nf = ?""", (db.agora(), usuario, nota["chave_nf"]))
    s.thread.start()
    log.info(f"robô do AGHU (servidor) iniciado para a NF {nota['numero_nf']}", usuario)
    return True, "Robô iniciado.", s.id


def iniciar_consumo(id_atendimento: str, usuario: str, nome: str = "", largura: int = LARGURA,
                    altura: int = ALTURA) -> tuple[bool, str, str]:
    """v18.6: robô da Nota de Consumo para um atendimento."""
    from . import nota_consumo
    at = nota_consumo.atendimento(id_atendimento)
    if not at:
        return False, "Atendimento não encontrado.", ""
    if texto(at.get("aghu_consumo_status")) == "lancada":
        return False, "A nota de consumo deste paciente já está marcada como lançada no AGHU.", ""
    if not [i for i in nota_consumo.itens(id_atendimento) if i["codigo_aghu"]]:
        return False, "Nenhum material com código AGHU foi utilizado neste paciente.", ""
    chave = f"consumo:{at['id_atendimento']}"
    with _trava:
        _limpar_antigas()
        for s in _sessoes.values():
            if s.chave == chave and s.thread.is_alive():
                if s.usuario == usuario:
                    return True, "Continuando o lançamento que já estava aberto.", s.id
                return False, f"{s.nome} já está lançando a nota de consumo deste paciente agora.", ""
        if sum(1 for s in _sessoes.values() if s.thread.is_alive()) >= MAX_SIMULTANEOS:
            return False, (f"Já há {MAX_SIMULTANEOS} lançamentos no AGHU abertos no servidor. "
                           "Espere um terminar e tente de novo."), ""
        s = Sessao(chave, texto(at["prontuario"]), usuario, nome, largura, altura, tipo="consumo")
        _sessoes[s.id] = s
    nota_consumo.iniciar(at["id_atendimento"], usuario)
    s.thread.start()
    log.info(f"robô do AGHU (servidor) iniciado para a nota de consumo do prontuário {at['prontuario']}", usuario)
    return True, "Robô iniciado.", s.id


def buscar(sessao: str, usuario: str, admin: bool = False) -> "Sessao | None":
    s = _sessoes.get(texto(sessao))
    if not s:
        return None
    if s.usuario != usuario and not admin:
        return None
    return s
