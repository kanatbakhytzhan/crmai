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
    Инициализировать базу данных (создать таблицы + миграция is_admin при необходимости)
    """
    from sqlalchemy import text
    from app.core.config import get_settings
    db_url = get_settings().database_url

    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
        # is_admin в users (PostgreSQL и SQLite — миграция для старых БД)
        if "postgresql" in db_url:
            try:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"
                ))
                print("[OK] Kolonka is_admin proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] is_admin migration: {type(e).__name__}: {e}")
        elif "sqlite" in db_url:
            try:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"
                ))
                print("[OK] SQLite: kolonka is_admin dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print("[OK] SQLite: is_admin uzhe est")
                else:
                    print(f"[WARN] is_admin SQLite: {type(e).__name__}: {e}")
            try:
                await conn.execute(text(
                    "ALTER TABLE tenants ADD COLUMN ai_enabled INTEGER DEFAULT 1"
                ))
                print("[OK] SQLite: kolonka tenants.ai_enabled dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print("[OK] SQLite: tenants.ai_enabled uzhe est")
                else:
                    print(f"[WARN] tenants.ai_enabled SQLite: {type(e).__name__}: {e}")
        if "postgresql" in db_url:
            # tenant_id в leads (nullable)
            try:
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id)"
                ))
                print("[OK] Kolonka leads.tenant_id proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] leads.tenant_id migration: {type(e).__name__}: {e}")
            # default_owner_user_id в tenants (nullable)
            try:
                await conn.execute(text(
                    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS default_owner_user_id INTEGER REFERENCES users(id)"
                ))
                print("[OK] Kolonka tenants.default_owner_user_id proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] tenants.default_owner_user_id migration: {type(e).__name__}: {e}")
            # conversation_messages.external_message_id (дедупликация ChatFlow)
            try:
                await conn.execute(text(
                    "ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS external_message_id VARCHAR(255)"
                ))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_messages_external_message_id "
                    "ON conversation_messages(external_message_id) WHERE external_message_id IS NOT NULL"
                ))
                print("[OK] Kolonka conversation_messages.external_message_id proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] external_message_id migration: {type(e).__name__}: {e}")
            # tenants.ai_prompt (кастомный промпт для AI по tenant)
            try:
                await conn.execute(text(
                    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ai_prompt TEXT"
                ))
                print("[OK] Kolonka tenants.ai_prompt proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] tenants.ai_prompt migration: {type(e).__name__}: {e}")
            # tenants.ai_enabled (AI-менеджер вкл/выкл для tenant)
            try:
                await conn.execute(text(
                    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT TRUE"
                ))
                await conn.execute(text(
                    "UPDATE tenants SET ai_enabled = TRUE WHERE ai_enabled IS NULL"
                ))
                print("[OK] Kolonka tenants.ai_enabled proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] tenants.ai_enabled migration: {type(e).__name__}: {e}")
            # Явное CREATE TABLE IF NOT EXISTS для Render/Postgres (на случай если create_all не создал)
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS lead_comments (
                        id SERIAL PRIMARY KEY,
                        lead_id INTEGER NOT NULL REFERENCES leads(id),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        text TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_lead_comments_lead_id ON lead_comments(lead_id)"
                ))
                print("[OK] Tablica lead_comments proverena/sozdana")
            except Exception as e:
                print(f"[WARN] lead_comments create: {type(e).__name__}: {e}")
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tenant_users (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        role VARCHAR(50) DEFAULT 'member',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, user_id)
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_tenant_users_tenant_id ON tenant_users(tenant_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_tenant_users_user_id ON tenant_users(user_id)"
                ))
                print("[OK] Tablica tenant_users proverena/sozdana")
            except Exception as e:
                print(f"[WARN] tenant_users create: {type(e).__name__}: {e}")
            # chat_mutes: per-chat и global mute для WhatsApp/ChatFlow
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS chat_mutes (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER REFERENCES tenants(id),
                        channel VARCHAR(64) NOT NULL,
                        phone_number_id VARCHAR(255),
                        external_id VARCHAR(255) NOT NULL,
                        scope VARCHAR(32) NOT NULL,
                        is_muted BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(channel, phone_number_id, scope, external_id)
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_mutes_channel_phone ON chat_mutes(channel, phone_number_id)"
                ))
                print("[OK] Tablica chat_mutes proverena/sozdana")
            except Exception as e:
                print(f"[WARN] chat_mutes create: {type(e).__name__}: {e}")
    print("[OK] Baza dannyh initializirovana")


async def drop_all_tables():
    """
    Удалить все таблицы (для dev режима)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("[DEV] Vse tablicy udaleny")
