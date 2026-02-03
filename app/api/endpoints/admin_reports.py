"""
CRM v3: отчёты для ROP/Owner — конверсия, нагрузка, SLA.
GET /api/admin/reports/summary, workload, sla. Только admin/owner/rop.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin_or_owner_or_rop
from app.database import crud
from app.database.models import User

router = APIRouter()


async def _resolve_tenant_id(db: AsyncSession, current_user: User, tenant_id: int | None) -> int:
    tid = tenant_id
    if tid is None:
        tenant = await crud.get_tenant_for_me(db, current_user.id)
        if not tenant:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="tenant_id required when user has no tenant")
        return tenant.id
    return tid


@router.get("/reports/summary", summary="Сводка: лиды, конверсия, скорость реакции, менеджеры")
async def reports_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
    tenant_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """
    Сводный отчёт по tenant: total_leads, new/in_progress/done/cancelled,
    avg_time_to_assign_sec, avg_time_to_first_response_sec, conversion_rate_done,
    список менеджеров с нагрузкой и средней скоростью ответа.
    """
    tid = await _resolve_tenant_id(db, current_user, tenant_id)
    df = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    try:
        data = await crud.report_summary(db, tid, date_from=df, date_to=dt)
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": True, "total_leads": 0, "new_leads": 0, "in_progress": 0, "done": 0, "cancelled": 0, "avg_time_to_assign_sec": 0, "avg_time_to_first_response_sec": 0, "conversion_rate_done": 0, "managers": [], "error": str(e)[:200]}


@router.get("/reports/workload", summary="Нагрузка по менеджерам")
async def reports_workload(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
    tenant_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """Таблица: менеджер, assigned, unassigned, active, done, cancelled."""
    tid = await _resolve_tenant_id(db, current_user, tenant_id)
    df = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    try:
        data = await crud.report_workload(db, tid, date_from=df, date_to=dt)
        return {"ok": True, "workload": data}
    except Exception as e:
        return {"ok": True, "workload": [], "error": str(e)[:200]}


@router.get("/reports/sla", summary="SLA: скорость первого ответа, проблемные лиды")
async def reports_sla(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
    tenant_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """Распределение по времени до первого ответа (under_5m, under_15m, under_1h, over_1h) и список лидов с ответом >1ч."""
    tid = await _resolve_tenant_id(db, current_user, tenant_id)
    df = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    try:
        data = await crud.report_sla(db, tid, date_from=df, date_to=dt)
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": True, "under_5m": 0, "under_15m": 0, "under_1h": 0, "over_1h": 0, "problem_leads": [], "error": str(e)[:200]}
