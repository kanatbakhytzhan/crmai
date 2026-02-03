"""
Конфигурация приложения - загрузка переменных окружения
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # OpenAI
    openai_api_key: str
    
    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str
    
    # Database (PostgreSQL / Supabase / SQLite fallback)
    database_url: str = "sqlite+aiosqlite:///./sales_bot.db"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Railway Database Switcher
        # Railway предоставляет DATABASE_URL в формате postgres://
        # Нужно заменить на postgresql:// для SQLAlchemy
        railway_db = os.getenv("DATABASE_URL")
        if railway_db:
            # Railway использует postgres://, SQLAlchemy требует postgresql://
            if railway_db.startswith("postgres://"):
                railway_db = railway_db.replace("postgres://", "postgresql+asyncpg://", 1)
            elif railway_db.startswith("postgresql://"):
                railway_db = railway_db.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            self.database_url = railway_db
            print(f"[Railway] Using DATABASE_URL from environment")
        else:
            print(f"[Local] Using SQLite: {self.database_url}")
    
    # Security (JWT)
    secret_key: str = "CHANGE_THIS_TO_RANDOM_SECRET_KEY_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 дней
    
    # Application
    app_name: str = "AI Sales Manager SaaS"
    debug: bool = True
    dev_mode: str = "FALSE"  # TRUE - очистка БД при перезапуске
    
    # Guest mode: владелец лидов с веб-чата (без токена). Если задан email — все гостевые лиды идут этому пользователю.
    default_owner_email: Optional[str] = None
    
    # Админка: emails, которые считаются админами (без is_admin в БД). Формат: "email1,email2"
    admin_emails: Optional[str] = None
    # Аварийное восстановление: секрет для POST /api/admin/recovery/enable-user (без логина). Задать на Render.
    admin_recovery_key: Optional[str] = None
    
    # CORS: разрешённые origins для CRM/админки. Формат: "http://localhost:5173,https://my-pwa.com"
    # На Render задайте CORS_ORIGINS с вашим прод-доменом PWA.
    cors_origins: Optional[str] = None
    # Публичный URL приложения (для webhook_url в админке). Например https://api.example.com
    public_base_url: Optional[str] = None
    
    # CRM v2 (feature-flag): нумерация лидов, GET /api/v2/leads/table
    crm_v2_enabled: str = "false"  # "true" — включить v2 API и lead_number
    # CRM v2.5: логировать применение tenant prompt (только длина/флаг, не сам текст)
    crm_debug_prompt: str = "false"  # "true" — stdout: tenant_id, ai_prompt_len, using_default_prompt, lead_id

    # Multi-tenant + WhatsApp (подготовка)
    multitenant_enabled: str = "false"  # "true" — фильтр лидов по tenant
    whatsapp_enabled: str = "false"     # "true" — включить webhook WhatsApp
    whatsapp_verify_token: Optional[str] = None  # Fallback для Meta verification

    # WhatsApp Cloud API: отправка ответов (по умолчанию выключено)
    whatsapp_send_enabled: str = "false"  # "true" — отправлять ответы в WhatsApp
    whatsapp_access_token: Optional[str] = None
    whatsapp_api_version: str = "v20.0"
    whatsapp_graph_base: str = "https://graph.facebook.com"

    # AmoCRM OAuth (Universal Admin Console)
    amo_client_id: Optional[str] = None
    amo_client_secret: Optional[str] = None
    amo_redirect_url: Optional[str] = None  # e.g. https://your-api.com/api/integrations/amocrm/callback

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки приложения (с кешированием)"""
    return Settings()
