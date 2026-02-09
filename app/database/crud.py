"""
CRUD операции для работы с базой данных (Async)
"""
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta

from app.database.models import (
    User, BotUser, Message, Lead, LeadStatus, LeadComment, LeadEvent, AutoAssignRule,
    Tenant, TenantUser, WhatsAppAccount, TenantIntegration, TenantPipelineMapping, TenantFieldMapping,
    Conversation, ConversationMessage, ChatMute, ChatAIState,
    Pipeline, PipelineStage, LeadTask,
    AIChatMute, AuditLog, Notification,
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


async def count_active_admins(db: AsyncSession, exclude_user_id: Optional[int] = None) -> int:
    """Количество активных админов (is_active=True, is_admin=True). exclude_user_id — не учитывать этого пользователя."""
    q = select(User).where(User.is_active == True).where(User.is_admin == True)
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    result = await db.execute(q)
    return len(list(result.scalars().all()))


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

async def get_bot_user_by_id(db: AsyncSession, bot_user_id: int) -> Optional[BotUser]:
    """Получить клиента бота по id (для lead -> remote_jid)."""
    result = await db.execute(select(BotUser).where(BotUser.id == bot_user_id))
    return result.scalar_one_or_none()


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

async def backfill_lead_numbers(db: AsyncSession) -> int:
    """
    Проставить lead_number всем лидам, где lead_number IS NULL.
    Группировка по tenant_id (если есть), иначе по owner_id. Внутри группы — по created_at ASC (1, 2, 3, ...).
    Учитывает уже существующие номера в группе (max+1, max+2, ...).
    Возвращает количество обновлённых лидов.
    """
    result = await db.execute(
        select(Lead).where(Lead.lead_number.is_(None)).order_by(Lead.created_at.asc())
    )
    null_leads = list(result.scalars().all())
    if not null_leads:
        return 0
    # Группа: (tenant_id,) если tenant есть, иначе (None, owner_id)
    from collections import defaultdict
    groups = defaultdict(list)
    for lead in null_leads:
        key = (lead.tenant_id,) if lead.tenant_id is not None else (None, lead.owner_id)
        groups[key].append(lead)
    updated = 0
    for key, group_leads in groups.items():
        # Существующий max в этой группе (лиды с уже проставленным lead_number)
        if key[0] is not None:
            tenant_id = key[0]
            max_q = select(func.coalesce(func.max(Lead.lead_number), 0)).where(Lead.tenant_id == tenant_id)
        else:
            owner_id = key[1]
            max_q = select(func.coalesce(func.max(Lead.lead_number), 0)).where(
                and_(Lead.owner_id == owner_id, Lead.tenant_id.is_(None))
            )
        res = await db.execute(max_q)
        start = (res.scalar_one() or 0) + 1
        for i, lead in enumerate(group_leads):
            lead.lead_number = start + i
            updated += 1
    if updated:
        await db.commit()
        for lead in null_leads:
            await db.refresh(lead)
    return updated


async def get_next_lead_number(
    db: AsyncSession,
    *,
    tenant_id: Optional[int] = None,
    owner_id: int,
) -> int:
    """
    Следующий порядковый номер лида в рамках tenant (или owner): max(lead_number)+1.
    Уникальность: по tenant_id если задан, иначе по owner_id (tenant_id IS NULL).
    """
    if tenant_id is not None:
        q = select(func.coalesce(func.max(Lead.lead_number), 0) + 1).where(Lead.tenant_id == tenant_id)
    else:
        q = select(func.coalesce(func.max(Lead.lead_number), 0) + 1).where(
            and_(Lead.owner_id == owner_id, Lead.tenant_id.is_(None))
        )
    result = await db.execute(q)
    return result.scalar_one() or 1


async def create_lead_event(
    db: AsyncSession,
    tenant_id: int,
    lead_id: int,
    event_type: str,
    actor_user_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> LeadEvent:
    """CRM v3: записать событие по лиду (created, assigned, first_response, ...)."""
    ev = LeadEvent(
        tenant_id=tenant_id,
        lead_id=lead_id,
        type=event_type,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


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
    area: str = "",
    tenant_id: Optional[int] = None,
    lead_number: Optional[int] = None,
    source: Optional[str] = None,
    external_source: Optional[str] = None,
    external_id: Optional[str] = None,
) -> Lead:
    """Создать новую заявку (лид). tenant_id опционален. lead_number — автоматически (max+1 в рамках tenant/owner), если не передан. CRM v3: source, external_source, external_id."""
    if lead_number is None:
        lead_number = await get_next_lead_number(db, tenant_id=tenant_id, owner_id=owner_id)
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
        status=LeadStatus.NEW,
        tenant_id=tenant_id,
        lead_number=lead_number,
        source=source,
        external_source=external_source,
        external_id=external_id,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    if tenant_id:
        await apply_default_pipeline_to_lead(db, lead)
        await create_lead_event(
            db, tenant_id=tenant_id, lead_id=lead.id, event_type="created",
            payload={"source": source or "manual"},
        )
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
    try:
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
    except Exception:
        # Fallback if tenant tables are missing or inconsistent
        result = await db.execute(
            select(Lead)
            .where(Lead.owner_id == owner_id)
            .order_by(Lead.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_leads_for_user_crm(
    db: AsyncSession,
    user_id: int,
    limit: int = 1000,
) -> List[Lead]:
    """
    Лиды для CRM с учётом ролей: owner/rop — все лиды tenant; manager — только где assigned_user_id = user_id.
    Плюс лиды по owner_id (legacy).
    """
    candidates = await get_user_leads(
        db, owner_id=user_id, limit=limit, multitenant_include_tenant_leads=True
    )
    filtered = []
    for lead in candidates:
        if lead.tenant_id is None:
            filtered.append(lead)
            continue
        try:
            role = await get_tenant_user_role(db, lead.tenant_id, user_id)
        except Exception:
            role = None
        if role in ("owner", "rop"):
            filtered.append(lead)
        elif role == "manager":
            if getattr(lead, "assigned_user_id", None) == user_id:
                filtered.append(lead)
        else:
            # Fallbacks for users missing tenant_users record
            if getattr(lead, "assigned_user_id", None) == user_id:
                filtered.append(lead)
            elif lead.owner_id == user_id:
                filtered.append(lead)
    return filtered


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
        role = await get_tenant_user_role(db, lead.tenant_id, owner_id)
        if role in ("owner", "rop"):
            return lead
        if role == "manager":
            return lead if getattr(lead, "assigned_user_id", None) == owner_id else None
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


async def update_lead_assignment(
    db: AsyncSession,
    lead_id: int,
    current_user_id: int,
    assigned_user_id: Optional[int],
    status: Optional[LeadStatus] = None,
    *,
    multitenant_include_tenant_leads: bool = False,
) -> Optional[Lead]:
    """
    Назначить лид (owner/rop). Manager не может назначать (вызывающий должен проверить роль).
    assigned_user_id должен быть в tenant_users того же tenant. Lead должен принадлежать tenant.
    CRM v3: first_assigned_at при первом назначении, lead_event assigned/unassigned.
    """
    lead = await get_lead_by_id(db, lead_id, current_user_id, multitenant_include_tenant_leads=multitenant_include_tenant_leads)
    if not lead or not lead.tenant_id:
        return None
    role = await get_tenant_user_role(db, lead.tenant_id, current_user_id)
    if role not in ("owner", "rop"):
        return None
    prev_assigned = getattr(lead, "assigned_user_id", None)
    lead.assigned_user_id = assigned_user_id
    if status is not None:
        lead.status = status
    if assigned_user_id is not None:
        target_in_tenant = await get_tenant_user(db, lead.tenant_id, assigned_user_id)
        if not target_in_tenant:
            return None
        now = datetime.utcnow()
        lead.assigned_at = now
        if getattr(lead, "first_assigned_at", None) is None:
            lead.first_assigned_at = now
        await db.flush()
        await create_lead_event(
            db, tenant_id=lead.tenant_id, lead_id=lead_id, event_type="assigned",
            actor_user_id=current_user_id, payload={"assigned_to_user_id": assigned_user_id},
        )
    else:
        lead.assigned_at = None
        await db.flush()
        await create_lead_event(
            db, tenant_id=lead.tenant_id, lead_id=lead_id, event_type="unassigned",
            actor_user_id=current_user_id, payload={"previous_assigned_user_id": prev_assigned},
        )
    await db.refresh(lead)
    return lead


async def bulk_assign_leads(
    db: AsyncSession,
    lead_ids: List[int],
    assigned_user_id: int,
    current_user_id: int,
    set_status: Optional[LeadStatus] = None,
    *,
    multitenant_include_tenant_leads: bool = False,
) -> tuple[int, int, List[int]]:
    """
    Массовое назначение. Возвращает (assigned_count, skipped_count, skipped_ids).
    Лиды не из tenant пользователя или без прав — пропуск.
    """
    assigned = 0
    skipped_ids = []
    for lid in lead_ids:
        lead = await get_lead_by_id(db, lid, current_user_id, multitenant_include_tenant_leads=multitenant_include_tenant_leads)
        if not lead or not lead.tenant_id:
            skipped_ids.append(lid)
            continue
        role = await get_tenant_user_role(db, lead.tenant_id, current_user_id)
        if role not in ("owner", "rop"):
            skipped_ids.append(lid)
            continue
        target_in_tenant = await get_tenant_user(db, lead.tenant_id, assigned_user_id)
        if not target_in_tenant:
            skipped_ids.append(lid)
            continue
        lead.assigned_user_id = assigned_user_id
        lead.assigned_at = datetime.utcnow()
        if set_status is not None:
            lead.status = set_status
        assigned += 1
    if assigned:
        await db.commit()
    return assigned, len(skipped_ids), skipped_ids


async def leads_selection(
    db: AsyncSession,
    user_id: int,
    filters: dict,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = 500,
) -> tuple[List[int], int]:
    """
    CRM v2.5: отбор лидов по фильтрам. Видимость по get_leads_for_user_crm.
    filters: status[], stage_id[], assigned (any|none|mine), city, date_from, date_to, search.
    Возвращает (lead_ids, total).
    """
    candidates = await get_leads_for_user_crm(db, user_id, limit=5000)
    status_list = filters.get("status")
    if isinstance(status_list, list):
        statuses = [s.strip().lower() for s in status_list if s]
        status_enum = []
        for s in statuses:
            if s in ("new",): status_enum.append(LeadStatus.NEW)
            elif s in ("in_progress",): status_enum.append(LeadStatus.IN_PROGRESS)
            elif s in ("done", "success",): status_enum.append(LeadStatus.DONE)
            elif s in ("cancelled", "failed",): status_enum.append(LeadStatus.CANCELLED)
        if status_enum:
            candidates = [l for l in candidates if l.status in status_enum]
    stage_ids = filters.get("stage_id")
    if isinstance(stage_ids, list) and stage_ids:
        stage_set = set(int(x) for x in stage_ids if x is not None)
        if stage_set:
            candidates = [l for l in candidates if getattr(l, "stage_id", None) in stage_set]
    assigned = filters.get("assigned")
    if assigned == "none":
        candidates = [l for l in candidates if not getattr(l, "assigned_user_id", None)]
    elif assigned == "mine":
        candidates = [l for l in candidates if getattr(l, "assigned_user_id", None) == user_id]
    city = (filters.get("city") or "").strip()
    if city:
        candidates = [l for l in candidates if (l.city or "").strip().lower() == city.lower()]
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from or date_to:
        try:
            if date_from:
                df = datetime.fromisoformat(str(date_from).replace("Z", "+00:00")) if isinstance(date_from, str) else date_from
                candidates = [l for l in candidates if l.created_at and l.created_at >= df]
            if date_to:
                dt = datetime.fromisoformat(str(date_to).replace("Z", "+00:00")) if isinstance(date_to, str) else date_to
                candidates = [l for l in candidates if l.created_at and l.created_at <= dt]
        except Exception:
            pass
    search = (filters.get("search") or "").strip()
    if search:
        search_lower = search.lower()
        candidates = [
            l for l in candidates
            if search_lower in (l.name or "").lower() or search_lower in (l.phone or "").lower()
            or search_lower in (l.summary or "").lower() or search_lower in (l.city or "").lower()
        ]
    total = len(candidates)
    reverse = (direction or "desc").strip().lower() == "desc"
    if (sort or "created_at").strip().lower() == "assigned_at":
        candidates.sort(key=lambda l: (getattr(l, "assigned_at") or datetime.min), reverse=reverse)
    else:
        candidates.sort(key=lambda l: l.created_at or datetime.min, reverse=reverse)
    limited = candidates[: limit]
    return [l.id for l in limited], total


async def assign_plan_execute(
    db: AsyncSession,
    lead_ids: List[int],
    plans: List[dict],
    mode: str,
    current_user_id: int,
    set_status: Optional[LeadStatus] = None,
    dry_run: bool = False,
) -> tuple[Optional[List[dict]], Optional[int], Optional[List[str]]]:
    """
    CRM v2.5: распределение по плану. mode=by_ranges: plans=[{manager_user_id, from_index, to_index}] (1-based).
    Возвращает (preview_list, assigned_count, errors). При dry_run — (preview, None, None).
    """
    from app.database.models import LeadStatus
    multitenant = True
    visible = []
    for lid in lead_ids:
        lead = await get_lead_by_id(db, lid, current_user_id, multitenant_include_tenant_leads=True)
        if lead and lead.tenant_id:
            role = await get_tenant_user_role(db, lead.tenant_id, current_user_id)
            if role in ("owner", "rop"):
                visible.append(lead)
            elif role == "manager" and getattr(lead, "assigned_user_id", None) == current_user_id:
                visible.append(lead)
        elif lead and lead.owner_id == current_user_id:
            visible.append(lead)
    visible_ids = [l.id for l in visible]
    sorted_ids = sorted(visible_ids)
    preview = []
    errors = []
    assigned = 0
    if mode == "by_ranges":
        for plan in plans:
            manager_user_id = plan.get("manager_user_id")
            if not manager_user_id:
                errors.append("manager_user_id required")
                continue
            from_idx = int(plan.get("from_index", 0)) - 1
            to_idx = int(plan.get("to_index", 0))
            if from_idx < 0 or to_idx > len(sorted_ids) or from_idx >= to_idx:
                errors.append(f"Invalid range from_index={from_idx+1} to_index={to_idx} for plan manager={manager_user_id}")
                continue
            slice_ids = sorted_ids[from_idx:to_idx]
            tenant_id = None
            for lead_id in slice_ids:
                lead = await get_lead_by_id(db, lead_id, current_user_id, multitenant_include_tenant_leads=True)
                if not lead or not lead.tenant_id:
                    errors.append(f"Lead {lead_id} not found or no tenant")
                    continue
                tenant_id = lead.tenant_id
                tu = await get_tenant_user(db, lead.tenant_id, manager_user_id)
                if not tu or not getattr(tu, "is_active", True):
                    errors.append(f"User {manager_user_id} not in tenant or inactive")
                    continue
                preview.append({"lead_id": lead_id, "to_manager_id": manager_user_id})
                if not dry_run:
                    lead.assigned_user_id = manager_user_id
                    lead.assigned_at = datetime.utcnow()
                    if set_status is not None:
                        lead.status = set_status
                    assigned += 1
    if not dry_run and assigned:
        await db.commit()
    if dry_run:
        return preview, None, (errors if errors else None)
    return None, assigned, (errors if errors else None)


async def update_lead_fields(
    db: AsyncSession,
    lead_id: int,
    current_user_id: int,
    *,
    status: Optional[LeadStatus] = None,
    next_call_at: Optional[datetime] = None,
    last_contact_at: Optional[datetime] = None,
    assigned_user_id: Optional[int] = None,
    multitenant_include_tenant_leads: bool = False,
) -> Optional[Lead]:
    """
    PATCH лида. owner/rop: могут менять status, next_call_at, assigned_user_id.
    manager: только status и next_call_at для своих лидов (assigned_user_id = current_user_id).
    CRM v3: при смене статуса на in_progress — первый «касание» менеджера: first_response_at + lead_event.
    """
    lead = await get_lead_by_id(db, lead_id, current_user_id, multitenant_include_tenant_leads=multitenant_include_tenant_leads)
    if not lead:
        return None
    role = None
    if lead.tenant_id:
        role = await get_tenant_user_role(db, lead.tenant_id, current_user_id)
    is_owner_rop = role in ("owner", "rop") or (lead.tenant_id and not role and lead.owner_id == current_user_id)
    if status is not None:
        lead.status = status
        # CRM v3: первый переход в in_progress от manager/rop/owner = first_response
        if status == LeadStatus.IN_PROGRESS and lead.tenant_id and getattr(lead, "first_response_at", None) is None:
            if role in ("owner", "rop", "manager"):
                lead.first_response_at = datetime.utcnow()
                await db.flush()
                await create_lead_event(
                    db, tenant_id=lead.tenant_id, lead_id=lead_id, event_type="first_response",
                    actor_user_id=current_user_id, payload={"trigger": "status_changed"},
                )
    if next_call_at is not None:
        lead.next_call_at = next_call_at
    if last_contact_at is not None:
        lead.last_contact_at = last_contact_at
    if assigned_user_id is not None:
        if not is_owner_rop:
            pass  # manager не может менять назначение
        else:
            if assigned_user_id:
                target_in_tenant = await get_tenant_user(db, lead.tenant_id, assigned_user_id) if lead.tenant_id else None
                if lead.tenant_id and not target_in_tenant:
                    pass
                else:
                    lead.assigned_user_id = assigned_user_id
            else:
                lead.assigned_user_id = None
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


async def update_lead_phone(db: AsyncSession, lead_id: int, phone: str, phone_from_message: Optional[str] = None) -> Optional[Lead]:
    """Обновить телефон лида (для ChatFlow: номер из текста сообщения). Опционально сохранить phone_from_message."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if lead and (phone or "").strip():
        lead.phone = (phone or "").strip()
        if phone_from_message is not None and hasattr(lead, "phone_from_message"):
            lead.phone_from_message = (phone_from_message or "").strip()[:32] or None
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


async def resolve_lead_tenant_id(db: AsyncSession, lead: Lead) -> Optional[int]:
    """
    Попытаться определить tenant_id для лида (если отсутствует).
    Порядок: (a) conversation по remote_jid (lead.bot_user.user_id);
             (b) tenant где default_owner_user_id == lead.owner_id.
    Лёгкие запросы, без тяжёлых операций.
    """
    # (a) remote_jid из bot_user
    bot_user = await get_bot_user_by_id(db, lead.bot_user_id)
    remote_jid = (bot_user.user_id if bot_user else "") or ""
    if (remote_jid or "").strip():
        result = await db.execute(
            select(Conversation)
            .where(Conversation.external_id == remote_jid.strip())
            .where(Conversation.tenant_id.isnot(None))
            .order_by(Conversation.id.desc())
            .limit(1)
        )
        conv = result.scalar_one_or_none()
        if conv and conv.tenant_id:
            return conv.tenant_id
    # (b) tenant по default_owner_user_id
    result = await db.execute(
        select(Tenant).where(Tenant.default_owner_user_id == lead.owner_id).limit(1)
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant.id
    return None


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


async def get_leads_stats(
    db: AsyncSession,
    user_id: int,
) -> dict[str, int]:
    """
    Получить статистику по лидам (counts по статусам) для текущего пользователя.
    Возвращает: {"new": 15, "in_progress": 8, "done": 42, "cancelled": 3, "total": 68}
    """
    leads = await get_leads_for_user_crm(db, user_id, limit=10000)
    stats = {
        "new": 0,
        "in_progress": 0,
        "done": 0,
        "cancelled": 0,
        "total": len(leads),
    }
    for lead in leads:
        status = lead.status
        if hasattr(status, "value"):
            status_str = status.value
        else:
            status_str = str(status) if status else "new"
        
        if status_str == "new":
            stats["new"] += 1
        elif status_str == "in_progress":
            stats["in_progress"] += 1
        elif status_str in ("done", "success"):
            stats["done"] += 1
        elif status_str in ("cancelled", "failed"):
            stats["cancelled"] += 1
    
    return stats


async def get_last_conversation_message(db: AsyncSession, lead_id: int) -> Optional[str]:
    """
    Получить preview последнего сообщения из conversation для лида (для мобильных карточек).
    Возвращает первые 100 символов последнего user-сообщения.
    """
    # Найти лид и его bot_user
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        return None
    
    bot_user = await get_bot_user_by_id(db, lead.bot_user_id)
    if not bot_user:
        return None
    
    remote_jid = bot_user.user_id or ""
    if not remote_jid.strip():
        return None
    
    # Найти conversation
    result = await db.execute(
        select(Conversation)
        .where(Conversation.external_id == remote_jid.strip())
        .order_by(Conversation.id.desc())
        .limit(1)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        return None
    
    # Последнее user-сообщение
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv.id)
        .where(ConversationMessage.role == "user")
        .order_by(ConversationMessage.created_at.desc())
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        return None
    
    text = msg.text or ""
    return text[:100] if len(text) > 100 else text
async def create_lead_comment(
    db: AsyncSession,
    lead_id: int,
    user_id: int,
    text: str,
) -> LeadComment:
    """Добавить комментарий к лиду. CRM v3: при первом комментарии менеджера/rop/owner выставляет first_response_at и создаёт lead_event first_response."""
    comment = LeadComment(lead_id=lead_id, user_id=user_id, text=(text or "").strip())
    db.add(comment)
    await db.flush()
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if lead and lead.tenant_id:
        if getattr(lead, "first_response_at", None) is None:
            role = await get_tenant_user_role(db, lead.tenant_id, user_id)
            if role in ("owner", "rop", "manager"):
                lead.first_response_at = datetime.utcnow()
                await db.flush()
                await create_lead_event(
                    db, tenant_id=lead.tenant_id, lead_id=lead_id, event_type="first_response",
                    actor_user_id=user_id, payload={"comment_id": comment.id},
                )
        await create_lead_event(
            db, tenant_id=lead.tenant_id, lead_id=lead_id, event_type="comment_added",
            actor_user_id=user_id, payload={"comment_id": comment.id},
        )
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


# ========== LEAD CATEGORIES ==========

async def get_lead_categories(
    db: AsyncSession,
    tenant_id: int,
    active_only: bool = True
) -> List["LeadCategory"]:
    """Получить все категории для tenant."""
    from app.database.models import LeadCategory
    query = select(LeadCategory).where(LeadCategory.tenant_id == tenant_id)
    if active_only:
        query = query.where(LeadCategory.is_active == True)
    query = query.order_by(LeadCategory.order_index, LeadCategory.id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_lead_category_by_key(
    db: AsyncSession,
    tenant_id: int,
    key: str
) -> Optional["LeadCategory"]:
    """Получить категорию по ключу."""
    from app.database.models import LeadCategory
    result = await db.execute(
        select(LeadCategory).where(
            LeadCategory.tenant_id == tenant_id,
            LeadCategory.key == key
        )
    )
    return result.scalar_one_or_none()


async def create_or_update_lead_category(
    db: AsyncSession,
    tenant_id: int,
    key: str,
    label: str,
    color: Optional[str] = None,
    order_index: int = 0
) -> "LeadCategory":
    """Создать или обновить категорию."""
    from app.database.models import LeadCategory
    
    # Проверить, существует ли категория
    category = await get_lead_category_by_key(db, tenant_id, key)
    
    if category:
        # Обновить существующую
        category.label = label
        if color is not None:
            category.color = color
        category.order_index = order_index
        category.updated_at = datetime.utcnow()
    else:
        # Создать новую
        category = LeadCategory(
            tenant_id=tenant_id,
            key=key,
            label=label,
            color=color,
            order_index=order_index
        )
        db.add(category)
    
    await db.commit()
    await db.refresh(category)
    return category


async def update_lead_category_key(
    db: AsyncSession,
    lead_id: int,
    category_key: str,
    current_user_id: int,
    *,
    multitenant_include_tenant_leads: bool = True
) -> Optional[Lead]:
    """
    Обновить категорию лида и синхронизировать с AmoCRM.
    
    1. Проверить, что категория существует у tenant
    2. Обновить поля category_* в лиде
    3. Создать lead_event
    4. Синхронизировать с AmoCRM (если интеграция активна)
    """
    # Получить лид
    lead = await get_lead_by_id(
        db, lead_id=lead_id, owner_id=current_user_id,
        multitenant_include_tenant_leads=multitenant_include_tenant_leads
    )
    if not lead:
        return None
    
    # Проверить tenant_id
    tenant_id = lead.tenant_id
    if not tenant_id:
        # Для старых лидов без tenant_id, попробовать определить
        tenant_id = await infer_tenant_id_for_lead(db, lead)
    
    if not tenant_id:
        # Если tenant_id не найден, просто обновить category_key
        lead.category_key = category_key
        lead.category_label = None
        lead.category_color = None
        lead.category_order = None
        await db.commit()
        await db.refresh(lead)
        return lead
    
    # Получить категорию
    category = await get_lead_category_by_key(db, tenant_id, category_key)
    if not category:
        # Категория не найдена - ошибка валидации
        return None
    
    # Обновить поля лида
    old_category = lead.category_key
    lead.category_key = category.key
    lead.category_label = category.label
    lead.category_color = category.color
    lead.category_order = category.order_index
    
    await db.flush()
    
    # Создать lead_event
    if old_category != category_key:
        await create_lead_event(
            db, tenant_id=tenant_id, lead_id=lead_id,
            event_type="category_changed",
            actor_user_id=current_user_id,
            payload={
                "old_category": old_category,
                "new_category": category_key
            }
        )
    
    await db.commit()
    await db.refresh(lead)
    
    # TODO: Синхронизировать с AmoCRM (вызвать amocrm_service)
    # await sync_lead_category_to_amocrm(db, lead, category_key)
    
    return lead


async def seed_default_categories(
    db: AsyncSession,
    tenant_id: int
):
    """Создать дефолтные категории для нового tenant."""
    DEFAULT_CATEGORIES = [
        {"key": "new", "label": "Новый", "color": "#3B82F6", "order": 0},
        {"key": "hot", "label": "Горячий", "color": "#EF4444", "order": 1},
        {"key": "warm", "label": "Теплый", "color": "#F59E0B", "order": 2},
        {"key": "cold", "label": "Холодный", "color": "#6B7280", "order": 3},
        {"key": "need_call", "label": "Нужен звонок", "color": "#8B5CF6", "order": 4},
        {"key": "postponed", "label": "Отложен", "color": "#EC4899", "order": 5},
        {"key": "not_target", "label": "Не целевой", "color": "#64748B", "order": 6},
    ]
    
    for cat_data in DEFAULT_CATEGORIES:
        await create_or_update_lead_category(
            db, tenant_id=tenant_id,
            key=cat_data["key"],
            label=cat_data["label"],
            color=cat_data["color"],
            order_index=cat_data["order"]
        )


# ========== PIPELINES & STAGES (CRM v2) ==========

DEFAULT_PIPELINE_NAME = "Основная"
DEFAULT_STAGES = [
    ("Новые", False),
    ("В работе", False),
    ("Договорились", False),
    ("Замер/Встреча", False),
    ("Смета отправлена", False),
    ("Успешно (closed won)", True),
    ("Отказ (closed lost)", True),
]


async def get_or_create_default_pipeline_for_tenant(db: AsyncSession, tenant_id: int):
    """Вернуть default pipeline tenant; если нет — создать «Основная» и стадии."""
    result = await db.execute(
        select(Pipeline).where(Pipeline.tenant_id == tenant_id).where(Pipeline.is_default == True).limit(1)
    )
    pipeline = result.scalar_one_or_none()
    if pipeline:
        return pipeline
    pipeline = Pipeline(tenant_id=tenant_id, name=DEFAULT_PIPELINE_NAME, is_default=True)
    db.add(pipeline)
    await db.flush()
    for i, (name, is_closed) in enumerate(DEFAULT_STAGES):
        stage = PipelineStage(pipeline_id=pipeline.id, name=name, order_index=i, is_closed=is_closed)
        db.add(stage)
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def get_default_pipeline_first_stage(db: AsyncSession, tenant_id: int):
    """Вернуть (default pipeline, первая стадия «Новые») для tenant. Для новых лидов."""
    pipeline = await get_or_create_default_pipeline_for_tenant(db, tenant_id)
    if not pipeline:
        return None, None
    result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_id == pipeline.id)
        .order_by(PipelineStage.order_index.asc())
        .limit(1)
    )
    stage = result.scalar_one_or_none()
    return pipeline, stage


async def apply_default_pipeline_to_lead(db: AsyncSession, lead: Lead) -> None:
    """Если у лида есть tenant_id и нет stage_id — поставить default pipeline и стадию «Новые»."""
    if not getattr(lead, "tenant_id", None) or getattr(lead, "stage_id", None):
        return
    pipeline, stage = await get_default_pipeline_first_stage(db, lead.tenant_id)
    if pipeline and stage:
        lead.pipeline_id = pipeline.id
        lead.stage_id = stage.id
        lead.moved_to_stage_at = datetime.utcnow()
        await db.commit()
        await db.refresh(lead)


async def list_pipelines_for_tenant(db: AsyncSession, tenant_id: int) -> List[Pipeline]:
    """Список воронок tenant с подгрузкой стадий."""
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.tenant_id == tenant_id)
        .order_by(Pipeline.id.asc())
        .options(selectinload(Pipeline.stages))
    )
    return list(result.scalars().all())


async def get_pipeline_by_id(db: AsyncSession, pipeline_id: int, tenant_id: int) -> Optional[Pipeline]:
    """Воронка по ID с проверкой tenant."""
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == pipeline_id).where(Pipeline.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_pipeline(db: AsyncSession, tenant_id: int, name: str, is_default: bool = False) -> Pipeline:
    """Создать воронку. Если is_default — снять default с остальных."""
    pipeline = Pipeline(tenant_id=tenant_id, name=(name or "").strip() or DEFAULT_PIPELINE_NAME, is_default=is_default)
    db.add(pipeline)
    await db.flush()
    if is_default:
        await db.execute(
            select(Pipeline).where(Pipeline.tenant_id == tenant_id).where(Pipeline.id != pipeline.id)
        )
        for p in (await db.execute(select(Pipeline).where(Pipeline.tenant_id == tenant_id).where(Pipeline.id != pipeline.id))).scalars().all():
            p.is_default = False
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def update_pipeline(
    db: AsyncSession, pipeline_id: int, tenant_id: int, name: Optional[str] = None, is_default: Optional[bool] = None
) -> Optional[Pipeline]:
    """Обновить воронку."""
    pipeline = await get_pipeline_by_id(db, pipeline_id, tenant_id)
    if not pipeline:
        return None
    if name is not None:
        pipeline.name = (name or "").strip() or pipeline.name
    if is_default is not None and is_default:
        for p in await list_pipelines_for_tenant(db, tenant_id):
            p.is_default = p.id == pipeline_id
        pipeline.is_default = True
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def get_pipeline_stage_by_id(db: AsyncSession, stage_id: int, tenant_id: int) -> Optional[PipelineStage]:
    """Стадия по ID с проверкой через pipeline.tenant_id."""
    result = await db.execute(
        select(PipelineStage)
        .join(Pipeline, PipelineStage.pipeline_id == Pipeline.id)
        .where(PipelineStage.id == stage_id)
        .where(Pipeline.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_pipeline_stage(
    db: AsyncSession, pipeline_id: int, tenant_id: int, name: str, order_index: Optional[int] = None, color: Optional[str] = None, is_closed: bool = False
) -> Optional[PipelineStage]:
    """Добавить стадию в воронку."""
    pipeline = await get_pipeline_by_id(db, pipeline_id, tenant_id)
    if not pipeline:
        return None
    if order_index is None:
        result = await db.execute(
            select(func.coalesce(func.max(PipelineStage.order_index), -1) + 1).where(PipelineStage.pipeline_id == pipeline_id)
        )
        order_index = result.scalar_one() or 0
    stage = PipelineStage(pipeline_id=pipeline_id, name=(name or "").strip() or "Stage", order_index=order_index, color=color, is_closed=is_closed)
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return stage


async def update_pipeline_stage(
    db: AsyncSession, stage_id: int, tenant_id: int,
    name: Optional[str] = None, order_index: Optional[int] = None, color: Optional[str] = None, is_closed: Optional[bool] = None,
) -> Optional[PipelineStage]:
    """Обновить стадию."""
    stage = await get_pipeline_stage_by_id(db, stage_id, tenant_id)
    if not stage:
        return None
    if name is not None:
        stage.name = (name or "").strip() or stage.name
    if order_index is not None:
        stage.order_index = order_index
    if color is not None:
        stage.color = color
    if is_closed is not None:
        stage.is_closed = is_closed
    await db.commit()
    await db.refresh(stage)
    return stage


async def delete_pipeline_stage(db: AsyncSession, stage_id: int, tenant_id: int) -> tuple[bool, str]:
    """Удалить стадию. Если есть лиды на этой стадии — вернуть (False, message)."""
    stage = await get_pipeline_stage_by_id(db, stage_id, tenant_id)
    if not stage:
        return False, "not_found"
    result = await db.execute(select(Lead).where(Lead.stage_id == stage_id).limit(1))
    if result.scalar_one_or_none():
        return False, "stage_has_leads"
    await db.delete(stage)
    await db.commit()
    return True, "ok"


async def move_lead_stage(
    db: AsyncSession, lead_id: int, stage_id: int, current_user_id: int,
    *,
    multitenant_include_tenant_leads: bool = False,
    only_if_assigned_to_me: bool = False,
) -> Optional[Lead]:
    """Переместить лид в стадию. only_if_assigned_to_me: manager может только для своих."""
    lead = await get_lead_by_id(db, lead_id, current_user_id, multitenant_include_tenant_leads=multitenant_include_tenant_leads)
    if not lead or not lead.tenant_id:
        return None
    stage = await get_pipeline_stage_by_id(db, stage_id, lead.tenant_id)
    if not stage:
        return None
    if only_if_assigned_to_me and getattr(lead, "assigned_user_id", None) != current_user_id:
        return None
    if lead.pipeline_id != stage.pipeline_id:
        lead.pipeline_id = stage.pipeline_id
    lead.stage_id = stage_id
    lead.moved_to_stage_at = datetime.utcnow()
    await db.commit()
    await db.refresh(lead)
    return lead


# ========== LEAD TASKS (CRM v2) ==========

async def create_lead_task(
    db: AsyncSession,
    lead_id: int,
    tenant_id: int,
    assigned_to_user_id: int,
    task_type: str,
    due_at: datetime,
    note: Optional[str] = None,
) -> Optional[LeadTask]:
    """Создать задачу по лиду."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id).where(Lead.tenant_id == tenant_id))
    if not result.scalar_one_or_none():
        return None
    task = LeadTask(
        lead_id=lead_id,
        tenant_id=tenant_id,
        assigned_to_user_id=assigned_to_user_id,
        type=(task_type or "call").strip().lower() if task_type else "call",
        due_at=due_at,
        status="open",
        note=(note or "").strip() or None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_lead_tasks(db: AsyncSession, lead_id: int, tenant_id: Optional[int] = None) -> List[LeadTask]:
    """Задачи по лиду (опционально фильтр по tenant)."""
    q = select(LeadTask).where(LeadTask.lead_id == lead_id)
    if tenant_id is not None:
        q = q.where(LeadTask.tenant_id == tenant_id)
    q = q.order_by(LeadTask.due_at.asc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_lead_task_by_id(db: AsyncSession, task_id: int, tenant_id: Optional[int] = None) -> Optional[LeadTask]:
    """Задача по ID."""
    q = select(LeadTask).where(LeadTask.id == task_id)
    if tenant_id is not None:
        q = q.where(LeadTask.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def update_lead_task(
    db: AsyncSession, task_id: int, tenant_id: int,
    status: Optional[str] = None, due_at: Optional[datetime] = None, note: Optional[str] = None,
) -> Optional[LeadTask]:
    """Обновить задачу."""
    task = await get_lead_task_by_id(db, task_id, tenant_id)
    if not task:
        return None
    if status is not None:
        task.status = (status or "").strip().lower() or task.status
        if task.status == "done":
            task.done_at = datetime.utcnow()
        elif task.status != "done":
            task.done_at = None
    if due_at is not None:
        task.due_at = due_at
    if note is not None:
        task.note = (note or "").strip() or None
    await db.commit()
    await db.refresh(task)
    return task


async def get_tasks_for_user(
    db: AsyncSession,
    user_id: int,
    tenant_id: Optional[int] = None,
    status: str = "open",
    due_filter: Optional[str] = None,
    limit: int = 200,
) -> List[LeadTask]:
    """Задачи пользователя. due_filter: today | overdue | week."""
    q = select(LeadTask).where(LeadTask.assigned_to_user_id == user_id).where(LeadTask.status == status)
    if tenant_id is not None:
        q = q.where(LeadTask.tenant_id == tenant_id)
    now = datetime.utcnow()
    if due_filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        q = q.where(LeadTask.due_at >= start).where(LeadTask.due_at < end)
    elif due_filter == "overdue":
        q = q.where(LeadTask.due_at < now)
    elif due_filter == "week":
        end_week = now + timedelta(days=7)
        q = q.where(LeadTask.due_at >= now).where(LeadTask.due_at <= end_week)
    q = q.order_by(LeadTask.due_at.asc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_tasks_for_tenant(
    db: AsyncSession,
    tenant_id: int,
    status: str = "open",
    due_filter: Optional[str] = None,
    limit: int = 200,
) -> List[LeadTask]:
    """Задачи по tenant (для owner/rop: все задачи воронки)."""
    q = select(LeadTask).where(LeadTask.tenant_id == tenant_id).where(LeadTask.status == status)
    now = datetime.utcnow()
    if due_filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        q = q.where(LeadTask.due_at >= start).where(LeadTask.due_at < end)
    elif due_filter == "overdue":
        q = q.where(LeadTask.due_at < now)
    elif due_filter == "week":
        end_week = now + timedelta(days=7)
        q = q.where(LeadTask.due_at >= now).where(LeadTask.due_at <= end_week)
    q = q.order_by(LeadTask.due_at.asc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


# ========== TENANT (multi-tenant) ==========

def _generate_webhook_key() -> str:
    """Случайный ключ для webhook (например secrets.token_urlsafe(16))."""
    import secrets
    return secrets.token_urlsafe(16)


async def create_tenant(
    db: AsyncSession,
    name: str,
    slug: str,
    default_owner_user_id: Optional[int] = None,
    webhook_key: Optional[str] = None,
) -> Tenant:
    """Создать tenant. webhook_key генерируется автоматически, если не передан."""
    key = (webhook_key or "").strip() or _generate_webhook_key()
    tenant = Tenant(
        name=name,
        slug=slug.strip().lower(),
        default_owner_user_id=default_owner_user_id,
        webhook_key=key,
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
    ai_enabled: Optional[bool] = None,
    ai_prompt: Optional[str] = None,
    webhook_key: Optional[str] = None,
    whatsapp_source: Optional[str] = None,
    ai_enabled_global: Optional[bool] = None,
    ai_after_lead_submitted_behavior: Optional[str] = None,
    amocrm_base_domain: Optional[str] = None,
) -> Optional[Tenant]:
    """Обновить tenant. Включает Universal Admin Console поля."""
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
    if ai_enabled is not None:
        tenant.ai_enabled = ai_enabled
    if ai_prompt is not None:
        tenant.ai_prompt = ai_prompt
    if webhook_key is not None:
        tenant.webhook_key = (webhook_key or "").strip() or None
    if whatsapp_source is not None:
        tenant.whatsapp_source = whatsapp_source
    if ai_enabled_global is not None:
        tenant.ai_enabled_global = ai_enabled_global
    if ai_after_lead_submitted_behavior is not None:
        tenant.ai_after_lead_submitted_behavior = ai_after_lead_submitted_behavior
    if amocrm_base_domain is not None:
        # Normalize: strip protocol and trailing slashes
        domain = (amocrm_base_domain or "").strip()
        if domain.startswith("https://"):
            domain = domain[8:]
        elif domain.startswith("http://"):
            domain = domain[7:]
        domain = domain.rstrip("/")
        tenant.amocrm_base_domain = domain if domain else None
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def get_tenant_by_id(db: AsyncSession, tenant_id: int) -> Optional[Tenant]:
    """Получить tenant по ID."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def get_tenant_ids_for_user(db: AsyncSession, user_id: int) -> List[int]:
    """Tenant IDs, в которых состоит пользователь (tenant_users, is_active=True)."""
    q = select(TenantUser.tenant_id).where(TenantUser.user_id == user_id)
    if hasattr(TenantUser, "is_active"):
        q = q.where(TenantUser.is_active == True)
    result = await db.execute(q)
    return [row[0] for row in result.all()]


async def get_tenant_user(
    db: AsyncSession, tenant_id: int, user_id: int
) -> Optional[TenantUser]:
    """Найти связку tenant-user по tenant_id и user_id."""
    result = await db.execute(
        select(TenantUser)
        .where(TenantUser.tenant_id == tenant_id)
        .where(TenantUser.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_tenant_user_role(db: AsyncSession, tenant_id: int, user_id: int) -> Optional[str]:
    """
    Роль пользователя в tenant: owner, rop, manager (или member как manager).
    Если пользователь default_owner tenant — возвращаем "owner". Иначе из tenant_users.
    """
    tenant = await get_tenant_by_id(db, tenant_id)
    if tenant and getattr(tenant, "default_owner_user_id", None) == user_id:
        return "owner"
    tu = await get_tenant_user(db, tenant_id, user_id)
    if not tu or not tu.role:
        return None
    r = (tu.role or "").strip().lower()
    if r in ("owner", "rop", "manager"):
        return r
    if r == "member":
        return "manager"  # member = manager для доступа к лидам
    return r


async def list_tenant_users_with_user(
    db: AsyncSession, tenant_id: int, active_only: bool = False
) -> List[tuple]:
    """Список (TenantUser, User) для tenant. Для GET /api/admin/tenants/{id}/users."""
    q = (
        select(TenantUser, User)
        .join(User, TenantUser.user_id == User.id)
        .where(TenantUser.tenant_id == tenant_id)
    )
    if active_only:
        q = q.where(TenantUser.is_active == True)
    q = q.order_by(TenantUser.id.asc())
    result = await db.execute(q)
    return list(result.all())


async def get_tenant_user_by_id(db: AsyncSession, tenant_user_id: int) -> Optional[TenantUser]:
    """TenantUser по id."""
    result = await db.execute(select(TenantUser).where(TenantUser.id == tenant_user_id))
    return result.scalar_one_or_none()


async def create_tenant_user(
    db: AsyncSession,
    tenant_id: int,
    user_id: int,
    role: str = "member",
    parent_user_id: Optional[int] = None,
    is_active: bool = True,
) -> TenantUser:
    """Добавить пользователя в tenant. Если уже есть — обновить role/parent/is_active и вернуть."""
    existing = await get_tenant_user(db, tenant_id, user_id)
    if existing:
        existing.role = (role or existing.role or "member").strip() or existing.role
        if parent_user_id is not None:
            existing.parent_user_id = parent_user_id
        existing.is_active = is_active
        await db.commit()
        await db.refresh(existing)
        return existing
    tu = TenantUser(
        tenant_id=tenant_id,
        user_id=user_id,
        role=(role or "member").strip() or "member",
        parent_user_id=parent_user_id,
        is_active=is_active,
    )
    db.add(tu)
    await db.commit()
    await db.refresh(tu)
    return tu


async def update_tenant_user(
    db: AsyncSession,
    tenant_user_id: int,
    tenant_id: int,
    role: Optional[str] = None,
    parent_user_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> Optional[TenantUser]:
    """Обновить tenant_user. Проверка tenant_id — запись должна принадлежать tenant."""
    tu = await get_tenant_user_by_id(db, tenant_user_id)
    if not tu or tu.tenant_id != tenant_id:
        return None
    if role is not None:
        tu.role = (role or "").strip() or tu.role
    if parent_user_id is not None:
        tu.parent_user_id = parent_user_id
    if is_active is not None:
        tu.is_active = is_active
    await db.commit()
    await db.refresh(tu)
    return tu


async def delete_tenant_user(
    db: AsyncSession, tenant_id: int, user_id: int
) -> bool:
    """Удалить пользователя из tenant (hard delete). Возвращает True если удалён."""
    tu = await get_tenant_user(db, tenant_id, user_id)
    if not tu:
        return False
    await db.delete(tu)
    await db.commit()
    return True


async def soft_delete_tenant_user(db: AsyncSession, tenant_user_id: int, tenant_id: int) -> bool:
    """Soft delete: is_active=false. Возвращает True если обновлён."""
    tu = await get_tenant_user_by_id(db, tenant_user_id)
    if not tu or tu.tenant_id != tenant_id:
        return False
    tu.is_active = False
    await db.commit()
    await db.refresh(tu)
    return True


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


async def user_has_owner_or_rop_in_any_tenant(db: AsyncSession, user_id: int) -> bool:
    """CRM v3: есть ли у пользователя роль owner или rop в каком-либо tenant (для доступа к Import/Reports/Auto Assign)."""
    # Tenant где default_owner_user_id == user_id
    result = await db.execute(
        select(Tenant.id).where(Tenant.default_owner_user_id == user_id).where(Tenant.is_active == True).limit(1)
    )
    if result.scalar_one_or_none():
        return True
    # tenant_users с role owner или rop
    result = await db.execute(
        select(TenantUser.tenant_id)
        .where(TenantUser.user_id == user_id)
        .where(TenantUser.role.in_(["owner", "rop"]))
        .where(TenantUser.is_active == True)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_tenant_for_me(db: AsyncSession, user_id: int) -> Optional[Tenant]:
    """
    Tenant для текущего пользователя (GET/PATCH /api/me/ai-settings).
    Сначала первый активный tenant из tenant_users; иначе tenant где default_owner_user_id == user_id.
    """
    # 1) tenant_users: первый активный tenant
    tenant_ids = await get_tenant_ids_for_user(db, user_id)
    if tenant_ids:
        result = await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_ids[0])
            .where(Tenant.is_active == True)
        )
        t = result.scalar_one_or_none()
        if t:
            return t
    # 2) fallback: tenant где default_owner_user_id == current_user.id
    result = await db.execute(
        select(Tenant)
        .where(Tenant.default_owner_user_id == user_id)
        .where(Tenant.is_active == True)
        .order_by(Tenant.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ========== WHATSAPP ACCOUNT ==========

async def create_whatsapp_account(
    db: AsyncSession,
    tenant_id: int,
    phone_number: str,
    phone_number_id: Optional[str] = None,
    verify_token: Optional[str] = None,
    waba_id: Optional[str] = None,
    chatflow_token: Optional[str] = None,
    chatflow_instance_id: Optional[str] = None,
    is_active: bool = True,
) -> WhatsAppAccount:
    """Привязать WhatsApp (Meta и/или ChatFlow) к tenant."""
    acc = WhatsAppAccount(
        tenant_id=tenant_id,
        phone_number=(phone_number or "").strip() or "—",
        phone_number_id=(phone_number_id or "").strip() or None,
        verify_token=verify_token,
        waba_id=waba_id,
        chatflow_token=(chatflow_token or "").strip() or None,
        chatflow_instance_id=(chatflow_instance_id or "").strip() or None,
        is_active=is_active,
    )
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


async def get_whatsapp_account_by_phone_number_id(
    db: AsyncSession, phone_number_id: str
) -> Optional[WhatsAppAccount]:
    """Найти WhatsApp account по phone_number_id (для webhook Meta)."""
    if not (phone_number_id or "").strip():
        return None
    result = await db.execute(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.phone_number_id == str(phone_number_id).strip())
        .where(WhatsAppAccount.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_whatsapp_account_by_chatflow_instance_id(
    db: AsyncSession, instance_id: str
) -> Optional[WhatsAppAccount]:
    """Найти WhatsApp account по chatflow_instance_id (для ChatFlow webhook)."""
    if not (instance_id or "").strip():
        return None
    result = await db.execute(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.chatflow_instance_id == str(instance_id).strip())
        .where(WhatsAppAccount.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_tenant_by_webhook_key(db: AsyncSession, webhook_key: str) -> Optional[Tenant]:
    """Tenant по webhook_key (для POST /api/chatflow/webhook/{key})."""
    if not (webhook_key or "").strip():
        return None
    result = await db.execute(
        select(Tenant).where(Tenant.webhook_key == str(webhook_key).strip()).where(Tenant.is_active == True)
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


async def get_chatflow_binding_snapshot(db: AsyncSession, tenant_id: int, include_full_token: bool = False) -> dict:
    """
    Get ChatFlow binding snapshot for tenant settings response.
    
    Returns dict with:
        - binding_exists, is_active, accounts_count
        - phone_number, chatflow_instance_id
        - chatflow_token_masked (always)
        - chatflow_token (only if include_full_token=True, for admin/owner)
    """
    accounts = await list_whatsapp_accounts_by_tenant(db, tenant_id)
    if not accounts:
        return {
            "binding_exists": False,
            "is_active": False,
            "accounts_count": 0,
            "phone_number": None,
            "chatflow_instance_id": None,
            "chatflow_token_masked": None,
            "chatflow_token": None,
        }
    # Get first (or active) account
    acc = next((a for a in accounts if a.is_active), accounts[0])
    token = getattr(acc, "chatflow_token", None) or ""
    instance_id = getattr(acc, "chatflow_instance_id", None) or ""
    
    # Mask token: first 4 chars + *** + last 2 chars
    if len(token) > 6:
        token_masked = token[:4] + "***" + token[-2:]
    elif token:
        token_masked = "***"
    else:
        token_masked = None
    
    result = {
        "binding_exists": True,
        "is_active": acc.is_active,
        "accounts_count": len(accounts),
        "phone_number": acc.phone_number or None,
        "chatflow_instance_id": instance_id or None,
        "chatflow_token_masked": token_masked,
    }
    
    # Include full token only for privileged roles
    if include_full_token:
        result["chatflow_token"] = token if token else None
    else:
        result["chatflow_token"] = None
    
    return result


async def update_whatsapp_account(
    db: AsyncSession,
    account_id: int,
    tenant_id: int,
    *,
    phone_number: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    chatflow_token: Optional[str] = None,
    chatflow_instance_id: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[WhatsAppAccount]:
    """Обновить существующий whatsapp_account. None для token/instance_id = не менять (не затирать)."""
    result = await db.execute(
        select(WhatsAppAccount).where(WhatsAppAccount.id == account_id).where(WhatsAppAccount.tenant_id == tenant_id)
    )
    acc = result.scalar_one_or_none()
    if not acc:
        return None
    if phone_number is not None:
        acc.phone_number = (phone_number or "").strip() or acc.phone_number or "—"
    if phone_number_id is not None:
        acc.phone_number_id = (phone_number_id or "").strip() or None
    if chatflow_token is not None:
        val = (chatflow_token or "").strip()
        if val:
            acc.chatflow_token = val
    if chatflow_instance_id is not None:
        val = (chatflow_instance_id or "").strip()
        if val:
            acc.chatflow_instance_id = val
    if is_active is not None:
        acc.is_active = is_active
    if hasattr(acc, "updated_at"):
        acc.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(acc)
    return acc


async def upsert_whatsapp_for_tenant(
    db: AsyncSession,
    tenant_id: int,
    *,
    phone_number: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    chatflow_token: Optional[str] = None,
    chatflow_instance_id: Optional[str] = None,
    is_active: bool = True,
) -> WhatsAppAccount:
    """
    Если у tenant есть whatsapp_account — обновить (первый по id), иначе создать. Одна запись на tenant.
    
    MERGE SEMANTICS:
    - None for phone_number/token/instance_id = don't update (preserve existing)
    - Non-None values (including "") will update the field
    - Empty string ("") for phone_number defaults to "—" only on CREATE, not on UPDATE
    """
    accounts = await list_whatsapp_accounts_by_tenant(db, tenant_id)
    
    if accounts:
        # UPDATE existing - pass values as-is (None = don't change)
        acc = await update_whatsapp_account(
            db,
            accounts[0].id,
            tenant_id,
            phone_number=phone_number,  # None = keep existing
            phone_number_id=phone_number_id,
            chatflow_token=chatflow_token,
            chatflow_instance_id=chatflow_instance_id,
            is_active=is_active,
        )
        return acc or accounts[0]
    
    # CREATE new - provide defaults for required fields
    phone = (phone_number or "").strip() or "—"
    return await create_whatsapp_account(
        db,
        tenant_id=tenant_id,
        phone_number=phone,  # Default to "—" only on create
        phone_number_id=phone_number_id,
        chatflow_token=chatflow_token,
        chatflow_instance_id=chatflow_instance_id,
        is_active=is_active,
    )


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


async def get_active_chatflow_account_for_tenant(db: AsyncSession, tenant_id: int) -> Optional[WhatsAppAccount]:
    """Есть ли у tenant активный WhatsApp attach с критичными полями (chatflow_token OR chatflow_instance_id)."""
    result = await db.execute(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.tenant_id == tenant_id)
        .where(WhatsAppAccount.is_active == True)
    )
    for acc in result.scalars().all():
        if (getattr(acc, "chatflow_token", None) or "").strip() or (getattr(acc, "chatflow_instance_id", None) or "").strip():
            return acc
    return None


# ========== chat_ai_states (per-chat /stop /start по remoteJid) ==========

async def get_chat_ai_state(db: AsyncSession, tenant_id: int, remote_jid: str) -> bool:
    """AI включён в этом чате. Сначала ai_chat_mutes по chat_key=remote_jid, затем chat_ai_states."""
    if not (remote_jid or "").strip():
        return True
    chat_key = (remote_jid or "").strip()
    # CRM v2.5: ai_chat_mutes (единый источник по chat_key)
    result = await db.execute(
        select(AIChatMute)
        .where(AIChatMute.tenant_id == tenant_id)
        .where(AIChatMute.chat_key == chat_key)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return not row.is_muted
    result = await db.execute(
        select(ChatAIState)
        .where(ChatAIState.tenant_id == tenant_id)
        .where(ChatAIState.remote_jid == chat_key)
    )
    row = result.scalar_one_or_none()
    return row.is_enabled if row else True


async def set_chat_ai_state(db: AsyncSession, tenant_id: int, remote_jid: str, enabled: bool) -> None:
    """Включить/выключить AI в чате. Пишем в ai_chat_mutes (chat_key=remote_jid) и chat_ai_states для совместимости."""
    jid = (remote_jid or "").strip()
    if not jid:
        return
    is_muted = not enabled
    # ai_chat_mutes upsert
    result = await db.execute(
        select(AIChatMute).where(AIChatMute.tenant_id == tenant_id).where(AIChatMute.chat_key == jid)
    )
    row = result.scalar_one_or_none()
    if row:
        row.is_muted = is_muted
        row.muted_at = datetime.utcnow()
        await db.commit()
        await db.refresh(row)
    else:
        row = AIChatMute(tenant_id=tenant_id, chat_key=jid, is_muted=is_muted, muted_at=datetime.utcnow())
        db.add(row)
        await db.commit()
        await db.refresh(row)
    # chat_ai_states для обратной совместимости
    result2 = await db.execute(
        select(ChatAIState).where(ChatAIState.tenant_id == tenant_id).where(ChatAIState.remote_jid == jid)
    )
    r2 = result2.scalar_one_or_none()
    if r2:
        r2.is_enabled = enabled
        r2.updated_at = datetime.utcnow()
        await db.commit()
    else:
        r2 = ChatAIState(tenant_id=tenant_id, remote_jid=jid, is_enabled=enabled)
        db.add(r2)
        await db.commit()


async def get_ai_chat_mute(db: AsyncSession, tenant_id: int, chat_key: str) -> Optional[bool]:
    """Проверить mute по chat_key. Возвращает is_muted (True/False) или None если записи нет."""
    key = (chat_key or "").strip()
    if not key:
        return None
    result = await db.execute(
        select(AIChatMute).where(AIChatMute.tenant_id == tenant_id).where(AIChatMute.chat_key == key)
    )
    row = result.scalar_one_or_none()
    return row.is_muted if row else None


async def set_ai_chat_mute(
    db: AsyncSession,
    tenant_id: int,
    chat_key: str,
    is_muted: bool,
    lead_id: Optional[int] = None,
    muted_by_user_id: Optional[int] = None,
) -> None:
    """Установить mute по chat_key. Upsert в ai_chat_mutes."""
    key = (chat_key or "").strip()
    if not key:
        return
    result = await db.execute(
        select(AIChatMute).where(AIChatMute.tenant_id == tenant_id).where(AIChatMute.chat_key == key)
    )
    row = result.scalar_one_or_none()
    if row:
        row.is_muted = is_muted
        row.lead_id = lead_id
        row.muted_by_user_id = muted_by_user_id
        row.muted_at = datetime.utcnow()
        await db.commit()
        await db.refresh(row)
    else:
        row = AIChatMute(
            tenant_id=tenant_id,
            chat_key=key,
            is_muted=is_muted,
            lead_id=lead_id,
            muted_by_user_id=muted_by_user_id,
            muted_at=datetime.utcnow(),
        )
        db.add(row)
        await db.commit()


# ========== audit_log (CRM v2.5) ==========

async def audit_log_append(
    db: AsyncSession,
    actor_user_id: int,
    action: str,
    tenant_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    """Добавить запись в audit_log."""
    import json
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
    row = AuditLog(tenant_id=tenant_id, actor_user_id=actor_user_id, action=(action or "").strip(), payload_json=payload_json)
    db.add(row)
    await db.commit()


# ========== notifications (CRM v2.5) ==========

async def notification_create(
    db: AsyncSession,
    user_id: int,
    type: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    tenant_id: Optional[int] = None,
    lead_id: Optional[int] = None,
) -> Notification:
    """Создать уведомление."""
    n = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=(type or "").strip(),
        title=(title or "").strip() or None,
        body=(body or "").strip() or None,
        lead_id=lead_id,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def notifications_for_user(
    db: AsyncSession,
    user_id: int,
    unread_only: bool = False,
    limit: int = 100,
) -> List[Notification]:
    """Список уведомлений пользователя."""
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.is_read == False)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def notification_mark_read(db: AsyncSession, notification_id: int, user_id: int) -> bool:
    """Отметить уведомление прочитанным. Только своё."""
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id).where(Notification.user_id == user_id)
    )
    n = result.scalar_one_or_none()
    if not n:
        return False
    n.is_read = True
    await db.commit()
    return True


async def notification_mark_all_read(db: AsyncSession, user_id: int) -> int:
    """Отметить все уведомления пользователя прочитанными. Возвращает количество."""
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id).where(Notification.is_read == False)
    )
    items = list(result.scalars().all())
    for n in items:
        n.is_read = True
    if items:
        await db.commit()
    return len(items)


async def get_tenant_owner_rop_user_ids(db: AsyncSession, tenant_id: int) -> List[int]:
    """User IDs owner и rop в tenant (для рассылки уведомлений о новом лиде)."""
    tenant = await get_tenant_by_id(db, tenant_id)
    ids = []
    if tenant and getattr(tenant, "default_owner_user_id", None):
        ids.append(tenant.default_owner_user_id)
    q = select(TenantUser.user_id).where(TenantUser.tenant_id == tenant_id).where(TenantUser.role.in_(["owner", "rop"]))
    if hasattr(TenantUser, "is_active"):
        q = q.where(TenantUser.is_active == True)
    result = await db.execute(q)
    for row in result.all():
        if row[0] and row[0] not in ids:
            ids.append(row[0])
    return ids


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


async def get_or_create_lead_for_chatflow_jid(
    db: AsyncSession,
    tenant_id: int,
    remote_jid: str,
) -> Optional[Lead]:
    """
    CRM v2.5: при первом сообщении — лид должен существовать. Найти по (tenant + jid) или создать.
    phone_from_jid = jid.split('@')[0]. Backfill tenant_id если у лида null.
    """
    if not (remote_jid or "").strip():
        return None
    tenant = await get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    owner_id = getattr(tenant, "default_owner_user_id", None)
    if owner_id is None:
        first_user = await get_first_user(db)
        if not first_user:
            return None
        owner_id = first_user.id
    bot_user = await get_or_create_bot_user(db, user_id=remote_jid.strip(), owner_id=owner_id)
    active_lead = await get_active_lead_by_bot_user(db, bot_user.id)
    if active_lead:
        if active_lead.tenant_id is None:
            active_lead.tenant_id = tenant_id
            await apply_default_pipeline_to_lead(db, active_lead)
            await db.commit()
            await db.refresh(active_lead)
        return active_lead
    phone_from_jid = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    lead = await create_lead(
        db,
        owner_id=owner_id,
        bot_user_id=bot_user.id,
        name="Unknown",
        phone=phone_from_jid or "unknown",
        summary="",
        language="ru",
        tenant_id=tenant_id,
        source="chatflow",
    )
    try:
        from app.services.auto_assign_service import try_auto_assign
        await try_auto_assign(db, tenant_id, lead, first_message_text=None)
    except Exception:
        pass
    return lead


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
    next_num = await get_next_lead_number(db, tenant_id=tenant_id, owner_id=owner_id)
    lead = Lead(
        owner_id=owner_id,
        bot_user_id=bot_user.id,
        tenant_id=tenant_id,
        name="WhatsApp",
        phone=from_wa_id or "unknown",
        summary=message_text or "(no text)",
        language="ru",
        status=LeadStatus.NEW,
        lead_number=next_num,
        source="whatsapp",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    await apply_default_pipeline_to_lead(db, lead)
    await create_lead_event(db, tenant_id=tenant_id, lead_id=lead.id, event_type="created", payload={"source": "whatsapp"})
    try:
        from app.services.auto_assign_service import try_auto_assign
        await try_auto_assign(db, tenant_id, lead, first_message_text=message_text)
    except Exception:
        pass
    return lead


# ========== CHAT MUTE (per-chat / global mute для WhatsApp/ChatFlow) ==========

def _norm_phone_id(phone_number_id: Optional[str]) -> str:
    """Нормализовать phone_number_id для хранения (пустая строка вместо None)."""
    return (phone_number_id or "").strip()


def _norm_external_id(external_id: Optional[str]) -> str:
    return (external_id or "").strip()


async def set_chat_muted(
    db: AsyncSession,
    channel: str,
    phone_number_id: str,
    external_id: str,
    muted: bool,
    tenant_id: Optional[int] = None,
) -> ChatMute:
    """Upsert mute для одного чата (scope=chat)."""
    channel = (channel or "whatsapp").strip().lower()
    phone_number_id = _norm_phone_id(phone_number_id)
    external_id = _norm_external_id(external_id)
    q = (
        select(ChatMute)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "chat")
        .where(ChatMute.external_id == external_id)
    )
    if tenant_id is not None:
        q = q.where(ChatMute.tenant_id == tenant_id)
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row:
        row.is_muted = muted
        row.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(row)
        return row
    row = ChatMute(
        tenant_id=tenant_id,
        channel=channel,
        phone_number_id=phone_number_id,  # "" для ChatFlow — храним как пустую строку для совпадения в is_muted
        external_id=external_id,
        scope="chat",
        is_muted=muted,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def set_all_muted(
    db: AsyncSession,
    channel: str,
    phone_number_id: str,
    muted: bool,
    tenant_id: Optional[int] = None,
) -> ChatMute:
    """Upsert mute для всех чатов этого phone_number_id (scope=all, external_id='')."""
    channel = (channel or "whatsapp").strip().lower()
    phone_number_id = _norm_phone_id(phone_number_id)
    result = await db.execute(
        select(ChatMute)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "all")
        .where(ChatMute.external_id == "")
    )
    row = result.scalar_one_or_none()
    if row:
        row.is_muted = muted
        row.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(row)
        return row
    row = ChatMute(
        tenant_id=tenant_id,
        channel=channel,
        phone_number_id=phone_number_id,  # "" для ChatFlow
        external_id="",
        scope="all",
        is_muted=muted,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def is_muted(
    db: AsyncSession,
    channel: str,
    phone_number_id: str,
    external_id: str,
) -> bool:
    """
    Правило: если scope=all muted для этого phone_number_id → True.
    Иначе если scope=chat muted для (external_id) → True.
    Иначе False.
    """
    channel = (channel or "whatsapp").strip().lower()
    phone_number_id = _norm_phone_id(phone_number_id)
    external_id = _norm_external_id(external_id)

    # 1) Проверить scope=all
    result = await db.execute(
        select(ChatMute)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "all")
        .where(ChatMute.external_id == "")
    )
    row = result.scalar_one_or_none()
    if row and row.is_muted:
        return True

    # 2) Проверить scope=chat для этого external_id
    result = await db.execute(
        select(ChatMute)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "chat")
        .where(ChatMute.external_id == external_id)
    )
    row = result.scalar_one_or_none()
    if row and row.is_muted:
        return True

    return False


async def get_chat_mute(
    db: AsyncSession,
    tenant_id: int,
    channel: str,
    phone_number_id: str,
    external_id: str,
) -> Optional[ChatMute]:
    """Найти запись mute для одного чата (scope=chat, tenant_id)."""
    channel = (channel or "whatsapp").strip().lower()
    phone_number_id = _norm_phone_id(phone_number_id)
    external_id = _norm_external_id(external_id)
    result = await db.execute(
        select(ChatMute)
        .where(ChatMute.tenant_id == tenant_id)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "chat")
        .where(ChatMute.external_id == external_id)
    )
    return result.scalar_one_or_none()


async def set_chat_mute(
    db: AsyncSession,
    tenant_id: int,
    channel: str,
    phone_number_id: str,
    external_id: str,
    is_muted: bool,
) -> ChatMute:
    """Upsert mute для одного чата (scope=chat) с обязательным tenant_id."""
    return await set_chat_muted(
        db, channel, phone_number_id, external_id, is_muted, tenant_id=tenant_id
    )


async def is_chat_muted(
    db: AsyncSession,
    tenant_id: int,
    channel: str,
    phone_number_id: str,
    external_id: str,
) -> bool:
    """
    Mute только для этого чата в рамках tenant.
    Сначала scope=all для этого (tenant_id, channel, phone_number_id), затем scope=chat.
    """
    channel = (channel or "whatsapp").strip().lower()
    phone_number_id = _norm_phone_id(phone_number_id)
    external_id = _norm_external_id(external_id)

    # 1) scope=all для этого tenant
    result = await db.execute(
        select(ChatMute)
        .where(ChatMute.tenant_id == tenant_id)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "all")
        .where(ChatMute.external_id == "")
    )
    row = result.scalar_one_or_none()
    if row and row.is_muted:
        return True

    # 2) scope=chat для этого чата
    result = await db.execute(
        select(ChatMute)
        .where(ChatMute.tenant_id == tenant_id)
        .where(ChatMute.channel == channel)
        .where(ChatMute.phone_number_id == phone_number_id)
        .where(ChatMute.scope == "chat")
        .where(ChatMute.external_id == external_id)
    )
    row = result.scalar_one_or_none()
    if row and row.is_muted:
        return True

    return False


# ========== CRM v3: Auto Assign Rules ==========

async def get_managers_for_tenant(db: AsyncSession, tenant_id: int, active_only: bool = True) -> List[int]:
    """Список user_id с ролью manager (и member) в tenant для round_robin/least_loaded."""
    q = (
        select(TenantUser.user_id)
        .where(TenantUser.tenant_id == tenant_id)
        .where(TenantUser.role.in_(["manager", "member"]))
    )
    if active_only and hasattr(TenantUser, "is_active"):
        q = q.where(TenantUser.is_active == True)
    result = await db.execute(q)
    return [r[0] for r in result.all()]


async def list_auto_assign_rules(db: AsyncSession, tenant_id: int, active_only: bool = False) -> List[AutoAssignRule]:
    """Правила автоназначения по tenant, сортировка по priority ASC."""
    q = select(AutoAssignRule).where(AutoAssignRule.tenant_id == tenant_id)
    if active_only:
        q = q.where(AutoAssignRule.is_active == True)
    q = q.order_by(AutoAssignRule.priority.asc(), AutoAssignRule.id.asc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_auto_assign_rule_by_id(db: AsyncSession, rule_id: int, tenant_id: int) -> Optional[AutoAssignRule]:
    result = await db.execute(
        select(AutoAssignRule).where(AutoAssignRule.id == rule_id).where(AutoAssignRule.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_auto_assign_rule(
    db: AsyncSession,
    tenant_id: int,
    name: str,
    is_active: bool = True,
    priority: int = 0,
    match_city: Optional[str] = None,
    match_language: Optional[str] = None,
    match_object_type: Optional[str] = None,
    match_contains: Optional[str] = None,
    time_from: Optional[int] = None,
    time_to: Optional[int] = None,
    days_of_week: Optional[str] = None,
    strategy: str = "round_robin",
    fixed_user_id: Optional[int] = None,
    rr_state: int = 0,
) -> AutoAssignRule:
    rule = AutoAssignRule(
        tenant_id=tenant_id,
        name=name,
        is_active=is_active,
        priority=priority,
        match_city=match_city,
        match_language=match_language,
        match_object_type=match_object_type,
        match_contains=match_contains,
        time_from=time_from,
        time_to=time_to,
        days_of_week=days_of_week,
        strategy=strategy,
        fixed_user_id=fixed_user_id,
        rr_state=rr_state,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_auto_assign_rule(
    db: AsyncSession,
    rule_id: int,
    tenant_id: int,
    **kwargs,
) -> Optional[AutoAssignRule]:
    rule = await get_auto_assign_rule_by_id(db, rule_id, tenant_id)
    if not rule:
        return None
    for k, v in kwargs.items():
        if hasattr(rule, k):
            setattr(rule, k, v)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_auto_assign_rule(db: AsyncSession, rule_id: int, tenant_id: int) -> bool:
    rule = await get_auto_assign_rule_by_id(db, rule_id, tenant_id)
    if not rule:
        return False
    await db.delete(rule)
    await db.commit()
    return True


async def count_active_leads_by_user(
    db: AsyncSession,
    tenant_id: int,
    days: int = 7,
) -> dict:
    """Количество активных лидов (NEW/IN_PROGRESS) по assigned_user_id за последние days дней. Для least_loaded."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Lead.assigned_user_id, func.count(Lead.id))
        .where(Lead.tenant_id == tenant_id)
        .where(Lead.status.in_([LeadStatus.NEW, LeadStatus.IN_PROGRESS]))
        .where(Lead.created_at >= since)
        .where(Lead.assigned_user_id.isnot(None))
        .group_by(Lead.assigned_user_id)
    )
    return {r[0]: r[1] for r in result.all()}


async def lead_exists_by_external(db: AsyncSession, tenant_id: int, external_source: str, external_id: str) -> bool:
    """Есть ли уже лид с таким external_source+external_id в tenant (дедупликация импорта)."""
    result = await db.execute(
        select(Lead.id)
        .where(Lead.tenant_id == tenant_id)
        .where(Lead.external_source == external_source)
        .where(Lead.external_id == str(external_id).strip())
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def lead_exists_by_phone_recent(db: AsyncSession, tenant_id: int, phone_normalized: str, days: int = 7) -> bool:
    """Есть ли лид с таким телефоном в tenant за последние days дней (мягкая дедупликация)."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Lead.id)
        .where(Lead.tenant_id == tenant_id)
        .where(Lead.phone == phone_normalized)
        .where(Lead.created_at >= since)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


# ========== CRM v3: Reports ==========

async def report_summary(
    db: AsyncSession,
    tenant_id: int,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> dict:
    """Сводка для tenant: total_leads, new, in_progress, done, cancelled, avg_time_to_assign, avg_time_to_first_response, conversion_rate_done, managers[]."""
    q = select(Lead).where(Lead.tenant_id == tenant_id)
    if date_from:
        q = q.where(Lead.created_at >= date_from)
    if date_to:
        q = q.where(Lead.created_at <= date_to)
    result = await db.execute(q)
    leads = list(result.scalars().all())
    total = len(leads)
    new_c = sum(1 for l in leads if l.status == LeadStatus.NEW)
    in_progress_c = sum(1 for l in leads if l.status == LeadStatus.IN_PROGRESS)
    done_c = sum(1 for l in leads if l.status == LeadStatus.DONE)
    cancelled_c = sum(1 for l in leads if l.status == LeadStatus.CANCELLED)

    assign_times = []
    response_times = []
    for l in leads:
        if getattr(l, "assigned_at", None) and l.created_at:
            assign_times.append((l.assigned_at - l.created_at).total_seconds())
        if getattr(l, "first_response_at", None) and l.created_at:
            response_times.append((l.first_response_at - l.created_at).total_seconds())

    avg_assign = (sum(assign_times) / len(assign_times)) if assign_times else 0
    avg_response = (sum(response_times) / len(response_times)) if response_times else 0
    conversion = (done_c / total) if total else 0

    manager_ids = await get_managers_for_tenant(db, tenant_id)
    managers_list = []
    for uid in manager_ids:
        assigned_count = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid)
        done_count = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid and l.status == LeadStatus.DONE)
        new_count = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid and l.status == LeadStatus.NEW)
        resp_times = [
            (l.first_response_at - l.created_at).total_seconds()
            for l in leads
            if getattr(l, "assigned_user_id", None) == uid and getattr(l, "first_response_at", None) and l.created_at
        ]
        avg_resp = (sum(resp_times) / len(resp_times)) if resp_times else 0
        active_load = sum(
            1 for l in leads
            if getattr(l, "assigned_user_id", None) == uid and l.status in (LeadStatus.NEW, LeadStatus.IN_PROGRESS)
        )
        user = await get_user_by_id(db, uid)
        managers_list.append({
            "user_id": uid,
            "email": user.email if user else None,
            "leads_assigned_count": assigned_count,
            "leads_done_count": done_count,
            "leads_new_count": new_count,
            "avg_response_time_sec": round(avg_resp, 1),
            "active_load": active_load,
        })

    return {
        "total_leads": total,
        "new_leads": new_c,
        "in_progress": in_progress_c,
        "done": done_c,
        "cancelled": cancelled_c,
        "avg_time_to_assign_sec": round(avg_assign, 1),
        "avg_time_to_first_response_sec": round(avg_response, 1),
        "conversion_rate_done": round(conversion, 4),
        "managers": managers_list,
    }


async def report_workload(
    db: AsyncSession,
    tenant_id: int,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list:
    """Таблица по менеджерам: assigned, unassigned (лидов без назначения), active, done, cancelled."""
    q = select(Lead).where(Lead.tenant_id == tenant_id)
    if date_from:
        q = q.where(Lead.created_at >= date_from)
    if date_to:
        q = q.where(Lead.created_at <= date_to)
    result = await db.execute(q)
    leads = list(result.scalars().all())
    manager_ids = await get_managers_for_tenant(db, tenant_id)
    unassigned = sum(1 for l in leads if not getattr(l, "assigned_user_id", None))
    out = []
    out.append({
        "manager_user_id": None,
        "manager_email": "(unassigned)",
        "assigned": 0,
        "unassigned": unassigned,
        "active": 0,
        "done": 0,
        "cancelled": 0,
    })
    for uid in manager_ids:
        assigned = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid)
        active = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid and l.status in (LeadStatus.NEW, LeadStatus.IN_PROGRESS))
        done = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid and l.status == LeadStatus.DONE)
        cancelled = sum(1 for l in leads if getattr(l, "assigned_user_id", None) == uid and l.status == LeadStatus.CANCELLED)
        user = await get_user_by_id(db, uid)
        out.append({
            "manager_user_id": uid,
            "manager_email": user.email if user else None,
            "assigned": assigned,
            "unassigned": 0,
            "active": active,
            "done": done,
            "cancelled": cancelled,
        })
    return out


async def report_sla(
    db: AsyncSession,
    tenant_id: int,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> dict:
    """SLA: распределение time_to_first_response (under_5m, under_15m, under_1h, over_1h) и список проблемных лидов."""
    q = select(Lead).where(Lead.tenant_id == tenant_id).where(Lead.first_response_at.isnot(None))
    if date_from:
        q = q.where(Lead.created_at >= date_from)
    if date_to:
        q = q.where(Lead.created_at <= date_to)
    result = await db.execute(q)
    leads = list(result.scalars().all())
    under_5m = under_15m = under_1h = over_1h = 0
    problem = []
    for l in leads:
        if not getattr(l, "first_response_at", None) or not l.created_at:
            continue
        sec = (l.first_response_at - l.created_at).total_seconds()
        if sec < 300:
            under_5m += 1
        elif sec < 900:
            under_15m += 1
        elif sec < 3600:
            under_1h += 1
        else:
            over_1h += 1
            problem.append({
                "lead_id": l.id,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "assigned_at": l.assigned_at.isoformat() if getattr(l, "assigned_at", None) else None,
                "first_response_at": l.first_response_at.isoformat() if l.first_response_at else None,
                "assigned_to_user_id": getattr(l, "assigned_user_id", None),
            })
    return {
        "under_5m": under_5m,
        "under_15m": under_15m,
        "under_1h": under_1h,
        "over_1h": over_1h,
        "problem_leads": problem[:50],
    }


# ========== UNIVERSAL ADMIN: Tenant Integrations ==========

async def get_tenant_integration(db: AsyncSession, tenant_id: int, provider: str) -> Optional[TenantIntegration]:
    """Получить интеграцию tenant с провайдером."""
    result = await db.execute(
        select(TenantIntegration)
        .where(TenantIntegration.tenant_id == tenant_id)
        .where(TenantIntegration.provider == provider)
    )
    return result.scalar_one_or_none()


async def upsert_tenant_integration(
    db: AsyncSession,
    tenant_id: int,
    provider: str,
    *,
    base_domain: Optional[str] = None,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    token_expires_at: Optional[datetime] = None,
    is_active: Optional[bool] = None,
) -> TenantIntegration:
    """Создать или обновить интеграцию."""
    existing = await get_tenant_integration(db, tenant_id, provider)
    if existing:
        if base_domain is not None:
            existing.base_domain = base_domain
        if access_token is not None:
            existing.access_token = access_token
        if refresh_token is not None:
            existing.refresh_token = refresh_token
        if token_expires_at is not None:
            existing.token_expires_at = token_expires_at
        if is_active is not None:
            existing.is_active = is_active
        existing.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return existing
    integ = TenantIntegration(
        tenant_id=tenant_id,
        provider=provider,
        base_domain=base_domain,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        is_active=is_active if is_active is not None else True,
    )
    db.add(integ)
    await db.commit()
    await db.refresh(integ)
    return integ


async def update_tenant_integration_tokens(
    db: AsyncSession,
    tenant_id: int,
    provider: str,
    access_token: str,
    refresh_token: str,
    token_expires_at: datetime,
) -> bool:
    """Обновить токены интеграции (для авто-refresh)."""
    existing = await get_tenant_integration(db, tenant_id, provider)
    if not existing:
        return False
    existing.access_token = access_token
    existing.refresh_token = refresh_token
    existing.token_expires_at = token_expires_at
    existing.updated_at = datetime.utcnow()
    await db.commit()
    return True


async def deactivate_tenant_integration(db: AsyncSession, tenant_id: int, provider: str) -> bool:
    """Деактивировать интеграцию."""
    existing = await get_tenant_integration(db, tenant_id, provider)
    if not existing:
        return False
    existing.is_active = False
    existing.updated_at = datetime.utcnow()
    await db.commit()
    return True


# ========== UNIVERSAL ADMIN: Pipeline Mappings ==========

async def list_pipeline_mappings(db: AsyncSession, tenant_id: int, provider: str = "amocrm") -> List[TenantPipelineMapping]:
    """Список маппингов stage_key -> stage_id."""
    result = await db.execute(
        select(TenantPipelineMapping)
        .where(TenantPipelineMapping.tenant_id == tenant_id)
        .where(TenantPipelineMapping.provider == provider)
        .order_by(TenantPipelineMapping.stage_key.asc())
    )
    return list(result.scalars().all())


async def upsert_pipeline_mapping(
    db: AsyncSession,
    tenant_id: int,
    provider: str,
    stage_key: str,
    stage_id: Optional[str] = None,
    pipeline_id: Optional[str] = None,
    is_active: bool = True,
) -> TenantPipelineMapping:
    """Создать или обновить маппинг стадии."""
    result = await db.execute(
        select(TenantPipelineMapping)
        .where(TenantPipelineMapping.tenant_id == tenant_id)
        .where(TenantPipelineMapping.provider == provider)
        .where(TenantPipelineMapping.stage_key == stage_key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.stage_id = stage_id
        if pipeline_id is not None:
            existing.pipeline_id = pipeline_id
        existing.is_active = is_active
        await db.commit()
        await db.refresh(existing)
        return existing
    mapping = TenantPipelineMapping(
        tenant_id=tenant_id,
        provider=provider,
        stage_key=stage_key,
        stage_id=stage_id,
        pipeline_id=pipeline_id,
        is_active=is_active,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping


async def get_pipeline_mapping_by_stage_key(db: AsyncSession, tenant_id: int, provider: str, stage_key: str) -> Optional[TenantPipelineMapping]:
    """Получить маппинг по stage_key."""
    result = await db.execute(
        select(TenantPipelineMapping)
        .where(TenantPipelineMapping.tenant_id == tenant_id)
        .where(TenantPipelineMapping.provider == provider)
        .where(TenantPipelineMapping.stage_key == stage_key)
        .where(TenantPipelineMapping.is_active == True)
    )
    return result.scalar_one_or_none()


# ========== UNIVERSAL ADMIN: Field Mappings ==========

async def list_field_mappings(db: AsyncSession, tenant_id: int, provider: str = "amocrm") -> List[TenantFieldMapping]:
    """Список маппингов field_key -> amo_field_id."""
    result = await db.execute(
        select(TenantFieldMapping)
        .where(TenantFieldMapping.tenant_id == tenant_id)
        .where(TenantFieldMapping.provider == provider)
        .order_by(TenantFieldMapping.field_key.asc())
    )
    return list(result.scalars().all())


async def upsert_field_mapping(
    db: AsyncSession,
    tenant_id: int,
    provider: str,
    field_key: str,
    entity_type: str,
    amo_field_id: Optional[str] = None,
    is_active: bool = True,
) -> TenantFieldMapping:
    """Создать или обновить маппинг поля."""
    result = await db.execute(
        select(TenantFieldMapping)
        .where(TenantFieldMapping.tenant_id == tenant_id)
        .where(TenantFieldMapping.provider == provider)
        .where(TenantFieldMapping.field_key == field_key)
        .where(TenantFieldMapping.entity_type == entity_type)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.amo_field_id = amo_field_id
        existing.is_active = is_active
        await db.commit()
        await db.refresh(existing)
        return existing
    mapping = TenantFieldMapping(
        tenant_id=tenant_id,
        provider=provider,
        field_key=field_key,
        entity_type=entity_type,
        amo_field_id=amo_field_id,
        is_active=is_active,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping


# ========== UNIVERSAL ADMIN: Lead Backfill tenant_id ==========

async def backfill_lead_tenant_ids(db: AsyncSession) -> int:
    """
    Безопасный backfill: для лидов без tenant_id попробовать заполнить по conversation.tenant_id или tenant по default_owner_user_id.
    Возвращает количество обновлённых лидов.
    """
    # Лиды без tenant_id
    result = await db.execute(
        select(Lead).where(Lead.tenant_id.is_(None))
    )
    leads_without_tenant = list(result.scalars().all())
    updated = 0
    for lead in leads_without_tenant:
        # Попробовать найти tenant по owner_id
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.default_owner_user_id == lead.owner_id).limit(1)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant:
            lead.tenant_id = tenant.id
            updated += 1
    if updated:
        await db.commit()
    return updated


async def get_conversation_for_bot_user(db: AsyncSession, bot_user_id: int) -> Optional[Conversation]:
    """Последняя conversation по bot_user.user_id (remote_jid)."""
    bot_user = await get_bot_user_by_id(db, bot_user_id)
    if not bot_user:
        return None
    result = await db.execute(
        select(Conversation)
        .where(Conversation.external_id == bot_user.user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def mute_chat_for_lead(
    db: AsyncSession,
    lead_id: int,
    muted: bool,
    muted_by_user_id: Optional[int] = None,
) -> dict:
    """
    Mute/unmute чат для лида. Возвращает {"ok": True/False, "muted": bool, "error": str?}.
    Ищем conversation по lead.bot_user_id. Если нет tenant_id — ошибка.
    """
    lead = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = lead.scalar_one_or_none()
    if not lead:
        return {"ok": False, "error": "lead_not_found"}
    if not lead.tenant_id:
        return {"ok": False, "error": "lead_has_no_tenant_id"}
    conv = await get_conversation_for_bot_user(db, lead.bot_user_id)
    if not conv:
        return {"ok": False, "error": "no_conversation"}
    channel = conv.channel or "chatflow"
    external_id = conv.external_id
    # Upsert в chat_ai_states (главная таблица для /stop /start)
    result = await db.execute(
        select(ChatAIState)
        .where(ChatAIState.tenant_id == lead.tenant_id)
        .where(ChatAIState.remote_jid == external_id)
    )
    state = result.scalar_one_or_none()
    if state:
        state.is_enabled = not muted
        state.updated_at = datetime.utcnow()
    else:
        state = ChatAIState(
            tenant_id=lead.tenant_id,
            remote_jid=external_id,
            is_enabled=not muted,
        )
        db.add(state)
    await db.commit()
    return {"ok": True, "muted": muted, "channel": channel, "external_id": external_id}
