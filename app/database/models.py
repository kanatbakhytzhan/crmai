"""
Модели базы данных (PostgreSQL)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Boolean, UniqueConstraint
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database.session import Base


class Tenant(Base):
    """Клиент (tenant) для multi-tenant по WhatsApp."""
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    default_owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ai_prompt = Column(Text, nullable=True)  # кастомный system prompt для OpenAI (если пусто — дефолтный)
    ai_enabled = Column(Boolean, default=True, nullable=False)  # автоответ AI вкл/выкл (команды /start /stop)
    webhook_key = Column(String(64), unique=True, index=True, nullable=True)  # UUID для POST /api/chatflow/webhook/{key}
    created_at = Column(DateTime, default=datetime.utcnow)

    whatsapp_accounts = relationship("WhatsAppAccount", back_populates="tenant", cascade="all, delete-orphan")
    tenant_users = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    pipelines = relationship("Pipeline", back_populates="tenant", cascade="all, delete-orphan")


class TenantUser(Base):
    """Связка пользователя с tenant (multi-user в одном tenant)."""
    __tablename__ = "tenant_users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member", nullable=True)  # owner, admin, member
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="tenant_users")
    user = relationship("User", backref="tenant_users")


class WhatsAppAccount(Base):
    """Привязанный к tenant WhatsApp (Meta Cloud API и/или ChatFlow)."""
    __tablename__ = "whatsapp_accounts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    phone_number = Column(String, nullable=False)
    phone_number_id = Column(String, unique=True, index=True, nullable=True)  # Meta; для ChatFlow может быть пусто
    waba_id = Column(String, nullable=True)
    verify_token = Column(String, nullable=True)
    chatflow_token = Column(String, nullable=True)   # токен ChatFlow для отправки ответов
    chatflow_instance_id = Column(String(255), nullable=True, index=True)  # instance_id из payload → tenant
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="whatsapp_accounts")

    @property
    def chatflow_token_masked(self) -> str | None:
        """Маскированный токен для ответа API (первые 4 символа + ***)."""
        t = getattr(self, "chatflow_token", None) or ""
        if not (t and str(t).strip()):
            return None
        s = str(t).strip()
        return s[:4] + "***" if len(s) > 4 else "***"


class Pipeline(Base):
    """Воронка (CRM v2). У каждого tenant может быть default pipeline."""
    __tablename__ = "pipelines"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="pipelines")
    stages = relationship("PipelineStage", back_populates="pipeline", cascade="all, delete-orphan", order_by="PipelineStage.order_index")


class PipelineStage(Base):
    """Стадия воронки."""
    __tablename__ = "pipeline_stages"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(Integer, ForeignKey("pipelines.id"), nullable=False)
    name = Column(String(255), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    color = Column(String(32), nullable=True)
    is_closed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    pipeline = relationship("Pipeline", back_populates="stages")


class Conversation(Base):
    """Один чат (tenant + WA from). Keyed by (channel, phone_number_id, external_id)."""
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("channel", "phone_number_id", "external_id", name="uq_conversation_channel_phone_from"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    channel = Column(String, default="whatsapp", nullable=False)
    external_id = Column(String, nullable=False)  # WA "from" / remoteJid
    phone_number_id = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    ai_paused = Column(Boolean, default=False, nullable=False)  # per-chat /stop: AI не отвечает в этом чате
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    """Одно сообщение в conversation (user / assistant / system)."""
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant" | "system"
    text = Column(Text, nullable=False)
    raw_json = Column(JSON, nullable=True)
    external_message_id = Column(String(255), unique=True, index=True, nullable=True)  # для дедупликации (ChatFlow messageId)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class LeadStatus(enum.Enum):
    """Статусы лида"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class User(Base):
    """
    Модель пользователя (владельца аккаунта SaaS)
    Это НЕ клиент, а менеджер/компания которая использует систему
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bot_users = relationship("BotUser", back_populates="owner", cascade="all, delete-orphan")
    leads = relationship(
        "Lead",
        back_populates="owner",
        cascade="all, delete-orphan",
        primaryjoin="User.id == Lead.owner_id",
        foreign_keys="[Lead.owner_id]",
    )


class BotUser(Base):
    """
    Модель клиента бота (конечный пользователь, который общается с AI)
    """
    __tablename__ = "bot_users"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Кому принадлежит этот клиент
    user_id = Column(String, index=True, nullable=False)  # ID из мессенджера (Telegram, WhatsApp и т.д.)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    language = Column(String, default="ru")  # ru или kk
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    owner = relationship("User", back_populates="bot_users")
    messages = relationship("Message", back_populates="bot_user", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="bot_user", cascade="all, delete-orphan")


class Message(Base):
    """Модель сообщения (история диалога)"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    bot_user_id = Column(Integer, ForeignKey("bot_users.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" или "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    bot_user = relationship("BotUser", back_populates="messages")


class ChatAIState(Base):
    """
    Включён ли AI в этом чате (remoteJid). /stop и /start меняют только эту таблицу.
    UNIQUE(tenant_id, remote_jid). Критерий один: входящий remoteJid (не sender).
    """
    __tablename__ = "chat_ai_states"
    __table_args__ = (UniqueConstraint("tenant_id", "remote_jid", name="uq_chat_ai_states_tenant_remote_jid"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    remote_jid = Column(String(255), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Lead(Base):
    """Модель лида (заявки)"""
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Владелец заявки
    bot_user_id = Column(Integer, ForeignKey("bot_users.id"), nullable=False)  # Клиент
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)  # Multi-tenant (WhatsApp)
    
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    phone_from_message = Column(String(32), nullable=True)  # последний номер, присланный текстом в чате
    city = Column(String, nullable=True)
    object_type = Column(String, nullable=True)
    area = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    language = Column(String, default="ru")
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.NEW)
    telegram_message_id = Column(Integer, nullable=True)
    lead_number = Column(Integer, nullable=True, index=True)  # CRM v2: порядковый номер (max+1 при создании)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # CRM v2: кому назначен (manager/rop/owner)
    assigned_at = Column(DateTime, nullable=True)    # когда назначили
    next_call_at = Column(DateTime, nullable=True)   # когда перезвонить
    last_contact_at = Column(DateTime, nullable=True)  # последнее касание
    pipeline_id = Column(Integer, ForeignKey("pipelines.id"), nullable=True)  # CRM v2 воронка
    stage_id = Column(Integer, ForeignKey("pipeline_stages.id"), nullable=True)
    moved_to_stage_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="leads", foreign_keys=[owner_id])
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    bot_user = relationship("BotUser", back_populates="leads")
    comments = relationship("LeadComment", back_populates="lead", cascade="all, delete-orphan")
    pipeline = relationship("Pipeline", backref="leads")
    stage = relationship("PipelineStage", backref="leads")
    tasks = relationship("LeadTask", back_populates="lead", cascade="all, delete-orphan")


class LeadComment(Base):
    """Комментарий к лиду (от пользователя CRM)."""
    __tablename__ = "lead_comments"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="comments")
    user = relationship("User", backref="lead_comments")


class LeadTask(Base):
    """Задача/напоминание по лиду (follow-up): звонок, встреча, заметка."""
    __tablename__ = "lead_tasks"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(32), nullable=False)  # call, meeting, note
    due_at = Column(DateTime, nullable=False)
    status = Column(String(32), default="open", nullable=False)  # open, done, cancelled
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    done_at = Column(DateTime, nullable=True)

    lead = relationship("Lead", back_populates="tasks")
    assigned_user = relationship("User", backref="lead_tasks")


class ChatMute(Base):
    """
    Mute автоответа AI: по чату (scope=chat) или по всем чатам номера (scope=all).
    UNIQUE(channel, phone_number_id, scope, external_id): для scope=all храним external_id=''.
    """
    __tablename__ = "chat_mutes"
    __table_args__ = (
        UniqueConstraint(
            "channel", "phone_number_id", "scope", "external_id",
            name="uq_chat_mute_channel_phone_scope_external",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    channel = Column(String(64), nullable=False)  # whatsapp, chatflow
    phone_number_id = Column(String(255), nullable=True)  # бизнес-номер; для ChatFlow может быть ""
    external_id = Column(String(255), nullable=False)  # jid/from; для scope=all — ""
    scope = Column(String(32), nullable=False)  # "chat" | "all"
    is_muted = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
