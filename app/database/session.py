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
            try:
                await conn.execute(text(
                    "ALTER TABLE conversations ADD COLUMN ai_paused INTEGER DEFAULT 0"
                ))
                print("[OK] SQLite: kolonka conversations.ai_paused dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print("[OK] SQLite: conversations.ai_paused uzhe est")
                else:
                    print(f"[WARN] conversations.ai_paused SQLite: {type(e).__name__}: {e}")
            try:
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN phone_from_message VARCHAR(32)"
                ))
                print("[OK] SQLite: kolonka leads.phone_from_message dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print("[OK] SQLite: leads.phone_from_message uzhe est")
                else:
                    print(f"[WARN] leads.phone_from_message SQLite: {type(e).__name__}: {e}")
            try:
                await conn.execute(text(
                    "ALTER TABLE whatsapp_accounts ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ))
                print("[OK] SQLite: kolonka whatsapp_accounts.updated_at dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print("[OK] SQLite: whatsapp_accounts.updated_at uzhe est")
                else:
                    print(f"[WARN] whatsapp_accounts.updated_at SQLite: {type(e).__name__}: {e}")
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
            # conversations.ai_paused (per-chat /stop: AI не отвечает в этом чате)
            try:
                await conn.execute(text(
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_paused BOOLEAN DEFAULT FALSE"
                ))
                await conn.execute(text(
                    "UPDATE conversations SET ai_paused = FALSE WHERE ai_paused IS NULL"
                ))
                print("[OK] Kolonka conversations.ai_paused proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] conversations.ai_paused migration: {type(e).__name__}: {e}")
            # tenants.webhook_key (UUID для POST /api/chatflow/webhook/{key})
            try:
                await conn.execute(text(
                    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS webhook_key VARCHAR(64) UNIQUE"
                ))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_webhook_key ON tenants(webhook_key) WHERE webhook_key IS NOT NULL"
                ))
                print("[OK] Kolonka tenants.webhook_key proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] tenants.webhook_key migration: {type(e).__name__}: {e}")
            # Заполнить webhook_key у существующих tenants, где он пустой
            try:
                import secrets
                res = await conn.execute(text("SELECT id FROM tenants WHERE webhook_key IS NULL OR webhook_key = ''"))
                rows = res.fetchall()
                seen = set()
                for (tid,) in rows:
                    key = secrets.token_urlsafe(16)
                    while key in seen:
                        key = secrets.token_urlsafe(16)
                    seen.add(key)
                    await conn.execute(text("UPDATE tenants SET webhook_key = :k WHERE id = :id"), {"k": key, "id": tid})
                if rows:
                    print("[OK] tenants.webhook_key zapolnen dlya", len(rows), "zapisey")
            except Exception as e:
                print(f"[WARN] tenants.webhook_key fill: {type(e).__name__}: {e}")
            # whatsapp_accounts: chatflow_token, chatflow_instance_id; phone_number_id nullable
            try:
                await conn.execute(text(
                    "ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS chatflow_token VARCHAR(512)"
                ))
                await conn.execute(text(
                    "ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS chatflow_instance_id VARCHAR(255)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_whatsapp_accounts_chatflow_instance_id ON whatsapp_accounts(chatflow_instance_id) WHERE chatflow_instance_id IS NOT NULL"
                ))
                print("[OK] Kolonki whatsapp_accounts chatflow provereny/dobavleny")
            except Exception as e:
                print(f"[WARN] whatsapp_accounts chatflow migration: {type(e).__name__}: {e}")
            try:
                await conn.execute(text(
                    "ALTER TABLE whatsapp_accounts ALTER COLUMN phone_number_id DROP NOT NULL"
                ))
                print("[OK] whatsapp_accounts.phone_number_id nullable")
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    print(f"[WARN] whatsapp_accounts phone_number_id nullable: {type(e).__name__}: {e}")
            try:
                await conn.execute(text(
                    "ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ))
                print("[OK] Kolonka whatsapp_accounts.updated_at proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] whatsapp_accounts.updated_at migration: {type(e).__name__}: {e}")
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
            # chat_ai_states: per-chat /stop /start по remoteJid
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS chat_ai_states (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        remote_jid VARCHAR(255) NOT NULL,
                        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, remote_jid)
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_ai_states_tenant_jid ON chat_ai_states(tenant_id, remote_jid)"
                ))
                print("[OK] Tablica chat_ai_states proverena/sozdana")
            except Exception as e:
                print(f"[WARN] chat_ai_states create: {type(e).__name__}: {e}")
            # leads.phone_from_message (номер, присланный текстом в чате)
            try:
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS phone_from_message VARCHAR(32)"
                ))
                print("[OK] Kolonka leads.phone_from_message proverena/dobavlena")
            except Exception as e:
                print(f"[WARN] leads.phone_from_message migration: {type(e).__name__}: {e}")
            # leads.lead_number (CRM v2: порядковый номер, уникален в рамках tenant или owner)
            try:
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_number INTEGER"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_leads_lead_number ON leads(lead_number) WHERE lead_number IS NOT NULL"
                ))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_tenant_lead_number ON leads(tenant_id, lead_number) WHERE tenant_id IS NOT NULL"
                ))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_owner_lead_number ON leads(owner_id, lead_number) WHERE tenant_id IS NULL"
                ))
                print("[OK] Kolonka leads.lead_number i unikalnost provereny/dobavleny")
            except Exception as e:
                print(f"[WARN] leads.lead_number migration: {type(e).__name__}: {e}")
            # leads: assigned_user_id, next_call_at, last_contact_at (CRM v2)
            try:
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS assigned_user_id INTEGER REFERENCES users(id)"
                ))
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_call_at TIMESTAMP"
                ))
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contact_at TIMESTAMP"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_leads_tenant_id ON leads(tenant_id) WHERE tenant_id IS NOT NULL"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_leads_assigned_user_id ON leads(assigned_user_id) WHERE assigned_user_id IS NOT NULL"
                ))
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP"
                ))
                print("[OK] Kolonki leads.assigned_user_id, assigned_at, next_call_at, last_contact_at provereny")
            except Exception as e:
                print(f"[WARN] leads CRM v2 columns: {type(e).__name__}: {e}")
    if "sqlite" in db_url:
        try:
            await conn.execute(text(
                "ALTER TABLE leads ADD COLUMN lead_number INTEGER"
            ))
            print("[OK] SQLite: kolonka leads.lead_number dobavlena")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("[OK] SQLite: leads.lead_number uzhe est")
            else:
                print(f"[WARN] leads.lead_number SQLite: {type(e).__name__}: {e}")
        for col, typ in [("assigned_user_id", "INTEGER"), ("assigned_at", "DATETIME"), ("next_call_at", "DATETIME"), ("last_contact_at", "DATETIME")]:
            try:
                await conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {typ}"))
                print(f"[OK] SQLite: leads.{col} dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print(f"[OK] SQLite: leads.{col} uzhe est")
                else:
                    print(f"[WARN] leads.{col} SQLite: {type(e).__name__}: {e}")
    print("[OK] Baza dannyh initializirovana")


async def drop_all_tables():
    """
    Удалить все таблицы (для dev режима)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("[DEV] Vse tablicy udaleny")
