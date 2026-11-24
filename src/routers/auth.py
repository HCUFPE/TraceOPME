# src/routers/auth.py
"""
Autenticação (rotas públicas): login, renovação do token, logout e as
solicitações feitas da tela de login (pedir acesso / pedir nova senha).

Modelo híbrido do Framework SETISD:
  1. Etapa 1 — a senha é conferida no Active Directory (AD_URL configurado) ou,
     sem AD, na senha local do TraceOPME (modo de reserva);
  2. Etapa 2 — o login precisa existir e estar ATIVO na tabela local
     ``usuarios`` (RBAC). É dela que vem o perfil (papel) de acesso.
     nov/2026: com o AD, quem confere no AD mas ainda não tem perfil ganha
     uma solicitação de acesso automática (nome, e-mail e setor do AD) para o
     administrador aprovar ou recusar — o login responde 403 explicando isso.
Ambas as etapas, mais a trava por tentativas erradas, ficam em
``services/usuarios.autenticar`` — a mesma função usada pelas confirmações
com senha (entrega à sala, devolução, reabertura).
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..auth.auth import JWT_EXP_HOURS, REFRESH_TOKEN_EXP_DAYS, auth_handler
from ..helpers.audit_helper import registrar_auditoria
from ..helpers.web_helper import obter_usuario_autorizado
from ..providers.implementations.opme.security import (
    PAPEIS, modo_autenticacao, modulos_do_papel, rotulo_papel,
)
from ..providers.implementations.opme.services import usuarios
from ..resources.database import get_app_db_session

router = APIRouter(prefix="/api", tags=["Authentication"])


def _dados_token(usuario: dict) -> dict:
    """Conteúdo do JWT: identidade + perfil local (RBAC)."""
    return {
        "username": usuario["username"],
        "nome": usuario["nome"],
        "papel": usuario["papel"],
        "setor": usuario.get("setor") or "",
        "groups": [],
    }


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: bool = Form(False),
    db: AsyncSession = Depends(get_app_db_session),
):
    """Entra no sistema. Devolve o JWT de acesso e, com "lembrar de mim", o cookie HttpOnly de renovação."""
    ok, resultado = await run_in_threadpool(usuarios.autenticar, form_data.username, form_data.password,
                                            True)
    if not ok and isinstance(resultado, dict):
        # nov/2026: login válido no AD, sem perfil no TraceOPME → solicitação de
        # acesso registrada com os dados do AD, para o administrador decidir.
        await registrar_auditoria(db=db, usuario=(form_data.username or "").lower(), categoria="SEGURANCA",
                                  acao="SOLICITACAO_ACESSO_AD" if resultado.get("nova") else "LOGIN_AGUARDANDO_APROVACAO",
                                  recurso="auth:login", dados_novos={"motivo": resultado.get("mensagem")},
                                  ip_origem=_ip(request))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"mensagem": resultado.get("mensagem"), "solicitacao_acesso": True})
    if not ok:
        await registrar_auditoria(db=db, usuario=(form_data.username or "").lower(), categoria="SEGURANCA",
                                  acao="LOGIN_RECUSADO", recurso="auth:login",
                                  dados_novos={"motivo": resultado}, ip_origem=_ip(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=resultado)

    access_token_expires = timedelta(minutes=15) if remember_me else timedelta(hours=JWT_EXP_HOURS)
    access_token = auth_handler.create_access_token(data=_dados_token(resultado),
                                                    expires_delta=access_token_expires)
    if remember_me:
        refresh_token = await auth_handler.create_refresh_token(
            user_id=resultado["username"], groups=[], db=db)
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",  # Secure em produção com HTTPS
            max_age=REFRESH_TOKEN_EXP_DAYS * 24 * 60 * 60,
        )
    await registrar_auditoria(db=db, usuario=resultado["username"], categoria="SEGURANCA",
                              acao="LOGIN", recurso=f"usuario:{resultado['username']}",
                              dados_novos={"papel": resultado["papel"], "modo": modo_autenticacao()},
                              ip_origem=_ip(request))
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/token/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_app_db_session)):
    """Renova o token de acesso a partir do cookie HttpOnly (rotação do refresh token)."""
    token_atual = request.cookies.get("refresh_token")
    if not token_atual:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found")

    token_obj = await auth_handler.verify_refresh_token(token_atual, db)
    # Etapa 2 de novo: o acesso precisa continuar ativo no RBAC local.
    registro = await run_in_threadpool(usuarios.buscar, token_obj.user_id)
    if not registro or registro.get("status") != "ativo":
        await auth_handler.invalidate_refresh_token(token_atual, db)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Seu acesso não está ativo no TraceOPME.")

    await auth_handler.invalidate_refresh_token(token_atual, db)
    novo_access = auth_handler.create_access_token(data=_dados_token(registro),
                                                   expires_delta=timedelta(minutes=15))
    novo_refresh = await auth_handler.create_refresh_token(user_id=registro["username"], groups=[], db=db)
    response.set_cookie(
        key="refresh_token",
        value=novo_refresh,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=REFRESH_TOKEN_EXP_DAYS * 24 * 60 * 60,
    )
    return {"access_token": novo_access, "token_type": "bearer"}


@router.post("/logout")
async def logout(response: Response, request: Request, db: AsyncSession = Depends(get_app_db_session)):
    """Sai do sistema: invalida o refresh token e apaga o cookie HttpOnly."""
    token_atual = request.cookies.get("refresh_token")
    if token_atual:
        await auth_handler.invalidate_refresh_token(token_atual, db)
    response.delete_cookie(key="refresh_token", httponly=True, samesite="lax")
    return {"message": "Logged out successfully"}


@router.get("/users/me")
async def read_users_me(usuario: dict = Depends(obter_usuario_autorizado)):
    """Usuário logado, com o perfil (RBAC local) e os módulos que ele acessa."""
    return usuario | {
        "sub": usuario["username"],
        "rotulo_papel": rotulo_papel(usuario["papel"]),
        "modulos": modulos_do_papel(usuario["papel"]),
        "displayName": [usuario["nome"]],
        "givenName": [usuario["nome"].split()[0] if usuario["nome"] else usuario["username"]],
        "department": [usuario.get("setor") or ""],
        "groups": [],
    }


# ---------------------------------------------------------------------------
# Rotas públicas da tela de login (antes: /solicitar-cadastro e /solicitar-senha)
# ---------------------------------------------------------------------------

@router.get("/auth/modo")
async def modo():
    """Como a senha é conferida ('ad' ou 'local') e os perfis que podem ser pedidos."""
    return {
        "modo": modo_autenticacao(),
        "papeis": {k: v[0] for k, v in PAPEIS.items() if k != "admin"},
    }


@router.post("/solicitar-cadastro")
async def solicitar_cadastro(
    request: Request,
    nome: str = Form(""), username: str = Form(""), senha: str = Form(""),
    email: str = Form(""), setor: str = Form(""), papel: str = Form("consulta"),
    db: AsyncSession = Depends(get_app_db_session),
):
    """Pedido de acesso feito na tela de login. Um administrador libera depois."""
    if modo_autenticacao() == "ad" and username:
        # Com o AD, o login pedido precisa existir na rede da Ebserh.
        dados_ad = await run_in_threadpool(auth_handler.search_ad_user, username)
        if not dados_ad.get("exists"):
            return {"ok": False, "mensagem": "Este usuário não existe na rede (AD). Use o seu login de rede."}
        nome = nome or dados_ad.get("displayName", "")
        email = email or dados_ad.get("email", "")
        setor = setor or dados_ad.get("department", "")
    ok, mensagem = await run_in_threadpool(usuarios.solicitar_cadastro, {
        "nome": nome, "username": username, "senha": senha,
        "email": email, "setor": setor, "papel": papel,
    })
    await registrar_auditoria(db=db, usuario=(username or "").lower(), categoria="SEGURANCA",
                              acao="SOLICITAR_CADASTRO", recurso=f"usuario:{(username or '').lower()}",
                              dados_novos={"nome": nome, "papel": papel, "ok": ok}, ip_origem=_ip(request))
    return {"ok": ok, "mensagem": mensagem}


@router.post("/solicitar-senha")
async def solicitar_senha(
    request: Request,
    username: str = Form(""), email: str = Form(""),
    senha: str = Form(""), observacao: str = Form(""),
    db: AsyncSession = Depends(get_app_db_session),
):
    """Pedido de nova senha (modo local). Com o AD, a senha é a da rede."""
    ok, mensagem = await run_in_threadpool(usuarios.solicitar_nova_senha, {
        "username": username, "email": email, "senha": senha, "observacao": observacao,
    })
    await registrar_auditoria(db=db, usuario=(username or "").lower(), categoria="SEGURANCA",
                              acao="SOLICITAR_NOVA_SENHA", recurso=f"usuario:{(username or '').lower()}",
                              dados_novos={"ok": ok}, ip_origem=_ip(request))
    return {"ok": ok, "mensagem": mensagem}
