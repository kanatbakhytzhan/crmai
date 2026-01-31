"""
Главный файл приложения FastAPI + Telegram Bot (SaaS версия)
"""
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.database.session import init_db, drop_all_tables, engine, sync_engine, Base
from app.api.endpoints import chat, auth, admin_users
from app.services.telegram_service import stop_bot
from app.admin import setup_admin

# ВАЖНО: Импортируем модели, чтобы SQLAlchemy их зарегистрировал в Base.metadata
# Без этого импорта таблицы не будут созданы!
from app.database.models import User, BotUser, Message, Lead


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
    
    print("[OK] Prilozhenie zapushcheno!")
    print(f"[OK] Kompaniya: {settings.app_name}")
    print(f"[OK] JWT Auth: ENABLED")
    
    yield
    
    # Shutdown
    print("[*] Ostanovka prilozheniya...")
    await stop_bot()
    print("[*] Prilozhenie ostanovleno")


# Создание приложения FastAPI
app = FastAPI(
    title="AI Sales Manager SaaS API",
    description="Многопользовательская платформа ИИ-менеджеров по продажам",
    version="2.0.0",
    lifespan=lifespan
)

# Config and CORS — applied BEFORE routers so CORS runs on every request
from app.core.config import get_settings
_settings = get_settings()

# CORS_ORIGINS: split by comma, trim spaces, ignore empty
_origins_list = _parse_cors_origins(_settings.cors_origins)
if not _origins_list:
    _origins_list = ["https://buildcrm-pwa.vercel.app"]
print(f"[CORS] Final parsed allowed origins: {_origins_list}")

# Middleware order: last added = runs first. We want CORS first, then Session.
# So add Session first, then CORSMiddleware (CORS runs first on request).
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.secret_key,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


class _LogOriginMiddleware(BaseHTTPMiddleware):
    """Log request Origin for /api/* so Render logs show exact origin seen."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin") or "(none)"
            print(f"[CORS] Request Origin: {origin!r} | path={request.url.path} method={request.method}")
        return await call_next(request)


app.add_middleware(_LogOriginMiddleware)

# Подключение статических файлов
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Подключение роутеров
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(admin_users.router, prefix="/api/admin", tags=["Admin Users"])

# Подключение админ-панели (используем СИНХРОННЫЙ engine!)
setup_admin(app, sync_engine)


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
    """Debug: request Origin vs allowed origins. Remove or protect after fix."""
    origin = request.headers.get("origin") or "(none)"
    allowed = list(_origins_list)
    origin_allowed = origin in allowed if origin != "(none)" else False
    return {
        "request_origin": origin,
        "allowed_origins": allowed,
        "origin_allowed": origin_allowed,
    }


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
