"""Cliente de paridade com a versão 17 (só para os testes).

A suíte original do TraceOPME v17 (489 verificações) conversava com o servidor
antigo, que devolvia HTML pronto. Para reaproveitá-la inteira, este cliente
fala com a API nova do framework (``/api/...``, JWT, envelope JSON) e, quando a
API devolve os dados de uma tela, **renderiza o template Jinja original da v17
com esses dados**. Assim cada verificação antiga ("a tela mostra X") passa a
provar que a API entrega tudo o que a tela da v17 precisava — o contrato de
dados que as views Vue do frontend consomem.

Os templates em ``templates_v17/`` existem apenas para este fim: a aplicação
não usa Jinja; a interface é a SPA Vue 3 em ``frontend/``.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

PASTA_TEMPLATES = Path(__file__).resolve().parent / "templates_v17"

# Rotas JSON que já começavam com /api na v17 (sem prefixo de módulo).
APIS_RAIZ = ("/api/bipar", "/api/excluir-uso", "/api/selecao-manual", "/api/ciencia-entrega",
             "/api/desfazer", "/api/abrir-entrega")


def _ambiente() -> Environment:
    from src.providers.implementations.opme.config import (
        APP_SUBTITLE, APP_TITLE, GRADE_DAS_CAIXAS, ORGANIZACAO, ROTULO_ESPECIALIDADE,
        UNIDADES_ATIVAS, cor_unidade, rotulo_unidade,
    )
    from src.providers.implementations.opme.domain import ESTADOS, OPERACOES, cor_de, local_de, rotulo
    from src.providers.implementations.opme.security import MODULOS, rotulo_papel
    from src.providers.implementations.opme.services.alertas import itens as itens_alerta
    from src.providers.implementations.opme.services.relatorios import ROTULO_TIPO
    from src.providers.implementations.opme.utils import data_br, data_hora_br, hoje_iso, moeda

    env = Environment(loader=FileSystemLoader(str(PASTA_TEMPLATES)),
                      autoescape=select_autoescape(["html"]))
    env.filters["data_br"] = data_br
    env.filters["data_hora_br"] = data_hora_br
    env.filters["moeda"] = moeda

    def especialidade(valor) -> str:
        v = str(valor or "")
        return ROTULO_ESPECIALIDADE.get(v.upper(), v.title())

    env.filters["especialidade"] = especialidade
    env.globals.update(
        APP_TITLE=APP_TITLE, APP_SUBTITLE=APP_SUBTITLE, ORGANIZACAO=ORGANIZACAO,
        ESTADOS=ESTADOS, OPERACOES=OPERACOES, MODULOS=MODULOS,
        rotulo_status=rotulo, cor_status=cor_de, local_status=local_de,
        rotulo_papel=rotulo_papel, rotulo_unidade=rotulo_unidade, cor_unidade=cor_unidade,
        itens_alerta=itens_alerta, UNIDADES=UNIDADES_ATIVAS, hoje=hoje_iso,
        VERSAO_ESTATICA="0", GRADE_ATIVA=GRADE_DAS_CAIXAS,
        rotulo_evento=lambda tipo: ROTULO_TIPO.get(tipo, str(tipo or "").replace("_", " ").capitalize()),
    )
    return env


class RespostaLegada:
    def __init__(self, status_code: int, text: str = "", headers: dict | None = None,
                 content: bytes | None = None, caminho: str = "/", corpo_json=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = content if content is not None else text.encode("utf-8")
        self.url = SimpleNamespace(path=caminho)
        self._json = corpo_json

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self.text)


class ClienteLegado:
    """Imita o ``TestClient`` da v17 sobre a API do framework."""

    def __init__(self, cliente):
        self.c = cliente
        self.token = ""
        self.usuario: dict = {}
        self.sessao: dict = {}
        self.aviso_pendente: dict | None = None
        self.env = _ambiente()

    # ------------------------------------------------------------------
    def _cabecalhos(self, pagina: str = "/") -> dict:
        h = {"X-Pagina-Atual": pagina}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.sessao:
            h["X-Sessao"] = base64.b64encode(json.dumps(self.sessao).encode()).decode()
        return h

    @staticmethod
    def _api(caminho: str) -> str:
        if caminho.startswith(APIS_RAIZ):
            return caminho
        if caminho.startswith("/static/"):
            return "/" + caminho[len("/static/"):]
        return "/api" + caminho

    def _render(self, tela: str, dados: dict, caminho: str, status: int = 200) -> RespostaLegada:
        from src.providers.implementations.opme.security import modulos_do_papel
        contexto = dict(dados)
        contexto.setdefault("usuario", self.usuario)
        contexto.setdefault("modulos", modulos_do_papel(self.usuario.get("papel", "")))
        contexto["aviso"] = self.aviso_pendente
        self.aviso_pendente = None
        partes = urlsplit(caminho)
        contexto["request"] = SimpleNamespace(
            url=SimpleNamespace(path=partes.path, query=partes.query),
            query_params={}, session=self.sessao)
        html = self.env.get_template(tela).render(**contexto)
        return RespostaLegada(status, html, {"content-type": "text/html"}, caminho=partes.path)

    def _tratar(self, r, caminho: str, follow_redirects: bool) -> RespostaLegada:
        tipo = r.headers.get("content-type", "")
        if r.status_code >= 400 and "application/json" in tipo:
            corpo = r.json()
            if r.status_code == 404:
                return RespostaLegada(404, json.dumps(corpo), dict(r.headers), caminho=caminho)
            return RespostaLegada(r.status_code, json.dumps(corpo), dict(r.headers), caminho=caminho,
                                  corpo_json=corpo)
        if "application/json" not in tipo:
            return RespostaLegada(r.status_code, r.text if "text" in tipo else "", dict(r.headers),
                                  content=r.content, caminho=caminho)
        corpo = r.json()
        if not isinstance(corpo, dict) or not ({"tela", "redirecionar", "aviso", "sessao"} & set(corpo)):
            return RespostaLegada(r.status_code, r.text, dict(r.headers), caminho=caminho, corpo_json=corpo)
        if corpo.get("sessao"):
            self.sessao.update(corpo["sessao"])
        if corpo.get("aviso"):
            self.aviso_pendente = corpo["aviso"]
        if "tela" in corpo:
            return self._render(corpo["tela"], corpo.get("dados") or {}, caminho, corpo.get("status", 200))
        if "redirecionar" in corpo:
            destino = corpo["redirecionar"]
            if not follow_redirects:
                return RespostaLegada(303, "", {"location": destino}, caminho=caminho)
            return self.get(destino.split("#")[0], follow_redirects=True)
        return RespostaLegada(r.status_code, r.text, dict(r.headers), caminho=caminho, corpo_json=corpo)

    # ------------------------------------------------------------------
    def get(self, caminho: str, params: dict | None = None, follow_redirects: bool = True) -> RespostaLegada:
        if params:
            caminho = caminho + ("&" if "?" in caminho else "?") + urlencode(params)
        r = self.c.get(self._api(caminho), headers=self._cabecalhos(caminho))
        return self._tratar(r, caminho, follow_redirects)

    def post(self, caminho: str, data: dict | None = None, json: dict | None = None,  # noqa: A002
             files: dict | None = None, follow_redirects: bool = True) -> RespostaLegada:
        if caminho == "/login":
            r = self.c.post("/api/login", data={"username": data.get("username"),
                                                "password": data.get("senha")})
            if r.status_code == 200:
                self.token = r.json()["access_token"]
                self.usuario = self.c.get("/api/users/me", headers=self._cabecalhos()).json()
                return RespostaLegada(303, "", {"location": "/"}, caminho="/login")
            return RespostaLegada(200, r.text, caminho="/login")
        kwargs: dict = {"headers": self._cabecalhos(caminho)}
        if json is not None:
            kwargs["json"] = json
        else:
            kwargs["data"] = data or {}
            if files:
                kwargs["files"] = dict(files)
        r = self.c.post(self._api(caminho), **kwargs)
        return self._tratar(r, caminho, follow_redirects)
