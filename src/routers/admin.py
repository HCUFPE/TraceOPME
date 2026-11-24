"""
Administração de acesso (Framework SETISD): validação de usuários no AD e
inclusão direta de usuários no RBAC local do TraceOPME.

As demais telas de administração do TraceOPME (aprovar solicitações, mudar
perfil, catálogo de materiais, backup, diagnóstico...) estão em
``src/routers/admin_opme.py``.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..auth.auth import auth_handler
from ..helpers.audit_helper import registrar_auditoria
from ..helpers.web_helper import obter_usuario_autorizado
from ..providers.implementations.opme.security import PAPEIS
from ..providers.implementations.opme.services import usuarios
from ..resources.database import get_app_db_session

router = APIRouter(prefix="/api", tags=["Admin"])

# Perfil local (RBAC) com acesso à administração.
PAPEL_ADMIN = "admin"


async def verify_admin_group(current_user: dict = Depends(obter_usuario_autorizado)) -> dict:
    """Só o perfil local ``admin`` do TraceOPME administra usuários."""
    if current_user.get("papel") != PAPEL_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")
    return current_user


class ADUserSearchResponse(BaseModel):
    exists: bool
    username: str
    displayName: str
    email: str
    department: str
    ja_cadastrado: bool = False


@router.get("/admin/ad-user-search/{username}", response_model=ADUserSearchResponse)
async def search_ad_user(username: str, current_user: dict = Depends(verify_admin_group)):
    """
    Busca e valida um usuário no Active Directory (ou Mock) pelo login de rede.
    Restrito a administradores do sistema.
    """
    res = await run_in_threadpool(auth_handler.search_ad_user, username)
    ja = await run_in_threadpool(usuarios.buscar, username)
    return ADUserSearchResponse(**res, ja_cadastrado=bool(ja))


class NovoUsuario(BaseModel):
    username: str
    nome: str
    email: str = ""
    setor: str = ""
    papel: str
    senha: str = ""


@router.post("/admin/usuarios")
async def cadastrar_usuario(
    dados: NovoUsuario,
    request: Request,
    current_user: dict = Depends(verify_admin_group),
    db=Depends(get_app_db_session),
):
    """Inclui um usuário no RBAC local depois de "Consultar AD" (nome, e-mail e setor vêm do AD)."""
    if dados.papel not in PAPEIS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Perfil inválido.")
    ok, mensagem = await run_in_threadpool(usuarios.cadastrar_direto, dados.model_dump(),
                                           current_user["username"])
    await registrar_auditoria(
        db=db, usuario=current_user["username"], categoria="SEGURANCA", acao="CADASTRAR_USUARIO",
        recurso=f"usuario:{dados.username.lower()}", dados_anteriores=None,
        dados_novos={"nome": dados.nome, "email": dados.email, "setor": dados.setor,
                     "papel": dados.papel, "ok": ok},
        ip_origem=request.client.host if request.client else None)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mensagem)
    return {"ok": True, "mensagem": mensagem}
