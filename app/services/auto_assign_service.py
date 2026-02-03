"""
CRM v3: автоназначение лидов по правилам (round_robin, least_loaded, fixed_user).
Timezone Asia/Almaty для проверки time_from/time_to и days_of_week (fallback UTC если tz нет).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import crud
from app.database.models import Lead, AutoAssignRule

try:
    from zoneinfo import ZoneInfo
    _ALMATY = ZoneInfo("Asia/Almaty")
except Exception:
    _ALMATY = None


def _current_almaty_hour() -> int:
    if _ALMATY:
        return datetime.now(_ALMATY).hour
    return datetime.utcnow().hour


def _current_almaty_weekday() -> int:
    """1 = Monday, 7 = Sunday (ISO)."""
    if _ALMATY:
        return datetime.now(_ALMATY).isoweekday()
    return datetime.utcnow().isoweekday()


def _rule_matches_time(rule: AutoAssignRule) -> bool:
    """Проверка времени: time_from/time_to (0-23), days_of_week (1,2,3,4,5 = пн-пт)."""
    hour = _current_almaty_hour()
    if rule.time_from is not None and hour < rule.time_from:
        return False
    if rule.time_to is not None and hour > rule.time_to:
        return False
    if rule.days_of_week:
        parts = [int(x.strip()) for x in str(rule.days_of_week).split(",") if x.strip()]
        if parts and _current_almaty_weekday() not in parts:
            return False
    return True


def _rule_matches_lead(rule: AutoAssignRule, lead: Lead, first_message_text: Optional[str] = None) -> bool:
    """Проверка match_city, match_language, match_object_type, match_contains по лиду."""
    if rule.match_city and (lead.city or "").strip().lower() != rule.match_city.strip().lower():
        return False
    if rule.match_language and (lead.language or "").strip().lower() != rule.match_language.strip().lower():
        return False
    if rule.match_object_type and (lead.object_type or "").strip().lower() != rule.match_object_type.strip().lower():
        return False
    if rule.match_contains:
        sub = rule.match_contains.strip().lower()
        summary = (lead.summary or "").lower()
        first = (first_message_text or "").lower()
        if sub not in summary and sub not in first:
            return False
    return True


async def try_auto_assign(
    db: AsyncSession,
    tenant_id: int,
    lead: Lead,
    first_message_text: Optional[str] = None,
) -> bool:
    """
    Применить автоназначение для лида. Если lead.assigned_user_id уже задан — не трогаем.
    Возвращает True если назначили кого-то.
    """
    if getattr(lead, "assigned_user_id", None) is not None:
        return False
    rules = await crud.list_auto_assign_rules(db, tenant_id, active_only=True)
    managers = await crud.get_managers_for_tenant(db, tenant_id)
    if not managers:
        return False

    for rule in rules:
        if not _rule_matches_time(rule):
            continue
        if not _rule_matches_lead(rule, lead, first_message_text):
            continue

        user_id_to_assign: Optional[int] = None
        if rule.strategy == "fixed_user" and rule.fixed_user_id:
            if rule.fixed_user_id in managers:
                user_id_to_assign = rule.fixed_user_id
        elif rule.strategy == "least_loaded":
            counts = await crud.count_active_leads_by_user(db, tenant_id, days=7)
            best = None
            best_count = None
            for uid in managers:
                c = counts.get(uid, 0)
                if best_count is None or c < best_count:
                    best = uid
                    best_count = c
            if best is not None:
                user_id_to_assign = best
        elif rule.strategy == "round_robin":
            if not managers:
                continue
            idx = (rule.rr_state or 0) % len(managers)
            user_id_to_assign = managers[idx]
            rule.rr_state = (rule.rr_state or 0) + 1
            await db.commit()
            await db.refresh(rule)

        if user_id_to_assign is not None:
            now = datetime.utcnow()
            lead.assigned_user_id = user_id_to_assign
            lead.assigned_at = now
            if getattr(lead, "first_assigned_at", None) is None:
                lead.first_assigned_at = now
            await db.flush()
            await crud.create_lead_event(
                db, tenant_id=tenant_id, lead_id=lead.id, event_type="assigned",
                actor_user_id=None, payload={"auto_assign_rule_id": rule.id, "assigned_to_user_id": user_id_to_assign},
            )
            await db.commit()
            await db.refresh(lead)
            return True

    return False
