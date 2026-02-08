"""
Главный файл приложения FastAPI + Telegram Bot (SaaS версия)
"""
import os
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uuid

from app.database.session import init_db, drop_all_tables, engine, sync_engine, Base
from app.api.endpoints import chat, auth, admin_users, admin_tenants, admin_diagnostics, admin_recovery, whatsapp_webhook, chatflow_webhook, me, leads_v2, pipelines, tasks, events, notifications, admin_import, admin_reports, admin_auto_assign, admin_universal, lead_categories, leads, worker_health, tenant_stages
from app.services.telegram_service import stop_bot
from app.admin import setup_admin

# ВАЖНО: Импортируем модели, чтобы SQLAlchemy их зарегистрировал в Base.metadata
# Без этого импорта таблицы не будут созданы!
from app.database.models import (
    User, BotUser, Message, Lead, LeadComment, LeadEvent, AutoAssignRule, Tenant, TenantUser, WhatsAppAccount,
    TenantIntegration, TenantPipelineMapping, TenantFieldMapping, LeadCategory, TenantStage,
    Conversation, ConversationMessage, ChatMute, ChatAIState,
    Pipeline, PipelineStage, LeadTask, AIChatMute, AuditLog, Notification
)
from app.api.deps import get_db
from app.api.endpoints import auth as auth_endpoints
from app.schemas.auth import Token


def _parse_cors_origins(raw: str | None) -> list[str]:
    """CORS_ORIGINS: split by comma, trim spaces, ignore empty."""
    if raw is None:
        return []
    s = (raw or "").strip()
    if not s:
        return []
    return [o.strip() for o in s.split(",") if o.strip()]


# Lifespan event handler для FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    print("[*] Zapusk prilozheniya (SaaS versiya)...")
    
    from app.core.config import get_settings
    settings = get_settings()
    
    # Очистка БД при разработке
    if settings.dev_mode.upper() == "TRUE":
        print("[DEV] Rezim razrabotki - ochistka bazy dannyh...")
        try:
            await drop_all_tables()
            print("[DEV] Tablicy udaleny")
        except Exception as e:
            print(f"[DEV] Oshibka ochistki tablic: {type(e).__name__}")
    
    # Инициализация БД
    print("[*] Initializaciya PostgreSQL...")
    await init_db()
    
    # Telegram бот готов для отправки уведомлений
    print("[*] Telegram bot gotov dlya otpravki uvedomleniy")
    
    # Proof: list API routes (POST /api/auth/login must appear)
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods") and route.path and route.path.startswith("/api/"):
            for method in sorted(route.methods or set()):
                if method != "HEAD":
                    print(f"[ROUTES] {method} {route.path}")
    
    print("[OK] Prilozhenie zapushcheno!")
    print(f"[OK] Kompaniya: {settings.app_name}")
    print(f"[OK] JWT Auth: ENABLED")
    
    yield
    
    # Shutdown
    print("[*] Ostanovka prilozheniya...")
    await stop_bot()
    print("[*] Prilozhenie ostanovleno")


# Создание приложения FastAPI (redirect_slashes=False so POST /api/auth/login is not redirected to GET)
app = FastAPI(
    title="BuildCRM API",
    description="Многопользовательская платформа ИИ-менеджеров по продажам. Документация и тесты: /docs. QA-панель: /api/admin/diagnostics/ui (только admin).",
    version="2.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Config and CORS — applied BEFORE routers so CORS runs on every request
from app.core.config import get_settings
_settings = get_settings()

# CORS: exact origins + regex for Vercel preview. Applied to SAME app that includes routers; middleware BEFORE include_router.
_origins_list = _parse_cors_origins(_settings.cors_origins)
if not _origins_list:
    _origins_list = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://buildcrm-pwa.vercel.app",
    ]
if "https://app.chatflow.kz" not in _origins_list:
    _origins_list = list(_origins_list) + ["https://app.chatflow.kz"]
_CORS_ORIGIN_REGEX = r"^https://.*\.vercel\.app$"
_CORS_ALLOW_METHODS = ["*"]
_CORS_ALLOW_HEADERS = ["*"]
print(f"[CORS] Allowed origins (final allowlist): {_origins_list}")
print(f"[CORS] allow_origin_regex: {_CORS_ORIGIN_REGEX}")

app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.secret_key,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=_CORS_ALLOW_METHODS,
    allow_headers=_CORS_ALLOW_HEADERS,
    expose_headers=["*"],
)


class _RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate and attach request_id to all requests."""
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class _LogOriginMiddleware(BaseHTTPMiddleware):
    """Log request Origin for /api/* so Render logs show exact origin seen."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin") or "(none)"
            request_id = getattr(request.state, "request_id", "unknown")
            print(f"[{request_id}] Request: {request.method} {request.url.path} | Origin: {origin!r}")
        return await call_next(request)


app.add_middleware(_RequestIDMiddleware)
app.add_middleware(_LogOriginMiddleware)


# Global exception handler to ensure CORS headers are always present
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return JSON with CORS headers."""
    import traceback
    from app.api.error_handler import APIError, get_request_id
    
    origin = request.headers.get("origin", "")
    request_id = get_request_id(request)
    
    # Log the error with request_id
    print(f"[{request_id}] [ERROR] Unhandled exception: {type(exc).__name__}: {exc}")
    traceback.print_exc()
    
    # Handle APIError with consistent format
    if isinstance(exc, APIError):
        response = JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        )
    else:
        # Build response for unexpected errors
        response = JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {type(exc).__name__}",
                "request_id": request_id,
            }
        )
    
    # Add CORS headers manually if origin is allowed
    allowed_origins = _origins_list + ["https://buildcrm-pwa.vercel.app"]
    if origin in allowed_origins or (origin and ".vercel.app" in origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response


# Explicit alias for frontend: POST /api/auth/login (form-urlencoded username, password) -> { access_token, token_type }
# Registered BEFORE auth router so this path is guaranteed; reuses same logic (no duplication).
@app.post("/api/auth/login", response_model=Token)
async def login_alias(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    return await auth_endpoints.login(form_data, db)


# Подключение статических файлов
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Роутеры. Теги для Swagger заданы в роутерах/эндпоинтах.
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/api", tags=["Leads"])
app.include_router(me.router, prefix="/api/me", tags=["Me"])
app.include_router(admin_users.router, prefix="/api/admin", tags=["Users Admin"])
app.include_router(admin_tenants.router, prefix="/api/admin", tags=["Tenants Admin"])
app.include_router(admin_diagnostics.router, prefix="/api/admin", tags=["Admin Diagnostics"])
app.include_router(admin_recovery.router, prefix="/api/admin", tags=["Admin Recovery"])
app.include_router(admin_import.router, prefix="/api/admin", tags=["Import"])
app.include_router(admin_reports.router, prefix="/api/admin", tags=["Reports"])
app.include_router(admin_auto_assign.router, prefix="/api/admin", tags=["Auto Assign"])
app.include_router(admin_universal.router, prefix="/api/admin", tags=["Universal Admin"])
app.include_router(lead_categories.router, prefix="/api", tags=["Lead Categories"])
app.include_router(admin_universal.integrations_router, prefix="/api/integrations", tags=["Integrations"])
app.include_router(whatsapp_webhook.router, prefix="/api/whatsapp", tags=["WhatsApp Webhook"])
app.include_router(chatflow_webhook.router, prefix="/api/chatflow", tags=["ChatFlow Webhook"])
app.include_router(leads_v2.router, prefix="/api/v2", tags=["CRM v2"])
app.include_router(pipelines.router, prefix="/api", tags=["Pipelines"])
app.include_router(tasks.router, prefix="/api", tags=["Tasks"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
app.include_router(leads.router, prefix="/api", tags=["Leads"])  # Phase E: Handoff endpoint
app.include_router(worker_health.router, prefix="/api", tags=["Worker Health"])  # Production monitoring
app.include_router(tenant_stages.router, prefix="/api", tags=["Tenant Stages"])  # Owner-managed pipelines

# Подключение админ-панели (используем СИНХРОННЫЙ engine!)
setup_admin(app, sync_engine)


# Кастомный Swagger UI: токен не слетает, список компактный
from fastapi.openapi.docs import get_swagger_ui_html
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Swagger UI",
        swagger_ui_parameters={
            "docExpansion": "none",
            "defaultModelsExpandDepth": 1,
            "persistAuthorization": True,
        },
    )


@app.get("/", include_in_schema=False)
async def root():
    """Главная страница - веб-интерфейс чата для клиентов"""
    return FileResponse("app/static/index.html")


@app.get("/health")
async def health_check():
    """Health check эндпоинт (root)"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "database": "PostgreSQL",
        "auth": "JWT",
        "admin_panel": "/admin"
    }


@app.get("/api/health")
async def api_health():
    """Health check для API (без auth, для CORS/preflight проверки)"""
    return {"ok": True, "status": "healthy"}


@app.get("/api/debug/cors", include_in_schema=False)
async def debug_cors(request: Request):
    """TEMP: CORS diagnostics. Remove or protect after fix."""
    import re
    origin = request.headers.get("origin") or "(none)"
    allowed_origins = list(_origins_list)
    in_list = origin in allowed_origins if origin != "(none)" else False
    regex_ok = bool(re.match(_CORS_ORIGIN_REGEX, origin)) if origin != "(none)" else False
    origin_allowed = in_list or regex_ok
    return {
        "origin": origin,
        "allowedOrigins": allowed_origins,
        "originAllowed": origin_allowed,
        "request_origin": origin,
        "allowed_origins": allowed_origins,
        "origin_allowed": origin_allowed,
    }


@app.get("/api/debug/auth", summary="Debug auth token", tags=["Debug"])
async def debug_auth(request: Request):
    """
    Debug endpoint to verify if Authorization header is being sent correctly.
    
    This endpoint does NOT require auth - it just reports what auth info was received.
    Useful for debugging "Not authenticated" errors from frontend.
    """
    from app.core.security import decode_access_token
    
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    
    result = {
        "ok": True,
        "auth_header_present": bool(auth_header),
        "auth_header_value": None,
        "token_extracted": False,
        "token_valid": False,
        "token_email": None,
        "error": None,
    }
    
    if not auth_header:
        result["error"] = "No Authorization header found"
        return result
    
    # Check format
    if not auth_header.startswith("Bearer "):
        result["auth_header_value"] = auth_header[:20] + "..." if len(auth_header) > 20 else auth_header
        result["error"] = "Authorization header must start with 'Bearer '"
        return result
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    result["token_extracted"] = True
    result["auth_header_value"] = f"Bearer {token[:10]}...{token[-5:]}" if len(token) > 15 else f"Bearer {token}"
    
    # Try to decode
    try:
        email = decode_access_token(token)
        if email:
            result["token_valid"] = True
            result["token_email"] = email
        else:
            result["error"] = "Token decode returned None (invalid or expired)"
    except Exception as e:
        result["error"] = f"Token decode error: {type(e).__name__}"
    
    return result


@app.post("/api/debug/auth", summary="Debug auth token (POST)", tags=["Debug"])
async def debug_auth_post(request: Request):
    """Same as GET but allows POST (for preflight testing)."""
    return await debug_auth(request)


def _collect_api_routes():
    """Routes starting with /api/auth or /api/leads (for diagnostics)."""
    out = []
    for route in app.routes:
        if not hasattr(route, "path") or not route.path:
            continue
        if not (route.path.startswith("/api/auth") or route.path.startswith("/api/leads")):
            continue
        methods = sorted(route.methods or set()) if hasattr(route, "methods") else []
        out.append({"path": route.path, "methods": methods})
    return out


@app.get("/api/debug/routes", include_in_schema=False)
async def debug_routes():
    """TEMP: List /api/auth and /api/leads routes. Only when DEBUG_ROUTES=true."""
    if os.environ.get("DEBUG_ROUTES", "").upper() != "TRUE":
        return {"enabled": False, "message": "Set DEBUG_ROUTES=true to enable"}
    return {"enabled": True, "routes": _collect_api_routes()}


if __name__ == "__main__":
    import uvicorn
    import socket
    
    # Получаем локальный IP адрес
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print("""
    ============================================================
    
            AI SALES MANAGER - SaaS Platform
            Multi-tenant Architecture
            PostgreSQL + JWT Auth
    
    ============================================================
    """)
    
    print(f"\n[*] Server dostupnen po adresam:")
    print(f"    - Localhost:        http://localhost:8000")
    print(f"    - Local Network:    http://{local_ip}:8000")
    print(f"    - Mobile (Wi-Fi):   http://{local_ip}:8000")
    print(f"\n[*] API Documentation:  http://{local_ip}:8000/docs")
    print(f"[*] Health Check:       http://{local_ip}:8000/health\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # Доступен из любой точки сети
        port=8000,
        reload=True
    )
