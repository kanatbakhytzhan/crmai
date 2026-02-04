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
            # CRM v2.5: tenant_users.parent_user_id, is_active
            for col, defn in [
                ("parent_user_id", "INTEGER REFERENCES users(id)"),
                ("is_active", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE tenant_users ADD COLUMN {col} {defn}"))
                    print(f"[OK] tenant_users.{col} dobavlena")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"[OK] tenant_users.{col} uzhe est")
                    else:
                        print(f"[WARN] tenant_users.{col}: {type(e).__name__}: {e}")
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
            # CRM v2: pipelines, pipeline_stages, lead_tasks; leads.pipeline_id, stage_id, moved_to_stage_at
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pipelines (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        name VARCHAR(255) NOT NULL,
                        is_default BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pipelines_tenant_id ON pipelines(tenant_id)"))
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pipeline_stages (
                        id SERIAL PRIMARY KEY,
                        pipeline_id INTEGER NOT NULL REFERENCES pipelines(id),
                        name VARCHAR(255) NOT NULL,
                        order_index INTEGER NOT NULL DEFAULT 0,
                        color VARCHAR(32),
                        is_closed BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pipeline_stages_pipeline_id ON pipeline_stages(pipeline_id)"))
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS lead_tasks (
                        id SERIAL PRIMARY KEY,
                        lead_id INTEGER NOT NULL REFERENCES leads(id),
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        assigned_to_user_id INTEGER NOT NULL REFERENCES users(id),
                        type VARCHAR(32) NOT NULL,
                        due_at TIMESTAMP NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'open',
                        note TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        done_at TIMESTAMP
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_lead_tasks_user_due_status ON lead_tasks(assigned_to_user_id, due_at, status)"
                ))
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_id INTEGER REFERENCES pipelines(id)"
                ))
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_id INTEGER REFERENCES pipeline_stages(id)"
                ))
                await conn.execute(text(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS moved_to_stage_at TIMESTAMP"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_leads_tenant_stage ON leads(tenant_id, stage_id) WHERE tenant_id IS NOT NULL AND stage_id IS NOT NULL"
                ))
                print("[OK] Tablicy pipelines, pipeline_stages, lead_tasks i kolonki leads provereny")
            except Exception as e:
                print(f"[WARN] pipelines/tasks migration: {type(e).__name__}: {e}")
            # CRM v2.5: ai_chat_mutes, audit_log, notifications
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_chat_mutes (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        lead_id INTEGER REFERENCES leads(id),
                        chat_key VARCHAR(512) NOT NULL,
                        is_muted BOOLEAN NOT NULL DEFAULT TRUE,
                        muted_by_user_id INTEGER REFERENCES users(id),
                        muted_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, chat_key)
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_chat_mutes_tenant_chat ON ai_chat_mutes(tenant_id, chat_key)"))
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER REFERENCES tenants(id),
                        actor_user_id INTEGER NOT NULL REFERENCES users(id),
                        action VARCHAR(128) NOT NULL,
                        payload_json JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_log_tenant_created ON audit_log(tenant_id, created_at)"))
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER REFERENCES tenants(id),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        type VARCHAR(64) NOT NULL,
                        title VARCHAR(255),
                        body TEXT,
                        is_read BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        lead_id INTEGER REFERENCES leads(id)
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications(user_id, is_read)"))
                print("[OK] Tablicy ai_chat_mutes, audit_log, notifications provereny")
            except Exception as e:
                print(f"[WARN] CRM v2.5 tables: {type(e).__name__}: {e}")
            # CRM v3: leads — first_response_at, first_assigned_at, source, external_source, external_id
            try:
                for col, defn in [
                    ("first_response_at", "TIMESTAMP"),
                    ("first_assigned_at", "TIMESTAMP"),
                    ("source", "VARCHAR(64)"),
                    ("external_source", "VARCHAR(64)"),
                    ("external_id", "VARCHAR(255)"),
                ]:
                    await conn.execute(text(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} {defn}"))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_leads_external_id ON leads(external_id) WHERE external_id IS NOT NULL"
                ))
                print("[OK] CRM v3 kolonki leads (first_response_at, source, external_*) provereny")
            except Exception as e:
                print(f"[WARN] CRM v3 leads columns: {type(e).__name__}: {e}")
            # CRM v3: lead_events
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS lead_events (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        lead_id INTEGER NOT NULL REFERENCES leads(id),
                        type VARCHAR(64) NOT NULL,
                        actor_user_id INTEGER REFERENCES users(id),
                        payload JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_lead_events_tenant_created ON lead_events(tenant_id, created_at)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_lead_events_lead_id ON lead_events(lead_id)"))
                print("[OK] Tablica lead_events proverena/sozdana")
            except Exception as e:
                print(f"[WARN] lead_events create: {type(e).__name__}: {e}")
            # CRM v3: auto_assign_rules
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS auto_assign_rules (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        name VARCHAR(255) NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        priority INTEGER NOT NULL DEFAULT 0,
                        match_city VARCHAR(255),
                        match_language VARCHAR(32),
                        match_object_type VARCHAR(255),
                        match_contains VARCHAR(512),
                        time_from INTEGER,
                        time_to INTEGER,
                        days_of_week VARCHAR(32),
                        strategy VARCHAR(32) NOT NULL,
                        fixed_user_id INTEGER REFERENCES users(id),
                        rr_state INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auto_assign_rules_tenant_active ON auto_assign_rules(tenant_id, is_active)"))
                print("[OK] Tablica auto_assign_rules proverena/sozdana")
            except Exception as e:
                print(f"[WARN] auto_assign_rules create: {type(e).__name__}: {e}")
            # Universal Admin Console: tenants new columns
            try:
                for col, defn in [
                    ("whatsapp_source", "VARCHAR(32) DEFAULT 'chatflow' NOT NULL"),
                    ("ai_enabled_global", "BOOLEAN DEFAULT TRUE NOT NULL"),
                    ("ai_after_lead_submitted_behavior", "VARCHAR(64) DEFAULT 'polite_close'"),
                    ("amocrm_base_domain", "VARCHAR(255)"),
                ]:
                    await conn.execute(text(f"ALTER TABLE tenants ADD COLUMN IF NOT EXISTS {col} {defn}"))
                await conn.execute(text("UPDATE tenants SET whatsapp_source = 'chatflow' WHERE whatsapp_source IS NULL"))
                await conn.execute(text("UPDATE tenants SET ai_enabled_global = TRUE WHERE ai_enabled_global IS NULL"))
                print("[OK] Universal Admin: kolonki tenants provereny")
            except Exception as e:
                print(f"[WARN] tenants Universal Admin columns: {type(e).__name__}: {e}")
            # Universal Admin Console: tenant_integrations
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tenant_integrations (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        provider VARCHAR(32) NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        base_domain VARCHAR(255),
                        access_token TEXT,
                        refresh_token TEXT,
                        token_expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, provider)
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_integrations_tenant ON tenant_integrations(tenant_id)"))
                print("[OK] Tablica tenant_integrations proverena/sozdana")
            except Exception as e:
                print(f"[WARN] tenant_integrations create: {type(e).__name__}: {e}")
            # Universal Admin Console: tenant_pipeline_mappings
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tenant_pipeline_mappings (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        provider VARCHAR(32) NOT NULL,
                        pipeline_id VARCHAR(64),
                        stage_key VARCHAR(64) NOT NULL,
                        stage_id VARCHAR(64),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, provider, stage_key)
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_pipeline_mappings_tenant ON tenant_pipeline_mappings(tenant_id, provider)"))
                print("[OK] Tablica tenant_pipeline_mappings proverena/sozdana")
            except Exception as e:
                print(f"[WARN] tenant_pipeline_mappings create: {type(e).__name__}: {e}")
            # Universal Admin Console: tenant_field_mappings
            try:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tenant_field_mappings (
                        id SERIAL PRIMARY KEY,
                        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                        provider VARCHAR(32) NOT NULL,
                        field_key VARCHAR(64) NOT NULL,
                        amo_field_id VARCHAR(64),
                        entity_type VARCHAR(32) NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, provider, field_key, entity_type)
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_field_mappings_tenant ON tenant_field_mappings(tenant_id, provider)"))
                print("[OK] Tablica tenant_field_mappings proverena/sozdana")
            except Exception as e:
                print(f"[WARN] tenant_field_mappings create: {type(e).__name__}: {e}")
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
        for col, typ in [("assigned_user_id", "INTEGER"), ("assigned_at", "DATETIME"), ("next_call_at", "DATETIME"), ("last_contact_at", "DATETIME"), ("pipeline_id", "INTEGER"), ("stage_id", "INTEGER"), ("moved_to_stage_at", "DATETIME"), ("first_response_at", "DATETIME"), ("first_assigned_at", "DATETIME"), ("source", "VARCHAR(64)"), ("external_source", "VARCHAR(64)"), ("external_id", "VARCHAR(255)")]:
            try:
                await conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {typ}"))
                print(f"[OK] SQLite: leads.{col} dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print(f"[OK] SQLite: leads.{col} uzhe est")
                else:
                    print(f"[WARN] leads.{col} SQLite: {type(e).__name__}: {e}")
        # SQLite: lead_events, auto_assign_rules, Universal Admin tables
        for tname, sql in [
            ("lead_events", """
                CREATE TABLE IF NOT EXISTS lead_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                    lead_id INTEGER NOT NULL REFERENCES leads(id),
                    type VARCHAR(64) NOT NULL,
                    actor_user_id INTEGER REFERENCES users(id),
                    payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """),
            ("auto_assign_rules", """
                CREATE TABLE IF NOT EXISTS auto_assign_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                    name VARCHAR(255) NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 0,
                    match_city VARCHAR(255),
                    match_language VARCHAR(32),
                    match_object_type VARCHAR(255),
                    match_contains VARCHAR(512),
                    time_from INTEGER,
                    time_to INTEGER,
                    days_of_week VARCHAR(32),
                    strategy VARCHAR(32) NOT NULL,
                    fixed_user_id INTEGER REFERENCES users(id),
                    rr_state INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """),
            ("tenant_integrations", """
                CREATE TABLE IF NOT EXISTS tenant_integrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                    provider VARCHAR(32) NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    base_domain VARCHAR(255),
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, provider)
                )
            """),
            ("tenant_pipeline_mappings", """
                CREATE TABLE IF NOT EXISTS tenant_pipeline_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                    provider VARCHAR(32) NOT NULL,
                    pipeline_id VARCHAR(64),
                    stage_key VARCHAR(64) NOT NULL,
                    stage_id VARCHAR(64),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, provider, stage_key)
                )
            """),
            ("tenant_field_mappings", """
                CREATE TABLE IF NOT EXISTS tenant_field_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                    provider VARCHAR(32) NOT NULL,
                    field_key VARCHAR(64) NOT NULL,
                    amo_field_id VARCHAR(64),
                    entity_type VARCHAR(32) NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, provider, field_key, entity_type)
                )
            """),
        ]:
            try:
                await conn.execute(text(sql))
                print(f"[OK] SQLite: tablica {tname} proverena/sozdana")
            except Exception as e:
                print(f"[WARN] SQLite {tname}: {type(e).__name__}: {e}")
        # SQLite: new tenant columns
        for col, typ in [("whatsapp_source", "VARCHAR(32) DEFAULT 'chatflow'"), ("ai_enabled_global", "INTEGER DEFAULT 1"), ("ai_after_lead_submitted_behavior", "VARCHAR(64) DEFAULT 'polite_close'"), ("amocrm_base_domain", "VARCHAR(255)")]:
            try:
                await conn.execute(text(f"ALTER TABLE tenants ADD COLUMN {col} {typ}"))
                print(f"[OK] SQLite: tenants.{col} dobavlena")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print(f"[OK] SQLite: tenants.{col} uzhe est")
                else:
                    print(f"[WARN] tenants.{col} SQLite: {type(e).__name__}: {e}")
    print("[OK] Baza dannyh initializirovana")


async def drop_all_tables():
    """
    Удалить все таблицы (для dev режима)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("[DEV] Vse tablicy udaleny")
