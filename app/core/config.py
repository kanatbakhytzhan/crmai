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
    
    # CORS: разрешённые origins для CRM/админки. Формат: "http://localhost:5173,https://my-pwa.com"
    # На Render задайте CORS_ORIGINS с вашим прод-доменом PWA.
    cors_origins: Optional[str] = None
    
    # Multi-tenant + WhatsApp (подготовка)
    multitenant_enabled: str = "false"  # "true" — фильтр лидов по tenant
    whatsapp_enabled: str = "false"     # "true" — включить webhook WhatsApp
    whatsapp_verify_token: Optional[str] = None  # Fallback для Meta verification
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки приложения (с кешированием)"""
    return Settings()
