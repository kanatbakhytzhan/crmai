"""
Настройка подключения к PostgreSQL (асинхронно + синхронно для админки)
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine  # Синхронный для админки
from sqlalchemy.orm import declarative_base

from app.core.config import get_settings

settings = get_settings()

# Создаем асинхронный движок для основного приложения (FastAPI)
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Логирование SQL запросов в dev режиме
    future=True,
    pool_pre_ping=True,  # Проверка подключения перед использованием
)

# Создаем СИНХРОННЫЙ движок для админ-панели (SQLAdmin)
# SQLAdmin лучше работает с синхронным движком даже в async приложении
sync_database_url = settings.database_url
# Преобразование для синхронного подключения
if "+asyncpg" in sync_database_url:
    # PostgreSQL: postgresql+asyncpg:// -> postgresql+psycopg2://
    sync_database_url = sync_database_url.replace("+asyncpg", "+psycopg2")
elif "+aiosqlite" in sync_database_url:
    # SQLite: sqlite+aiosqlite:// -> sqlite://
    sync_database_url = sync_database_url.replace("+aiosqlite", "")

sync_engine = create_engine(
    sync_database_url,
    echo=False,  # Отключаем логи для админки
    pool_pre_ping=True,
)

# Фабрика для создания асинхронных сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base для моделей
Base = declarative_base()


async def init_db():
    """
    Инициализировать базу данных (создать таблицы)
    """
    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
    
    print("[OK] Baza dannyh initializirovana")


async def drop_all_tables():
    """
    Удалить все таблицы (для dev режима)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("[DEV] Vse tablicy udaleny")
