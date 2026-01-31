"""
CRUD операции для работы с базой данных (Async)
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta

from app.database.models import User, BotUser, Message, Lead, LeadStatus
from app.core.security import get_password_hash


# ========== USER (Владелец аккаунта) ==========

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Получить пользователя по email"""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str, password: str, company_name: str) -> User:
    """Создать нового пользователя"""
    hashed_password = get_password_hash(password)
    user = User(
        email=email,
        hashed_password=hashed_password,
        company_name=company_name
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Получить пользователя по ID"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_first_user(db: AsyncSession) -> Optional[User]:
    """Получить первого пользователя (для guest mode)"""
    result = await db.execute(
        select(User)
        .where(User.is_active == True)
        .order_by(User.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_all_users(db: AsyncSession, limit: int = 500) -> List[User]:
    """Получить всех пользователей (для админки)"""
    result = await db.execute(
        select(User).order_by(User.id.asc()).limit(limit)
    )
    return list(result.scalars().all())


async def update_user(
    db: AsyncSession,
    user_id: int,
    *,
    is_active: Optional[bool] = None,
    company_name: Optional[str] = None,
    is_admin: Optional[bool] = None,
) -> Optional[User]:
    """Обновить пользователя (админка)"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    if is_active is not None:
        user.is_active = is_active
    if company_name is not None:
        user.company_name = company_name
    if is_admin is not None:
        user.is_admin = is_admin
    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_password(db: AsyncSession, user_id: int, new_password: str) -> Optional[User]:
    """Установить новый пароль пользователю (хеш)"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    user.hashed_password = get_password_hash(new_password)
    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


# ========== BOT USER (Клиент бота) ==========

async def get_bot_user_by_user_id(db: AsyncSession, user_id: str, owner_id: int) -> Optional[BotUser]:
    """Получить клиента бота по user_id (с проверкой владельца)"""
    result = await db.execute(
        select(BotUser).where(
            BotUser.user_id == user_id,
            BotUser.owner_id == owner_id
        )
    )
    return result.scalar_one_or_none()


async def create_bot_user(db: AsyncSession, user_id: str, owner_id: int, language: str = "ru") -> BotUser:
    """Создать нового клиента бота"""
    bot_user = BotUser(user_id=user_id, owner_id=owner_id, language=language)
    db.add(bot_user)
    await db.commit()
    await db.refresh(bot_user)
    return bot_user


async def get_or_create_bot_user(db: AsyncSession, user_id: str, owner_id: int, language: str = "ru") -> BotUser:
    """Получить или создать клиента бота"""
    bot_user = await get_bot_user_by_user_id(db, user_id, owner_id)
    if not bot_user:
        bot_user = await create_bot_user(db, user_id, owner_id, language)
    return bot_user


async def update_bot_user_info(
    db: AsyncSession, 
    user_id: str, 
    owner_id: int,
    name: Optional[str] = None, 
    phone: Optional[str] = None
) -> Optional[BotUser]:
    """Обновить информацию клиента бота"""
    bot_user = await get_bot_user_by_user_id(db, user_id, owner_id)
    if bot_user:
        if name:
            bot_user.name = name
        if phone:
            bot_user.phone = phone
        await db.commit()
        await db.refresh(bot_user)
    return bot_user


# ========== MESSAGE ==========

async def create_message(db: AsyncSession, bot_user_id: int, role: str, content: str) -> Message:
    """Создать сообщение в истории диалога"""
    message = Message(bot_user_id=bot_user_id, role=role, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_bot_user_messages(db: AsyncSession, bot_user_id: int, limit: int = 20) -> List[Message]:
    """Получить историю сообщений клиента бота"""
    result = await db.execute(
        select(Message)
        .where(Message.bot_user_id == bot_user_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ========== LEAD ==========

async def create_lead(
    db: AsyncSession,
    owner_id: int,
    bot_user_id: int,
    name: str,
    phone: str,
    summary: str,
    language: str,
    city: str = "",
    object_type: str = "",
    area: str = ""
) -> Lead:
    """Создать новую заявку (лид)"""
    lead = Lead(
        owner_id=owner_id,
        bot_user_id=bot_user_id,
        name=name,
        phone=phone,
        city=city,
        object_type=object_type,
        area=area,
        summary=summary,
        language=language,
        status=LeadStatus.NEW
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def get_user_leads(db: AsyncSession, owner_id: int, limit: int = 100) -> List[Lead]:
    """Получить все заявки пользователя"""
    result = await db.execute(
        select(Lead)
        .where(Lead.owner_id == owner_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_lead_by_id(db: AsyncSession, lead_id: int, owner_id: int) -> Optional[Lead]:
    """Получить лид по ID (с проверкой владельца)"""
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.owner_id == owner_id
        )
    )
    return result.scalar_one_or_none()


async def update_lead_status(db: AsyncSession, lead_id: int, owner_id: int, status: LeadStatus) -> Optional[Lead]:
    """Обновить статус лида"""
    lead = await get_lead_by_id(db, lead_id, owner_id)
    if lead:
        lead.status = status
        await db.commit()
        await db.refresh(lead)
    return lead


async def update_lead_telegram_message_id(
    db: AsyncSession, 
    lead_id: int, 
    owner_id: int, 
    telegram_message_id: int
) -> Optional[Lead]:
    """Сохранить ID сообщения Telegram для лида"""
    lead = await get_lead_by_id(db, lead_id, owner_id)
    if lead:
        lead.telegram_message_id = telegram_message_id
        await db.commit()
        await db.refresh(lead)
    return lead


async def has_recent_lead(db: AsyncSession, bot_user_id: int, minutes: int = 5) -> bool:
    """Проверить есть ли у клиента бота недавняя заявка (за последние N минут)"""
    time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
    result = await db.execute(
        select(Lead).where(
            Lead.bot_user_id == bot_user_id,
            Lead.created_at > time_threshold
        )
    )
    lead = result.scalar_one_or_none()
    return lead is not None


async def delete_lead(db: AsyncSession, lead_id: int, owner_id: int) -> bool:
    """
    Удалить заявку по ID (с проверкой владельца)
    
    Args:
        db: Сессия БД
        lead_id: ID заявки
        owner_id: ID владельца (для безопасности)
        
    Returns:
        True если заявка была удалена, False если не найдена
    """
    lead = await get_lead_by_id(db, lead_id, owner_id)
    if lead:
        await db.delete(lead)
        await db.commit()
        return True
    return False
