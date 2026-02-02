"""
CRUD операции для работы с базой данных (Async)
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta

from app.database.models import (
    User, BotUser, Message, Lead, LeadStatus, LeadComment, Tenant, TenantUser, WhatsAppAccount,
    Conversation, ConversationMessage,
)
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


async def get_user_leads(
    db: AsyncSession,
    owner_id: int,
    limit: int = 100,
    *,
    multitenant_include_tenant_leads: bool = False,
) -> List[Lead]:
    """
    Получить заявки пользователя. Если multitenant_include_tenant_leads=True,
    также включаются лиды: tenant.default_owner_user_id = owner_id ИЛИ
    пользователь в tenant_users для этого tenant (multi-user в одном tenant).
    """
    from sqlalchemy import or_
    if not multitenant_include_tenant_leads:
        result = await db.execute(
            select(Lead)
            .where(Lead.owner_id == owner_id)
            .order_by(Lead.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    # Лиды владельца + лиды tenant (default_owner) + лиды tenant (tenant_users)
    tenant_ids_default = select(Tenant.id).where(Tenant.default_owner_user_id == owner_id)
    tenant_ids_member = select(TenantUser.tenant_id).where(TenantUser.user_id == owner_id)
    result = await db.execute(
        select(Lead)
        .where(
            or_(
                Lead.owner_id == owner_id,
                Lead.tenant_id.in_(tenant_ids_default),
                Lead.tenant_id.in_(tenant_ids_member),
            )
        )
        .order_by(Lead.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_lead_by_id(
    db: AsyncSession,
    lead_id: int,
    owner_id: int,
    *,
    multitenant_include_tenant_leads: bool = False,
) -> Optional[Lead]:
    """
    Получить лид по ID. Доступ если owner_id совпадает или (multitenant и
    lead.tenant_id и (tenant.default_owner_user_id == owner_id или user в tenant_users)).
    """
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        return None
    if lead.owner_id == owner_id:
        return lead
    if multitenant_include_tenant_leads and lead.tenant_id is not None:
        tenant = await get_tenant_by_id(db, lead.tenant_id)
        if tenant and getattr(tenant, "default_owner_user_id", None) == owner_id:
            return lead
        # Доступ по tenant_users (multi-user в одном tenant)
        tu = await db.execute(
            select(TenantUser).where(
                TenantUser.tenant_id == lead.tenant_id,
                TenantUser.user_id == owner_id,
            )
        )
        if tu.scalar_one_or_none():
            return lead
    return None


async def update_lead_status(
    db: AsyncSession,
    lead_id: int,
    owner_id: int,
    status: LeadStatus,
    *,
    multitenant_include_tenant_leads: bool = False,
) -> Optional[Lead]:
    """Обновить статус лида"""
    lead = await get_lead_by_id(db, lead_id, owner_id, multitenant_include_tenant_leads=multitenant_include_tenant_leads)
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


async def get_active_lead_by_bot_user(db: AsyncSession, bot_user_id: int) -> Optional[Lead]:
    """Один активный лид на клиента (NEW или IN_PROGRESS). Для ChatFlow — один lead на jid."""
    result = await db.execute(
        select(Lead)
        .where(
            Lead.bot_user_id == bot_user_id,
            Lead.status.in_([LeadStatus.NEW, LeadStatus.IN_PROGRESS]),
        )
        .order_by(Lead.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_lead_phone(db: AsyncSession, lead_id: int, phone: str) -> Optional[Lead]:
    """Обновить телефон лида (для ChatFlow: номер из текста сообщения)."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if lead and (phone or "").strip():
        lead.phone = (phone or "").strip()
        await db.commit()
        await db.refresh(lead)
    return lead


async def delete_lead(
    db: AsyncSession,
    lead_id: int,
    owner_id: int,
    *,
    multitenant_include_tenant_leads: bool = False,
) -> bool:
    """
    Удалить заявку по ID (с проверкой владельца)

    Args:
        db: Сессия БД
        lead_id: ID заявки
        owner_id: ID владельца (для безопасности)

    Returns:
        True если заявка была удалена, False если не найдена
    """
    lead = await get_lead_by_id(db, lead_id, owner_id, multitenant_include_tenant_leads=multitenant_include_tenant_leads)
    if lead:
        await db.delete(lead)
        await db.commit()
        return True
    return False


# ========== LEAD COMMENTS ==========

async def get_lead_comments(
    db: AsyncSession,
    lead_id: int,
    limit: int = 100,
) -> List[LeadComment]:
    """Комментарии к лиду по created_at desc."""
    result = await db.execute(
        select(LeadComment)
        .where(LeadComment.lead_id == lead_id)
        .order_by(LeadComment.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_last_lead_comment(db: AsyncSession, lead_id: int) -> Optional[LeadComment]:
    """Последний комментарий к лиду (preview для GET /api/leads)."""
    result = await db.execute(
        select(LeadComment)
        .where(LeadComment.lead_id == lead_id)
        .order_by(LeadComment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_lead_comment(
    db: AsyncSession,
    lead_id: int,
    user_id: int,
    text: str,
) -> LeadComment:
    """Добавить комментарий к лиду."""
    comment = LeadComment(lead_id=lead_id, user_id=user_id, text=(text or "").strip())
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def get_lead_comment_by_id(db: AsyncSession, comment_id: int) -> Optional[LeadComment]:
    """Комментарий по ID."""
    result = await db.execute(select(LeadComment).where(LeadComment.id == comment_id))
    return result.scalar_one_or_none()


async def delete_lead_comment(db: AsyncSession, comment_id: int) -> bool:
    """Удалить комментарий по ID."""
    result = await db.execute(select(LeadComment).where(LeadComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment:
        await db.delete(comment)
        await db.commit()
        return True
    return False


# ========== TENANT (multi-tenant) ==========

async def create_tenant(
    db: AsyncSession,
    name: str,
    slug: str,
    default_owner_user_id: Optional[int] = None,
) -> Tenant:
    """Создать tenant."""
    tenant = Tenant(
        name=name,
        slug=slug.strip().lower(),
        default_owner_user_id=default_owner_user_id,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def update_tenant(
    db: AsyncSession,
    tenant_id: int,
    *,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    is_active: Optional[bool] = None,
    default_owner_user_id: Optional[int] = None,
) -> Optional[Tenant]:
    """Обновить tenant."""
    tenant = await get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    if name is not None:
        tenant.name = name
    if slug is not None:
        tenant.slug = slug.strip().lower()
    if is_active is not None:
        tenant.is_active = is_active
    if default_owner_user_id is not None:
        tenant.default_owner_user_id = default_owner_user_id
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def get_tenant_by_id(db: AsyncSession, tenant_id: int) -> Optional[Tenant]:
    """Получить tenant по ID."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def get_tenant_ids_for_user(db: AsyncSession, user_id: int) -> List[int]:
    """Tenant IDs, в которых состоит пользователь (tenant_users). Для доступа к лидам tenant."""
    result = await db.execute(
        select(TenantUser.tenant_id).where(TenantUser.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def create_tenant_user(
    db: AsyncSession,
    tenant_id: int,
    user_id: int,
    role: str = "member",
) -> TenantUser:
    """Добавить пользователя в tenant (multi-user в одном tenant)."""
    tu = TenantUser(tenant_id=tenant_id, user_id=user_id, role=(role or "member").strip() or "member")
    db.add(tu)
    await db.commit()
    await db.refresh(tu)
    return tu


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Optional[Tenant]:
    """Получить tenant по slug."""
    result = await db.execute(select(Tenant).where(Tenant.slug == slug.strip().lower()))
    return result.scalar_one_or_none()


async def list_tenants(db: AsyncSession, active_only: bool = False) -> List[Tenant]:
    """Список tenants."""
    q = select(Tenant).order_by(Tenant.id.asc())
    if active_only:
        q = q.where(Tenant.is_active == True)
    result = await db.execute(q)
    return list(result.scalars().all())


# ========== WHATSAPP ACCOUNT ==========

async def create_whatsapp_account(
    db: AsyncSession,
    tenant_id: int,
    phone_number: str,
    phone_number_id: str,
    verify_token: Optional[str] = None,
    waba_id: Optional[str] = None,
) -> WhatsAppAccount:
    """Привязать WhatsApp номер к tenant."""
    acc = WhatsAppAccount(
        tenant_id=tenant_id,
        phone_number=phone_number,
        phone_number_id=phone_number_id,
        verify_token=verify_token,
        waba_id=waba_id,
    )
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


async def get_whatsapp_account_by_phone_number_id(
    db: AsyncSession, phone_number_id: str
) -> Optional[WhatsAppAccount]:
    """Найти WhatsApp account по phone_number_id (для webhook)."""
    result = await db.execute(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.phone_number_id == str(phone_number_id))
        .where(WhatsAppAccount.is_active == True)
    )
    return result.scalar_one_or_none()


async def list_whatsapp_accounts_by_tenant(
    db: AsyncSession, tenant_id: int
) -> List[WhatsAppAccount]:
    """Список WhatsApp номеров tenant."""
    result = await db.execute(
        select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id).order_by(WhatsAppAccount.id.asc())
    )
    return list(result.scalars().all())


async def delete_whatsapp_account(
    db: AsyncSession, tenant_id: int, whatsapp_id: int
) -> bool:
    """Удалить whatsapp_account по id только если tenant_id совпадает. Возвращает True если удалён."""
    result = await db.execute(
        select(WhatsAppAccount).where(WhatsAppAccount.id == whatsapp_id).where(WhatsAppAccount.tenant_id == tenant_id)
    )
    acc = result.scalar_one_or_none()
    if not acc:
        return False
    await db.delete(acc)
    await db.commit()
    return True


# ========== WhatsApp conversation history (per tenant + wa_from) ==========

async def get_or_create_conversation(
    db: AsyncSession,
    tenant_id: Optional[int],
    phone_number_id: str,
    wa_from: str,
    channel: str = "whatsapp",
) -> Conversation:
    """Получить или создать conversation по (channel, phone_number_id, external_id). Retry on IntegrityError."""
    phone_number_id = str(phone_number_id).strip()
    wa_from = str(wa_from).strip()
    for attempt in range(2):
        result = await db.execute(
            select(Conversation)
            .where(Conversation.channel == channel)
            .where(Conversation.phone_number_id == phone_number_id)
            .where(Conversation.external_id == wa_from)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv
        try:
            conv = Conversation(
                tenant_id=tenant_id,
                channel=channel,
                external_id=wa_from,
                phone_number_id=phone_number_id,
            )
            db.add(conv)
            await db.commit()
            await db.refresh(conv)
            return conv
        except IntegrityError:
            await db.rollback()
            if attempt == 0:
                continue
            raise
    result = await db.execute(
        select(Conversation)
        .where(Conversation.channel == channel)
        .where(Conversation.phone_number_id == phone_number_id)
        .where(Conversation.external_id == wa_from)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise RuntimeError("get_or_create_conversation: race failed")
    return conv


async def get_conversation_message_by_external_id(
    db: AsyncSession, external_message_id: str
) -> Optional[ConversationMessage]:
    """Найти сообщение по external_message_id (для дедупликации ChatFlow)."""
    if not (external_message_id or "").strip():
        return None
    result = await db.execute(
        select(ConversationMessage).where(
            ConversationMessage.external_message_id == external_message_id.strip()
        )
    )
    return result.scalar_one_or_none()


async def add_conversation_message(
    db: AsyncSession,
    conversation_id: int,
    role: str,
    text: str,
    raw_json: Optional[dict] = None,
    external_message_id: Optional[str] = None,
) -> ConversationMessage:
    """Добавить сообщение в conversation (external_message_id для дедупа входящих)."""
    msg = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        text=text or "",
        raw_json=raw_json,
        external_message_id=(external_message_id or "").strip() or None,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_last_messages(
    db: AsyncSession, conversation_id: int, limit: int = 20
) -> List[ConversationMessage]:
    """Последние limit сообщений (по created_at asc для контекста)."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    all_rows = list(result.scalars().all())
    return all_rows[-limit:] if len(all_rows) > limit else all_rows


async def trim_conversation_messages(
    db: AsyncSession, conversation_id: int, keep_last: int = 50
) -> int:
    """Удалить старые сообщения, оставив только последние keep_last. Возвращает число удалённых."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    all_rows = list(result.scalars().all())
    if len(all_rows) <= keep_last:
        return 0
    to_delete = all_rows[: len(all_rows) - keep_last]
    for msg in to_delete:
        await db.delete(msg)
    await db.commit()
    return len(to_delete)


async def create_lead_from_whatsapp(
    db: AsyncSession,
    tenant_id: int,
    message_text: str,
    from_wa_id: Optional[str] = None,
) -> Optional[Lead]:
    """
    Создать лид из webhook WhatsApp. owner_id = tenant.default_owner_user_id;
    если NULL — fallback на первого пользователя с предупреждением в лог.
    """
    tenant = await get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    owner_id = getattr(tenant, "default_owner_user_id", None)
    if owner_id is not None:
        user = await get_user_by_id(db, owner_id)
        if not user:
            owner_id = None
    if owner_id is None:
        print("[WA][WARNING] tenant has no default_owner_user_id, fallback to first user")
        first_user = await get_first_user(db)
        if not first_user:
            return None
        owner_id = first_user.id
    wa_user_id = f"wa_{from_wa_id}" if from_wa_id else "wa_unknown"
    bot_user = await get_or_create_bot_user(db, user_id=wa_user_id, owner_id=owner_id)
    lead = Lead(
        owner_id=owner_id,
        bot_user_id=bot_user.id,
        tenant_id=tenant_id,
        name="WhatsApp",
        phone=from_wa_id or "unknown",
        summary=message_text or "(no text)",
        language="ru",
        status=LeadStatus.NEW,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead
