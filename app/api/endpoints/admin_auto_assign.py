"""
CRM v3: правила автоназначения и массовое назначение по диапазону.
Admin/owner/rop только.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin_or_owner_or_rop
from app.database import crud
from app.database.models import User, Lead, LeadStatus
from app.schemas.tenant import AutoAssignRuleCreate, AutoAssignRuleUpdate, AutoAssignRuleResponse
from app.schemas.lead import AssignByRangeBody, AssignByRangeResponse

router = APIRouter()


async def _ensure_tenant_access(db: AsyncSession, current_user: User, tenant_id: int):
    """Проверить что current_user имеет owner/rop в tenant_id."""
    if getattr(current_user, "is_admin", False):
        return
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if tenant and getattr(tenant, "default_owner_user_id", None) == current_user.id:
        return
    role = await crud.get_tenant_user_role(db, tenant_id, current_user.id)
    if role not in ("owner", "rop"):
        raise HTTPException(status_code=403, detail="Owner or ROP access required for this tenant")


@router.get("/tenants/{tenant_id}/auto-assign-rules", response_model=list[AutoAssignRuleResponse])
async def list_auto_assign_rules(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
    active_only: bool = Query(False),
):
    """Список правил автоназначения по tenant."""
    await _ensure_tenant_access(db, current_user, tenant_id)
    rules = await crud.list_auto_assign_rules(db, tenant_id, active_only=active_only)
    return [AutoAssignRuleResponse.model_validate(r) for r in rules]


@router.post("/tenants/{tenant_id}/auto-assign-rules", status_code=201)
async def create_auto_assign_rule(
    tenant_id: int,
    body: AutoAssignRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
):
    """Создать правило автоназначения."""
    await _ensure_tenant_access(db, current_user, tenant_id)
    rule = await crud.create_auto_assign_rule(
        db,
        tenant_id=tenant_id,
        name=body.name,
        is_active=body.is_active,
        priority=body.priority,
        match_city=body.match_city,
        match_language=body.match_language,
        match_object_type=body.match_object_type,
        match_contains=body.match_contains,
        time_from=body.time_from,
        time_to=body.time_to,
        days_of_week=body.days_of_week,
        strategy=body.strategy,
        fixed_user_id=body.fixed_user_id,
    )
    return AutoAssignRuleResponse.model_validate(rule)


@router.patch("/auto-assign-rules/{rule_id}")
async def patch_auto_assign_rule(
    rule_id: int,
    body: AutoAssignRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
):
    """Обновить правило автоназначения (частично)."""
    from app.database.models import AutoAssignRule
    from sqlalchemy import select
    res = await db.execute(select(AutoAssignRule).where(AutoAssignRule.id == rule_id))
    rule = res.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    _ensure_tenant_access(db, current_user, rule.tenant_id)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await crud.update_auto_assign_rule(db, rule_id, rule.tenant_id, **kwargs)
    return AutoAssignRuleResponse.model_validate(updated)


@router.delete("/auto-assign-rules/{rule_id}")
async def delete_auto_assign_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
):
    """Удалить правило автоназначения."""
    from app.database.models import AutoAssignRule
    from sqlalchemy import select
    res = await db.execute(select(AutoAssignRule).where(AutoAssignRule.id == rule_id))
    rule = res.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    _ensure_tenant_access(db, current_user, rule.tenant_id)
    await crud.delete_auto_assign_rule(db, rule_id, rule.tenant_id)
    return {"ok": True}


@router.post("/leads/assign/by-range", response_model=AssignByRangeResponse)
async def assign_by_range(
    body: AssignByRangeBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
):
    """
    Назначить лиды по диапазону индексов (from_index..to_index, 1-based).
    Фильтр: status, only_unassigned. Стратегии: round_robin, fixed_user, custom_map.
    """
    _ensure_tenant_access(db, current_user, body.tenant_id)
    filters = body.filters or {}
    status_filter = (filters.get("status") or "new").strip().lower()
    only_unassigned = filters.get("only_unassigned", True)

    candidates = await crud.get_leads_for_user_crm(db, current_user.id, limit=5000)
    candidates = [l for l in candidates if l.tenant_id == body.tenant_id]
    if status_filter == "new":
        candidates = [l for l in candidates if l.status == LeadStatus.NEW]
    elif status_filter == "in_progress":
        candidates = [l for l in candidates if l.status == LeadStatus.IN_PROGRESS]
    if only_unassigned:
        candidates = [l for l in candidates if not getattr(l, "assigned_user_id", None)]
    candidates.sort(key=lambda x: x.created_at or datetime.min)
    total_selected = len(candidates)
    from_idx = max(0, body.from_index - 1)
    to_idx = min(len(candidates), body.to_index)
    slice_leads = candidates[from_idx:to_idx] if from_idx < to_idx else []

    managers = await crud.get_managers_for_tenant(db, body.tenant_id)
    if not managers:
        return AssignByRangeResponse(ok=True, total_selected=total_selected, assigned=0, skipped=len(slice_leads), details=[{"error": "No managers in tenant"}])

    details = []
    assigned = 0
    for i, lead in enumerate(slice_leads):
        if body.strategy == "fixed_user" and body.fixed_user_id:
            uid = body.fixed_user_id
        elif body.strategy == "custom_map" and body.custom_map:
            idx_in_slice = i
            cum = 0
            uid = None
            for m in body.custom_map:
                count = m.get("count", 0)
                if idx_in_slice < cum + count:
                    uid = m.get("user_id")
                    break
                cum += count
            if uid is None and body.custom_map:
                uid = body.custom_map[-1].get("user_id")
        else:
            uid = managers[i % len(managers)]

        if uid not in managers:
            details.append({"lead_id": lead.id, "error": f"user_id {uid} not in tenant"})
            continue
        now = datetime.utcnow()
        lead.assigned_user_id = uid
        lead.assigned_at = now
        if getattr(lead, "first_assigned_at", None) is None:
            lead.first_assigned_at = now
        await db.flush()
        await crud.create_lead_event(
            db, tenant_id=body.tenant_id, lead_id=lead.id, event_type="assigned",
            actor_user_id=current_user.id, payload={"assigned_to_user_id": uid, "source": "by_range"},
        )
        assigned += 1
        details.append({"lead_id": lead.id, "assigned_to_user_id": uid})

    await db.commit()
    return AssignByRangeResponse(ok=True, total_selected=total_selected, assigned=assigned, skipped=len(slice_leads) - assigned, details=details[:50])