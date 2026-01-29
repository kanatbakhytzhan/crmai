"""
Модели базы данных (PostgreSQL)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database.session import Base


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
