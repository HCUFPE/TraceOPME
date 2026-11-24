# src/helpers/web_helper.py
"""
Helper de integração HTTP ↔ Controllers do TraceOPME
=====================================================

Os controllers do TraceOPME (``src/controllers/*_controller.py``) recebem um
objeto :class:`Requisicao` em vez do ``Request`` do Starlette. Ele carrega o
que a regra de negócio precisa saber da chamada — quem está logado (já
autorizado pelo RBAC local), os campos enviados pela tela, a escolha de
unidade/farmácia em que a pessoa está trabalhando — e coleta o que o
controller devolve à tela:

* ``render(req, tela, contexto)`` → os dados da tela, em JSON, para a view Vue;
* ``avisar(req, texto, tipo)`` → a mensagem que a tela mostra (sucesso/erro/janela);
* ``redirecionar(url)`` → para qual tela o frontend deve seguir.

A resposta da API tem sempre o mesmo envelope::

    {"tela": "...", "dados": {...}, "aviso": {...}, "redirecionar": "/...", "sessao": {...}}

O frontend Vue (``frontend/src/services/opme.ts``) interpreta esse envelope.
Respostas que já são arquivos (PDF, CSV, PNG) ou JSON de leitura contínua
(bipagem) passam direto, sem envelope.

Este módulo também registra a trilha de auditoria (``audit_logs``) de toda
chamada que altera dados, com usuário, IP, ação e dados enviados.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from fastapi import Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.responses import Response

from ..auth.auth import auth_handler

logger = logging.getLogger("web_helper")

# Campos que nunca vão para a trilha de auditoria.
CAMPOS_SENSIVEIS = {"senha", "senha_responsavel", "senha_supervisao", "senha_atual",
                    "nova_senha", "confirmar", "password"}

# Chaves da "sessão de trabalho" guardada no navegador e devolvida a cada chamada.
CHAVES_SESSAO = ("farmacia", "unidade_farmacia", "unidade_sala")


# =========================================================
# ESTRUTURAS
# =========================================================

class Redirecionamento(Exception):
    """Interrompe o controller e manda a tela seguir para outra URL."""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


@dataclass
class RespostaTela:
    tela: str
    dados: dict
    status: int = 200


@dataclass
class RespostaRedirecionar:
    url: str


class ArquivoEnviado:
    """Arquivo enviado pela tela (já lido na memória)."""

    def __init__(self, filename: str, conteudo: bytes, content_type: str = ""):
        self.filename = filename or ""
        self.content_type = content_type or ""
        self._conteudo = conteudo or b""

    async def read(self) -> bytes:
        """Conteúdo do arquivo (assíncrono, como o ``UploadFile`` do Starlette)."""
        return self._conteudo

    def __bool__(self) -> bool:
        return bool(self.filename or self._conteudo)


class Formulario:
    """Campos enviados pela tela, com a mesma interface do ``FormData`` do Starlette."""

    def __init__(self, pares: Iterable[tuple[str, Any]] = ()):
        self._pares: list[tuple[str, Any]] = list(pares)

    def get(self, chave: str, padrao: Any = None) -> Any:
        valores = self.getlist(chave)
        return valores[-1] if valores else padrao

    def getlist(self, chave: str) -> list[Any]:
        return [v for k, v in self._pares if k == chave]

    def keys(self):
        vistos: list[str] = []
        for k, _ in self._pares:
            if k not in vistos:
                vistos.append(k)
        return vistos

    def items(self):
        return [(k, self.get(k)) for k in self.keys()]

    def __getitem__(self, chave: str) -> Any:
        if chave not in self:
            raise KeyError(chave)
        return self.get(chave)

    def __contains__(self, chave: object) -> bool:
        return any(k == chave for k, _ in self._pares)

    def __iter__(self):
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())


class _Url:
    def __init__(self, path: str, query: str):
        self.path = path
        self.query = query


class _Cabecalhos(dict):
    """Cabeçalhos da chamada. ``referer`` é a tela em que a pessoa estava (SPA)."""

    def get(self, chave: str, padrao: Any = None) -> Any:  # type: ignore[override]
        return super().get(chave.lower(), padrao)


@dataclass
class Requisicao:
    """O que o controller enxerga da chamada HTTP."""

    usuario: dict
    session: dict
    query_params: Any
    headers: _Cabecalhos
    url: _Url
    formulario: Formulario = field(default_factory=Formulario)
    corpo_json: Any = None
    ip: str = ""
    aviso: dict | None = None
    _sessao_inicial: dict = field(default_factory=dict)

    async def form(self) -> Formulario:
        """Campos enviados pela tela (formulário multipart ou JSON)."""
        return self.formulario

    async def json(self) -> Any:
        """Corpo JSON enviado pela tela."""
        return self.corpo_json if self.corpo_json is not None else {}

    # --- atalhos usados pelos routers -----------------------------------
    def campo(self, nome: str, padrao: Any = "") -> Any:
        """Valor de um campo do formulário (o último, se vier repetido)."""
        valor = self.formulario.get(nome, None)
        if valor is None:
            return padrao
        if isinstance(valor, ArquivoEnviado):
            return valor
        return valor if isinstance(valor, str) else str(valor)

    def lista(self, nome: str) -> list[str]:
        """Todos os valores de um campo repetido (ex.: caixas marcadas)."""
        return [str(v) for v in self.formulario.getlist(nome)]

    def arquivo(self, nome: str) -> ArquivoEnviado | None:
        """Arquivo enviado no campo ``nome`` (ou None)."""
        valor = self.formulario.get(nome)
        return valor if isinstance(valor, ArquivoEnviado) and valor else None

    def sessao_alterada(self) -> dict | None:
        atual = {k: self.session.get(k) for k in CHAVES_SESSAO if self.session.get(k) is not None}
        return atual if atual != self._sessao_inicial else None


# =========================================================
# FUNÇÕES USADAS PELOS CONTROLLERS
# =========================================================

def render(request: Requisicao, template: str, contexto: dict | None = None,
           status: int = 200) -> RespostaTela:
    """Devolve os dados de uma tela. ``template`` identifica a view Vue que os exibe."""
    from ..providers.implementations.opme.security import modulos_do_papel

    usuario = request.usuario
    dados: dict = {}
    modulos = modulos_do_papel(usuario["papel"]) if usuario else []
    # v18.7.3: o alerta de solicitações de OPME em aberto é da FARMÁCIA — aparece só nas telas
    # dela (farmácia, dispensação, devolução), nunca na Sala de procedimento, em Procedimentos,
    # na Central das salas ou no QG, mesmo para quem também tem acesso à farmácia.
    if (usuario and "farmacia" in modulos and template.startswith(("farmacia/", "dispensacoes/", "devolucoes/"))):
        try:
            from ..providers.implementations.opme.config import UNIDADES_ATIVAS, rotulo_unidade
            from ..providers.implementations.opme.services.solicitacoes import contar_em_aberto
            # Cada farmácia vê só os pedidos da unidade que ela atende (escolhida na
            # entrada do módulo Farmácia). Sem unidade escolhida, mostra todos.
            un = request.session.get("unidade_farmacia", "")
            un = un if un in UNIDADES_ATIVAS else ""
            dados["pedidos_opme_abertos"] = contar_em_aberto(un)
            dados["pedidos_opme_unidade"] = rotulo_unidade(un) if un else ""
            if not un and dados["pedidos_opme_abertos"]:
                # v18.1: sem a unidade escolhida, o alerta vem separado por farmácia —
                # cada uma vê (e abre) só o que é dela, sem misturar Bloco e Hemodinâmica.
                dados["pedidos_opme_por_unidade"] = [
                    {"unidade": k, "rotulo": rotulo_unidade(k), "n": n,
                     "farmacia": __import__("src.providers.implementations.opme.config",
                                            fromlist=["x"]).rotulo_farmacia(k)}
                    for k in UNIDADES_ATIVAS if (n := contar_em_aberto(k))]
        except Exception:  # o alerta nunca pode derrubar a tela
            dados["pedidos_opme_abertos"] = 0
    dados.update(contexto or {})
    return RespostaTela(template, dados, status)


def avisar(request: Requisicao, texto_mensagem: str, tipo: str = "sucesso",
           acoes: list | None = None) -> None:
    """Mensagem para a tela. ``tipo="janela"`` abre a janela vermelha de bloqueio;
    ``acoes`` são pares (rótulo, link) mostrados como botões nela."""
    aviso: dict = {"texto": texto_mensagem, "tipo": tipo}
    if acoes:
        aviso["acoes"] = [list(a) for a in acoes]
    request.aviso = aviso


def ir_para(url: str) -> RespostaRedirecionar:
    """Manda a tela seguir para ``url`` (rota do frontend)."""
    return RespostaRedirecionar(url)


def redirecionar(url: str) -> RespostaRedirecionar:
    """Sinônimo de :func:`ir_para`."""
    return RespostaRedirecionar(url)


def exigir_login(request: Requisicao) -> dict:
    """Usuário logado (a autenticação já foi feita pela dependência do router)."""
    if not request.usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada.")
    return request.usuario


def exigir_modulo(request: Requisicao, modulo: str) -> dict:
    """RBAC local: o papel do usuário precisa dar acesso ao módulo."""
    from ..providers.implementations.opme.security import pode_acessar

    usuario = exigir_login(request)
    if not pode_acessar(usuario["papel"], modulo):
        raise Redirecionamento("/?sem_permissao=1")
    return usuario


def farmacia_atual(request: Requisicao) -> str:
    """Farmácia em que o usuário está trabalhando agora (Bloco ou Hemodinâmica)."""
    from ..providers.implementations.opme.config import farmacia_valida
    return farmacia_valida(request.session.get("farmacia"))


def definir_farmacia(request: Requisicao, valor: str) -> str:
    from ..providers.implementations.opme.config import farmacia_valida
    escolhida = farmacia_valida(valor)
    request.session["farmacia"] = escolhida
    return escolhida


# =========================================================
# DEPENDÊNCIA: monta a Requisicao a partir da chamada HTTP
# =========================================================

def _ler_sessao(valor: str | None) -> dict:
    if not valor:
        return {}
    try:
        dados = json.loads(base64.b64decode(valor).decode("utf-8"))
        return {k: str(dados[k]) for k in CHAVES_SESSAO if dados.get(k)}
    except Exception:
        return {}


async def obter_usuario_autorizado(payload: dict = Depends(auth_handler.decode_token)) -> dict:
    """Etapa 2 do modelo híbrido: o login do token precisa estar ativo no RBAC local."""
    from ..providers.implementations.opme.services import usuarios

    username = payload.get("sub") or payload.get("username") or ""
    registro = await run_in_threadpool(usuarios.buscar, username)
    if not registro or registro.get("status") != "ativo":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Seu acesso não está ativo no TraceOPME. Fale com o administrador.")
    return {"username": registro["username"], "nome": registro["nome"],
            "papel": registro["papel"], "setor": registro.get("setor") or "",
            "email": registro.get("email") or ""}


async def obter_requisicao(request: Request,
                           usuario: dict = Depends(obter_usuario_autorizado)) -> Requisicao:
    """Dependência FastAPI: transforma a chamada HTTP numa :class:`Requisicao`."""
    sessao = _ler_sessao(request.headers.get("x-sessao"))
    pares: list[tuple[str, Any]] = []
    corpo_json = None
    tipo = request.headers.get("content-type", "")
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if "application/json" in tipo:
            try:
                corpo_json = await request.json()
            except Exception:
                corpo_json = {}
            if isinstance(corpo_json, dict):
                for k, v in corpo_json.items():
                    if isinstance(v, list):
                        pares += [(k, x) for x in v]
                    elif v is not None:
                        pares.append((k, v if isinstance(v, str) else v))
        elif "multipart/form-data" in tipo or "application/x-www-form-urlencoded" in tipo:
            form = await request.form()
            for k, v in form.multi_items():
                if isinstance(v, UploadFile):
                    pares.append((k, ArquivoEnviado(v.filename or "", await v.read(),
                                                    v.content_type or "")))
                else:
                    pares.append((k, v))
    caminho = request.url.path
    if caminho.startswith("/api/"):
        caminho = caminho[4:]
    cabecalhos = _Cabecalhos({k.lower(): v for k, v in request.headers.items()})
    if request.headers.get("x-pagina-atual"):
        cabecalhos["referer"] = request.headers["x-pagina-atual"]
    sessao_trabalho = dict(sessao)
    sessao_trabalho["usuario"] = usuario
    return Requisicao(
        usuario=usuario, session=sessao_trabalho, query_params=request.query_params,
        headers=cabecalhos, url=_Url(caminho, request.url.query),
        formulario=Formulario(pares), corpo_json=corpo_json,
        ip=(request.client.host if request.client else ""),
        _sessao_inicial=dict(sessao),
    )


# =========================================================
# EXECUÇÃO DO CONTROLLER + ENVELOPE + AUDITORIA
# =========================================================

def _limpar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: ("***" if k in CAMPOS_SENSIVEIS else _limpar(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_limpar(v) for v in valor]
    if isinstance(valor, ArquivoEnviado):
        return f"<arquivo {valor.filename}>"
    if isinstance(valor, str) and valor.startswith("data:image/"):
        return f"<imagem {len(valor) // 1024} KB>"  # nov/2026: fotos não vão para a auditoria
    return valor


def _dados_enviados(req: Requisicao, extras: dict) -> dict:
    dados: dict = {}
    for k in req.formulario.keys():
        valores = req.formulario.getlist(k)
        dados[k] = valores if len(valores) > 1 else valores[0]
    dados.update({k: v for k, v in extras.items() if not isinstance(v, (bytes,))})
    return _limpar(jsonable_encoder(dados, custom_encoder={ArquivoEnviado: lambda a: f"<arquivo {a.filename}>"}))


def _categoria(recurso: str) -> str:
    if recurso.startswith("/admin/usuario") or recurso.startswith("/admin/solicitacao") \
            or recurso.startswith("/admin/usuarios"):
        return "SEGURANCA"
    if recurso.startswith("/admin") or recurso.startswith("/indicadores/metas"):
        return "CONFIGURACAO"
    return "NEGOCIO_CLINICO"


async def _auditar(request: Request, req: Requisicao, acao: str, dados_novos: dict,
                   resultado: dict, dados_anteriores: Any = None) -> None:
    """Grava a mutação na tabela unificada ``audit_logs`` (banco interno do framework)."""
    from .audit_helper import registrar_auditoria

    try:
        maker = request.app.state.app_db.async_session_maker
    except AttributeError:
        return
    try:
        async with maker() as sessao:
            await registrar_auditoria(
                db=sessao, usuario=req.usuario.get("username", ""),
                categoria=_categoria(req.url.path), acao=acao, recurso=req.url.path,
                dados_anteriores=dados_anteriores,
                dados_novos={"enviado": dados_novos, "resultado": resultado},
                ip_origem=req.ip)
    except Exception as erro:  # a auditoria nunca derruba a operação já gravada
        logger.error(f"falha ao gravar auditoria de {acao}: {erro}")


def _executar_em_thread(funcao: Callable, *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(funcao):
        return asyncio.run(funcao(*args, **kwargs))
    return funcao(*args, **kwargs)


async def executar(request: Request, req: Requisicao, funcao: Callable, *args: Any,
                   auditar: bool | None = None, dados_anteriores: Any = None,
                   **kwargs: Any) -> Any:
    """Executa o controller fora do *event loop* e devolve a resposta padronizada.

    ``auditar``: por padrão, toda chamada que não é GET entra na trilha de auditoria.
    """
    try:
        resultado = await run_in_threadpool(_executar_em_thread, funcao, req, *args, **kwargs)
    except Redirecionamento as r:
        resultado = RespostaRedirecionar(r.url)
    except HTTPException as e:
        if e.status_code == 303 and e.headers and e.headers.get("Location"):
            resultado = RespostaRedirecionar(e.headers["Location"])
        else:
            raise

    deve_auditar = (request.method != "GET") if auditar is None else auditar

    if isinstance(resultado, Response):
        if deve_auditar:
            corpo: dict = {}
            try:
                if resultado.media_type == "application/json":
                    corpo = json.loads(resultado.body)
                    corpo = {k: corpo.get(k) for k in ("ok", "mensagem") if k in corpo}
            except Exception:
                corpo = {}
            await _auditar(request, req, funcao.__name__, _dados_enviados(req, kwargs),
                           corpo, dados_anteriores)
        return resultado

    envelope: dict = {}
    if isinstance(resultado, RespostaTela):
        envelope["tela"] = resultado.tela
        envelope["dados"] = jsonable_encoder(resultado.dados)
        if resultado.status != 200:
            envelope["status"] = resultado.status
    elif isinstance(resultado, RespostaRedirecionar):
        envelope["redirecionar"] = resultado.url
    elif resultado is not None:
        envelope["dados"] = jsonable_encoder(resultado)
    if req.aviso:
        envelope["aviso"] = req.aviso
    sessao = req.sessao_alterada()
    if sessao is not None:
        envelope["sessao"] = sessao

    if deve_auditar:
        await _auditar(request, req, funcao.__name__, _dados_enviados(req, kwargs),
                       {"aviso": req.aviso, "redirecionar": envelope.get("redirecionar")},
                       dados_anteriores)
    return envelope
