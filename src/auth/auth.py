import os
import jwt
from ldap3 import Server, Connection, ALL, SUBTREE, SIMPLE
import re
import secrets
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..resources.database import get_app_db_session
from ..models.refresh_token import RefreshToken

load_dotenv()

# --- Configurações --- 
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", 10))
REFRESH_TOKEN_EXP_DAYS = int(os.getenv("REFRESH_TOKEN_EXP_DAYS", 30))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

# --- Interface e Implementações de Provedor de Autenticação ---

class AuthProviderInterface(ABC):
    """Interface para provedores de autenticação."""
    @abstractmethod
    def authenticate_user(self, username, password) -> dict:
        pass

    @abstractmethod
    def search_user(self, username: str) -> dict:
        pass

class MockAuthProvider(AuthProviderInterface):
    """Provedor para desenvolvimento offline / uso sem AD (modo "local").

    No TraceOPME, sem AD configurado, a senha de cada pessoa é a senha LOCAL
    guardada (com hash PBKDF2) na tabela ``usuarios`` do opme.db — o mesmo
    comportamento da versão 17. A conferência da senha, a trava por tentativas
    e a situação da conta ficam em ``services/usuarios.autenticar``.
    """
    def authenticate_user(self, username, password) -> dict:
        from ..providers.implementations.opme.services import usuarios
        ok, resultado = usuarios.autenticar(username, password or "")
        if not ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=resultado)
        return {
            "username": resultado["username"],
            "displayName": [resultado["nome"]],
            "groups": [],
            "email": [],
            "department": [resultado.get("setor") or ""],
        }

    def search_user(self, username: str) -> dict:
        """Busca simulada de usuário no AD para desenvolvimento/teste."""
        clean_username = username.strip().lower()
        mock_users = {
            "admin": {
                "exists": True,
                "username": "admin",
                "displayName": "Administrador do Sistema",
                "email": "admin@ebserh.gov.br",
                "department": "Escritório de Processos / HC-UFPE"
            },
            "joao.silva": {
                "exists": True,
                "username": "joao.silva",
                "displayName": "João da Silva",
                "email": "joao.silva@ebserh.gov.br",
                "department": "UTI Adulto / HC-UFPE"
            },
            "maria.souza": {
                "exists": True,
                "username": "maria.souza",
                "displayName": "Maria Souza",
                "email": "maria.souza@ebserh.gov.br",
                "department": "Bloco Cirúrgico / HC-UFPE"
            },
            "gestor.unidade": {
                "exists": True,
                "username": "gestor.unidade",
                "displayName": "Gestor da Unidade",
                "email": "gestor.unidade@ebserh.gov.br",
                "department": "Diretoria de Enfermagem / HC-UFPE"
            },
            "medico.exemplo": {
                "exists": True,
                "username": "medico.exemplo",
                "displayName": "Médico do Setor",
                "email": "medico.exemplo@ebserh.gov.br",
                "department": "Clínica Médica / HC-UFPE"
            },
            "enfermeiro.exemplo": {
                "exists": True,
                "username": "enfermeiro.exemplo",
                "displayName": "Enfermeiro do Setor",
                "email": "enfermeiro.exemplo@ebserh.gov.br",
                "department": "UTI Neonatal / HC-UFPE"
            },
            "farmaceutico.exemplo": {
                "exists": True,
                "username": "farmaceutico.exemplo",
                "displayName": "Farmacêutico do Setor",
                "email": "farmaceutico.exemplo@ebserh.gov.br",
                "department": "Farmácia Hospitalar / HC-UFPE"
            }
        }

        if clean_username in mock_users:
            return mock_users[clean_username]
        
        # Se for um formato 'nome.sobrenome', gera um mock dinâmico amigável
        if "." in clean_username:
            parts = clean_username.split(".")
            formatted_name = " ".join([p.capitalize() for p in parts])
            return {
                "exists": True,
                "username": clean_username,
                "displayName": formatted_name,
                "email": f"{clean_username}@ebserh.gov.br",
                "department": "Unidade Hospitalar / HC-UFPE"
            }
        
        return {
            "exists": False,
            "username": username,
            "displayName": "",
            "email": "",
            "department": ""
        }

class ActiveDirectoryAuthProvider(AuthProviderInterface):
    """Provedor de autenticação real usando LDAP/Active Directory (ldap3)."""
    def __init__(self):
        self.ad_url = os.getenv("AD_URL")
        self.ad_basedn = os.getenv("AD_BASEDN")
        self.ad_bind_user = os.getenv("AD_BIND_USER")
        self.ad_bind_password = os.getenv("AD_BIND_PASSWORD")
        if not self.ad_url or not self.ad_basedn:
            raise RuntimeError("Active Directory is not configured. Check .env file.")

    def authenticate_user(self, username, password) -> dict:
        """Confere login e senha no AD.

        nov/2026: o que prova a senha é o BIND. Se o bind passa mas a busca dos
        dados da pessoa falha (AD_BASEDN errado, permissão de leitura), o login
        segue com os dados mínimos — antes isso virava "AD indisponível".
        Erros de rede viram 503 com o motivo real (aparece no log e na tela).
        """
        print(f"--- Starting AD Authentication (ldap3) for user: {username} ---")
        url = (self.ad_url or "").strip().strip('"')
        try:
            server = Server(url, get_info=ALL, connect_timeout=10)
            conn = Connection(server, user=f"EBSERHNET\\{username}", password=password,
                              authentication=SIMPLE, check_names=True, raise_exceptions=True,
                              receive_timeout=15)
            conn.bind()
        except Exception as e:
            texto = str(e)
            if "invalidCredentials" in texto or "data 52e" in texto:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            if any(k in texto for k in ("data 532", "data 701", "data 773", "data 775", "data 533")):
                # senha expirada, conta expirada, troca obrigatória, conta bloqueada/desativada no AD
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=f"sem conexão com {url} ({e.__class__.__name__}: {texto[:200]})")

        user_info = {"username": username, "groups": []}
        try:
            search_conn = conn
            if self.ad_bind_user and self.ad_bind_password:
                search_conn = Connection(server, user=self.ad_bind_user, password=self.ad_bind_password,
                                         authentication=SIMPLE, check_names=True, raise_exceptions=True)
                search_conn.bind()
            bases = [(self.ad_basedn or "").strip().strip('"')]
            try:
                padrao = server.info.other.get("defaultNamingContext") if server.info else None
                padrao = padrao[0] if isinstance(padrao, list) and padrao else padrao
                if padrao and padrao not in bases:
                    bases.append(str(padrao))
            except Exception:
                pass
            filtro = f"(&(objectClass=user)(sAMAccountName={username}))"
            entrada = None
            for base in [b for b in bases if b]:
                try:
                    search_conn.search(base, filtro, search_scope=SUBTREE,
                                       attributes=['displayName', 'mail', 'title', 'department', 'givenName',
                                                   'employeeNumber', 'userPrincipalName', 'memberOf'])
                    if search_conn.entries:
                        entrada = search_conn.entries[0]
                        break
                except Exception as e:
                    print(f"AD: busca em '{base}' falhou: {e}")
            if entrada is not None:
                nomes = {'displayName': 'displayName', 'mail': 'email', 'title': 'title',
                         'department': 'department', 'employeeNumber': 'employeeNumber',
                         'givenName': 'givenName', 'userPrincipalName': 'userPrincipalName'}
                for attr in entrada.entry_attributes:
                    valor = entrada[attr].value
                    if attr.lower() == 'memberof':
                        for dn in (valor if isinstance(valor, list) else [valor]):
                            m = re.match(r'CN=([^,]+)', str(dn or ""))
                            if m:
                                user_info['groups'].append(m.group(1))
                    elif attr in nomes:
                        lista = valor if isinstance(valor, list) else [valor]
                        user_info[nomes[attr]] = [str(v) for v in lista if v is not None]
            else:
                print(f"AD: senha conferida, mas não achei os dados de {username} (AD_BASEDN={bases[0]!r}). "
                      "Login segue com dados mínimos.")
            if search_conn is not conn:
                search_conn.unbind()
        except Exception as e:
            print(f"AD: senha conferida, mas a busca de dados falhou: {e}")
        try:
            conn.unbind()
        except Exception:
            pass
        print(f"--- AD Authentication successful for user: {username}. ---")
        return user_info

    def search_user(self, username: str) -> dict:
        """Busca dados de um usuário no AD pelo login (sAMAccountName) sem efetuar login dele."""
        print(f"--- Searching AD User info (ldap3) for: {username} ---")
        try:
            server = Server(self.ad_url, get_info=ALL)
            if self.ad_bind_user and self.ad_bind_password:
                conn = Connection(server, user=self.ad_bind_user, password=self.ad_bind_password, authentication=SIMPLE, check_names=True, raise_exceptions=True)
            else:
                conn = Connection(server, authentication=SIMPLE, check_names=True, raise_exceptions=True)
            
            conn.bind()
            search_filter = f"(&(objectClass=user)(sAMAccountName={username}))"
            conn.search(self.ad_basedn, search_filter, search_scope=SUBTREE, attributes=['displayName', 'mail', 'department', 'title', 'sAMAccountName'])

            if not conn.entries:
                conn.unbind()
                return {
                    "exists": False,
                    "username": username,
                    "displayName": "",
                    "email": "",
                    "department": ""
                }

            entry = conn.entries[0]
            display_name = str(entry.displayName.value) if 'displayName' in entry and entry.displayName.value else username
            email = str(entry.mail.value) if 'mail' in entry and entry.mail.value else ""
            department = str(entry.department.value) if 'department' in entry and entry.department.value else "HC-UFPE / EBSERH"

            conn.unbind()
            return {
                "exists": True,
                "username": username,
                "displayName": display_name,
                "email": email,
                "department": department
            }
        except Exception as e:
            print(f"Error searching AD for user {username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Falha ao consultar Active Directory: {e}"
            )

# --- AuthHandler Principal ---

class AuthHandler:
    def __init__(self):
        # Lógica de troca: decide qual provedor usar na inicialização
        ad_url = os.getenv("AD_URL")
        if ad_url and "ad.domain.local" not in ad_url:
            print("INFO: Using Active Directory authentication.")
            self.provider: AuthProviderInterface = ActiveDirectoryAuthProvider()
            self.modo = "ad"
        else:
            print("WARNING: AD environment variables not found or template default. "
                  "Using local TraceOPME passwords (modo local).")
            self.provider: AuthProviderInterface = MockAuthProvider()
            self.modo = "local"
        self._registrar_validador_de_senha()

    def _registrar_validador_de_senha(self) -> None:
        """Etapa 1 (AD) ligada às regras do TraceOPME.

        Com o AD configurado, toda senha conferida pelo TraceOPME — login e as
        confirmações na hora (entrega à sala, devolução à farmácia, reabertura
        pela supervisão) — passa a ser validada no Active Directory. O papel
        (Etapa 2, RBAC) continua vindo da tabela local ``usuarios``.
        """
        from ..providers.implementations.opme import security
        if self.modo != "ad":
            security.registrar_validador_externo(None)
            return

        def _primeiro(valor) -> str:
            if isinstance(valor, list):
                return str(valor[0]) if valor else ""
            return str(valor or "")

        def validar_no_ad(username: str, senha: str) -> dict | None:
            """Login e senha no AD: dados da pessoa se conferem; None se não conferem."""
            try:
                info = self.provider.authenticate_user(username, senha)
            except HTTPException as erro:
                if erro.status_code == status.HTTP_401_UNAUTHORIZED:
                    return None
                from ..providers.implementations.opme import log
                log.aviso(f"AD indisponível ao conferir senha: {erro.detail}", username)
                raise security.AdIndisponivel(str(erro.detail)) from erro
            return {
                "username": username,
                "nome": _primeiro(info.get("displayName")) or username,
                "email": _primeiro(info.get("email")),
                "setor": _primeiro(info.get("department")),
            }

        security.registrar_validador_externo(validar_no_ad)

    def authenticate_user(self, username, password):
        return self.provider.authenticate_user(username, password)

    def search_ad_user(self, username: str) -> dict:
        return self.provider.search_user(username)

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None):
        to_encode = data.copy()
        if 'username' in to_encode:
            to_encode['sub'] = to_encode['username']
        
        # Use o tempo Unix (timestamp) para garantir serialização JSON
        expire = datetime.utcnow() + (expires_delta or timedelta(hours=JWT_EXP_HOURS))
        to_encode.update({"exp": int(expire.timestamp())})
        
        if not JWT_SECRET:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWT_SECRET not configured")
        return jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")

    async def create_refresh_token(self, user_id: str, groups: list, db: AsyncSession) -> str:
        refresh_token_string = secrets.token_urlsafe(64)
        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXP_DAYS)
        new_refresh_token = RefreshToken(user_id=user_id, token=refresh_token_string, groups=groups, expires_at=expires_at)
        db.add(new_refresh_token)
        await db.commit()
        return refresh_token_string

    async def verify_refresh_token(self, refresh_token: str, db: AsyncSession):
        stmt = select(RefreshToken).where(RefreshToken.token == refresh_token)
        result = await db.execute(stmt)
        token_obj = result.scalar_one_or_none()
        if not token_obj or token_obj.expires_at < datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
        return token_obj

    async def invalidate_refresh_token(self, refresh_token: str, db: AsyncSession):
        stmt = delete(RefreshToken).where(RefreshToken.token == refresh_token)
        await db.execute(stmt)
        await db.commit()

    def decode_token(self, token: str = Depends(oauth2_scheme)):
        try:
            if not JWT_SECRET:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWT_SECRET not configured")
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Instância única que será usada em toda a aplicação
auth_handler = AuthHandler()