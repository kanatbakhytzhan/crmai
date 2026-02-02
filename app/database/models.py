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
    created_at = Column(DateTime, default=datetime.utcnow)

    whatsapp_accounts = relationship("WhatsAppAccount", back_populates="tenant", cascade="all, delete-orphan")


class WhatsAppAccount(Base):
    """Привязанный к tenant WhatsApp номер (phone_number_id от Meta)."""
    __tablename__ = "whatsapp_accounts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    phone_number = Column(String, nullable=False)
    phone_number_id = Column(String, unique=True, index=True, nullable=False)
    waba_id = Column(String, nullable=True)
    verify_token = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="whatsapp_accounts")


class Conversation(Base):
    """Один чат (tenant + WA from). Keyed by (channel, phone_number_id, external_id)."""
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("channel", "phone_number_id", "external_id", name="uq_conversation_channel_phone_from"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    channel = Column(String, default="whatsapp", nullable=False)
    external_id = Column(String, nullable=False)  # WA "from" number
    phone_number_id = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
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
    leads = relationship("Lead", back_populates="owner", cascade="all, delete-orphan")


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


class Lead(Base):
    """Модель лида (заявки)"""
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Владелец заявки
    bot_user_id = Column(Integer, ForeignKey("bot_users.id"), nullable=False)  # Клиент
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)  # Multi-tenant (WhatsApp)
    
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    city = Column(String, nullable=True)
    object_type = Column(String, nullable=True)
    area = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    language = Column(String, default="ru")
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.NEW)
    telegram_message_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    owner = relationship("User", back_populates="leads")
    bot_user = relationship("BotUser", back_populates="leads")
