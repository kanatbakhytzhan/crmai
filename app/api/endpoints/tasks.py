"""
CRM v2: задачи по лидам (follow-ups). call / meeting / note.
Права: manager — только свои задачи и свои лиды; owner/rop/admin — по tenant.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.api.deps import get_db, get_current_user
from app.core.config import get_settings
from app.database import crud
from app.database.models import User
from app.services.events_bus import emit as events_emit

router = APIRouter(tags=["Tasks"])


class LeadTaskOut(BaseModel):
    id: int
    lead_id: int
    tenant_id: int
    assigned_to_user_id: int
    type: str
    due_at: datetime
    status: str
    note: Optional[str] = None
    created_at: datetime
    done_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadTaskCreate(BaseModel):
    type: str = "call"  # call | meeting | note
    due_at: datetime
    note: Optional[str] = None
    assigned_to_user_id: Optional[int] = None  # по умолчанию — текущий пользователь


class LeadTaskUpdate(BaseModel):
    status: Optional[str] = None  # open | done | cancelled
    due_at: Optional[datetime] = None
    note: Optional[str] = None


@router.get("/leads/{lead_id}/tasks", response_model=dict)
async def get_lead_tasks(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список задач по лиду. Manager — только если лид назначен ему."""
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.tenant_id is None:
        raise HTTPException(status_code=400, detail="Lead has no tenant")
    role = await crud.get_tenant_user_role(db, lead.tenant_id, current_user.id)
    if role == "manager" and getattr(lead, "assigned_user_id", None) != current_user.id:
        raise HTTPException(status_code=403, detail="Manager can only see tasks for assigned leads")
    tasks = await crud.get_lead_tasks(db, lead_id, tenant_id=lead.tenant_id)
    return {"tasks": [LeadTaskOut.model_validate(t) for t in tasks], "total": len(tasks)}


@router.post("/leads/{lead_id}/tasks", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_lead_task(
    lead_id: int,
    body: LeadTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создать задачу по лиду. owner/rop могут назначить на другого; manager — только на себя или свой лид."""
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead or not lead.tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    role = await crud.get_tenant_user_role(db, lead.tenant_id, current_user.id)
    assigned_to = body.assigned_to_user_id if body.assigned_to_user_id is not None else current_user.id
    if role == "manager":
        if assigned_to != current_user.id:
            raise HTTPException(status_code=403, detail="Manager can only assign tasks to themselves")
        if getattr(lead, "assigned_user_id", None) != current_user.id:
            raise HTTPException(status_code=403, detail="Manager can only add tasks to assigned leads")
    task_type = (body.type or "call").strip().lower()
    if task_type not in ("call", "meeting", "note"):
        task_type = "call"
    task = await crud.create_lead_task(
        db, lead_id=lead_id, tenant_id=lead.tenant_id,
        assigned_to_user_id=assigned_to, task_type=task_type, due_at=body.due_at, note=body.note,
    )
    if not task:
        raise HTTPException(status_code=400, detail="Could not create task")
    try:
        await events_emit("lead_updated", {"lead_id": lead_id, "tenant_id": lead.tenant_id})
    except Exception:
        pass
    return {"ok": True, "task": LeadTaskOut.model_validate(task)}


@router.patch("/leads/tasks/{task_id}", response_model=dict)
async def update_lead_task(
    task_id: int,
    body: LeadTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Изменить задачу: статус, дата, текст. Доступ по тем же правилам (свой лид / tenant)."""
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    task = await crud.get_lead_task_by_id(db, task_id, tenant_id=None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    lead = await crud.get_lead_by_id(db, task.lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    role = await crud.get_tenant_user_role(db, task.tenant_id, current_user.id)
    if role == "manager" and task.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Manager can only edit own tasks")
    if role == "manager" and getattr(lead, "assigned_user_id", None) != current_user.id:
        raise HTTPException(status_code=403, detail="Manager can only edit tasks for assigned leads")
    status_val = (body.status or "").strip().lower() if body.status else None
    if status_val and status_val not in ("open", "done", "cancelled"):
        status_val = None
    updated = await crud.update_lead_task(db, task_id, task.tenant_id, status=status_val, due_at=body.due_at, note=body.note)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        await events_emit("lead_updated", {"lead_id": task.lead_id, "tenant_id": task.tenant_id})
    except Exception:
        pass
    return {"ok": True, "task": LeadTaskOut.model_validate(updated)}


@router.get("/tasks", response_model=dict)
async def list_tasks(
    status: str = Query("open", description="open | done | cancelled"),
    due: Optional[str] = Query(None, description="today | overdue | week"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список задач. Manager — только свои; owner/rop/admin — все по tenant."""
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    tenant = await crud.get_tenant_for_me(db, current_user.id) if multitenant else None
    tid = tenant.id if tenant else None
    role = await crud.get_tenant_user_role(db, tid, current_user.id) if tid else None
    if tid and (role in ("owner", "rop") or getattr(current_user, "is_admin", False)):
        tasks = await crud.get_tasks_for_tenant(db, tid, status=status, due_filter=due, limit=200)
    else:
        tasks = await crud.get_tasks_for_user(db, current_user.id, tenant_id=tid, status=status, due_filter=due, limit=200)
    return {"tasks": [LeadTaskOut.model_validate(t) for t in tasks], "total": len(tasks)}
