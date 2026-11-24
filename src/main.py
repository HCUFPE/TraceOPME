from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

from .config import settings  # noqa: E402  (valida as configurações na subida)
from .resources.database import DatabaseManager, Base  # noqa: E402
from .models import audit_log, refresh_token  # noqa: E402,F401  (registra as tabelas no Base)
from .dependencies import get_opme_provider  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")

    # Initialize AGHU DB Manager and store in app.state (opcional no TraceOPME)
    aghu_dsn = os.getenv("POSTGRES_DSN")
    if aghu_dsn and "usuario_exemplo" not in aghu_dsn:
        app.state.aghu_db = DatabaseManager(aghu_dsn)
        print("AGHU PostgreSQL connection pool initialized.")
    else:
        print("WARNING: POSTGRES_DSN not found. Skipping AGHU DB initialization.")

    # Initialize App DB Manager (SQLite) and store in app.state
    app_dsn = os.getenv("SQLITE_DSN") or os.getenv("APP_DB_URL") or "sqlite+aiosqlite:///data/app.db"
    os.makedirs("data", exist_ok=True)
    app.state.app_db = DatabaseManager(app_dsn)
    print(f"App SQLite connection pool initialized ({app_dsn}).")

    # Create tables for App DB (if they don't exist) - for development only, Alembic handles this in production
    async with app.state.app_db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("App SQLite tables checked/created.")

    # Banco de rastreabilidade do TraceOPME (opme.db): estrutura, migrações,
    # cópia de segurança do dia e reconciliação das caixas.
    provider = get_opme_provider("SQLITE")()
    await run_in_threadpool(provider.inicializar)
    app.state.opme_provider = provider
    print(f"TraceOPME database ready ({settings.OPME_DB_PATH}).")

    # nov/2026: rotina diária da agenda de procedimentos (Metabase).
    tarefa_agenda = None
    from .providers.implementations.opme.services import agenda_metabase
    if settings.AGENDA_AUTOMATICA and agenda_metabase.configurada():
        import asyncio
        tarefa_agenda = asyncio.create_task(agenda_metabase.rotina())
        print(f"Agenda automática ligada: {', '.join(agenda_metabase.horarios())} (dias {agenda_metabase.dias()}).")
    elif settings.AGENDA_AUTOMATICA:
        print("WARNING: AGENDA_AUTOMATICA=1, mas falta METABASE_USUARIO/METABASE_SENHA no .env.")

    # v18.4: cópia de segurança diária (no horário BACKUP_HORA) e cópia fora do servidor.
    import asyncio as _asyncio
    from .providers.implementations.opme.services import backup as _backup
    tarefa_backup = _asyncio.create_task(_backup.rotina())
    print(f"Backup diário ligado: {_backup.hora_programada()} · "
          f"pasta externa: {_backup.pasta_externa() or 'NÃO CONFIGURADA (BACKUP_PASTA_EXTERNA)'}")
    if not _backup.pasta_externa():
        # v18.4.5: aviso também no log, para não passar despercebido em produção.
        from .providers.implementations.opme import log as _log_opme
        _log_opme.aviso("ATENÇÃO: BACKUP_PASTA_EXTERNA não configurada — não há cópia do banco fora do servidor.")

    yield

    tarefa_backup.cancel()
    if tarefa_agenda:
        tarefa_agenda.cancel()

    # Shutdown
    print("Shutting down...")
    if hasattr(app.state, 'aghu_db') and app.state.aghu_db:
        await app.state.aghu_db.close_connection()
        print("AGHU PostgreSQL connection pool closed.")
    if hasattr(app.state, 'app_db') and app.state.app_db:
        await app.state.app_db.close_connection()
        print("App SQLite connection pool closed.")

from .version import VERSION, APP_NAME  # noqa: E402

app = FastAPI(
    title=APP_NAME,
    description="TraceOPME — rastreabilidade de OPME do almoxarifado ao paciente (HC-UFPE). "
                "API REST FastAPI + Vue 3 SPA no padrão do Framework SETISD.",
    version=VERSION,
    swagger_ui_parameters={"persistAuthorization": True},
    lifespan=lifespan,
)

# Configuração de CORS (Cross-Origin Resource Sharing)
raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de Cabeçalhos de Segurança HTTP (Security Headers)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

# Handler Global para Padronizar Erros de Validação (Pydantic / FastAPI) no formato {"detail": "..."}
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = exc.errors()
    if errors:
        first_err = errors[0]
        field = first_err.get("loc", [])[-1] if first_err.get("loc") else "campo"
        msg = first_err.get("msg", "Valor inválido")
        detail_msg = f"Erro de validação no campo '{field}': {msg}"
    else:
        detail_msg = "Dados de requisição inválidos."

    return JSONResponse(
        status_code=400,
        content={"detail": detail_msg}
    )


@app.exception_handler(Exception)
async def falha_inesperada(request: Request, exc: Exception):
    """Nada de stack trace na tela: o detalhe vai para o log técnico (logs/opme.log)."""
    from .providers.implementations.opme import log
    log.erro(f"falha ao processar {request.method} {request.url.path}", "", exc)
    return JSONResponse(status_code=500, content={
        "detail": ("Algo deu errado. A falha foi registrada no log do sistema e nenhum dado foi "
                   "gravado pela metade. Tente novamente; se continuar, mostre ao suporte o horário exato."),
    })


# Serve o frontend Vue 3 empacotado (se o build existir)
assets_dir = os.path.join("src", "static", "dist", "assets")
static_dir = os.path.join("src", "static", "dist")

if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Roteadores da API
from .routers import (  # noqa: E402
    admin, admin_opme, chamados, robo_aghu, almoxarifado, auth, bipagem, consignados, consultas, devolucoes,
    dispensacoes, farmacia, health, indicadores, inventario, painel, perfil, procedimentos,
    sala_procedimento, monitoramento, qg,
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(perfil.router)
app.include_router(painel.router)
app.include_router(bipagem.router)
app.include_router(almoxarifado.router)
app.include_router(farmacia.router)
app.include_router(devolucoes.router)
app.include_router(dispensacoes.router)
app.include_router(procedimentos.router)
app.include_router(sala_procedimento.router)
app.include_router(consignados.router)
app.include_router(consultas.router)
app.include_router(inventario.router)
app.include_router(indicadores.router)
app.include_router(admin_opme.router)
app.include_router(chamados.router)
app.include_router(robo_aghu.router)
app.include_router(monitoramento.router)
app.include_router(qg.router)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """
    Serve o arquivo index.html para todas as rotas que não são da API ou arquivos estáticos.
    Isso é necessário para que o roteamento do Vue (SPA) funcione.
    """
    # Se a rota começa com 'api', deixa o roteador do FastAPI lidar
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API route not found")

    # Arquivos públicos do build (logo, favicon, modelo de planilha...)
    if full_path and "/" not in full_path and ".." not in full_path:
        arquivo = os.path.join(static_dir, full_path)
        if os.path.isfile(arquivo):
            return FileResponse(arquivo)

    index_path = os.path.join("src", "static", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Frontend build not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
