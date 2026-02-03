"""
CRM v2: воронки (pipelines) и стадии. Права: owner/rop/admin — полные; manager — только GET.
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

router = APIRouter(tags=["Pipelines"])


class PipelineStageOut(BaseModel):
    id: int
    pipeline_id: int
    name: str
    order_index: int
    color: Optional[str] = None
    is_closed: bool
    created_at: datetime
    class Config:
        from_attributes = True


class PipelineOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    is_default: bool
    created_at: datetime
    stages: list[PipelineStageOut] = []
    class Config:
        from_attributes = True


class PipelineCreate(BaseModel):
    name: str
    is_default: bool = False


class PipelineUpdate(BaseModel):
    name: Optional[str] = None
    is_default: Optional[bool] = None


class StageCreate(BaseModel):
    name: str
    order_index: Optional[int] = None
    color: Optional[str] = None
    is_closed: bool = False


class StageUpdate(BaseModel):
    name: Optional[str] = None
    order_index: Optional[int] = None
    color: Optional[str] = None
    is_closed: Optional[bool] = None


async def _get_tenant_id(db: AsyncSession, current_user: User, tenant_id: Optional[int]) -> int:
    if tenant_id is not None:
        return tenant_id
    tenant = await crud.get_tenant_for_me(db, current_user.id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
    return tenant.id


def _can_edit(role: Optional[str], is_admin: bool) -> bool:
    return role in ("owner", "rop") or is_admin


@router.get("/pipelines", response_model=dict)
async def list_pipelines(
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список воронок tenant (со стадиями). Manager — read-only."""
    tid = await _get_tenant_id(db, current_user, tenant_id)
    await crud.get_or_create_default_pipeline_for_tenant(db, tid)
    pipelines = await crud.list_pipelines_for_tenant(db, tid)
    out = []
    for p in pipelines:
        stages = [PipelineStageOut.model_validate(s) for s in (p.stages or [])]
        out.append(PipelineOut(id=p.id, tenant_id=p.tenant_id, name=p.name, is_default=p.is_default, created_at=p.created_at, stages=stages))
    return {"pipelines": out, "total": len(out)}


@router.post("/pipelines", response_model=dict)
async def create_pipeline(
    body: PipelineCreate,
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создать воронку. Только owner/rop/admin."""
    tid = await _get_tenant_id(db, current_user, tenant_id)
    role = await crud.get_tenant_user_role(db, tid, current_user.id) if tid else None
    if not _can_edit(role, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner/rop can create pipelines")
    pipeline = await crud.create_pipeline(db, tid, body.name, body.is_default)
    return {"ok": True, "pipeline": PipelineOut(id=pipeline.id, tenant_id=pipeline.tenant_id, name=pipeline.name, is_default=pipeline.is_default, created_at=pipeline.created_at, stages=[])}


@router.patch("/pipelines/{pipeline_id}", response_model=dict)
async def update_pipeline(
    pipeline_id: int,
    body: PipelineUpdate,
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить воронку. owner/rop/admin."""
    tid = await _get_tenant_id(db, current_user, tenant_id)
    role = await crud.get_tenant_user_role(db, tid, current_user.id) if tid else None
    if not _can_edit(role, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner/rop can update pipelines")
    updated = await crud.update_pipeline(db, pipeline_id, tid, name=body.name, is_default=body.is_default)
    if not updated:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"ok": True, "pipeline": PipelineOut(id=updated.id, tenant_id=updated.tenant_id, name=updated.name, is_default=updated.is_default, created_at=updated.created_at, stages=[PipelineStageOut.model_validate(s) for s in (updated.stages or [])])}


@router.post("/pipelines/{pipeline_id}/stages", response_model=dict)
async def create_stage(
    pipeline_id: int,
    body: StageCreate,
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Добавить стадию. owner/rop/admin."""
    tid = await _get_tenant_id(db, current_user, tenant_id)
    role = await crud.get_tenant_user_role(db, tid, current_user.id) if tid else None
    if not _can_edit(role, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner/rop can add stages")
    stage = await crud.create_pipeline_stage(db, pipeline_id, tid, body.name, order_index=body.order_index, color=body.color, is_closed=body.is_closed)
    if not stage:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"ok": True, "stage": PipelineStageOut.model_validate(stage)}


@router.patch("/pipelines/stages/{stage_id}", response_model=dict)
async def update_stage(
  stage_id: int,
  body: StageUpdate,
  tenant_id: Optional[int] = Query(None),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
):
    """Обновить стадию. owner/rop/admin."""
    tid = await _get_tenant_id(db, current_user, tenant_id)
    role = await crud.get_tenant_user_role(db, tid, current_user.id) if tid else None
    if not _can_edit(role, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner/rop can update stages")
    updated = await crud.update_pipeline_stage(db, stage_id, tid, name=body.name, order_index=body.order_index, color=body.color, is_closed=body.is_closed)
    if not updated:
        raise HTTPException(status_code=404, detail="Stage not found")
    return {"ok": True, "stage": PipelineStageOut.model_validate(updated)}


@router.delete("/pipelines/stages/{stage_id}", response_model=dict)
async def delete_stage(
  stage_id: int,
  tenant_id: Optional[int] = Query(None),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
):
    """Удалить стадию. Если есть лиды — 400. owner/rop/admin."""
    tid = await _get_tenant_id(db, current_user, tenant_id)
    role = await crud.get_tenant_user_role(db, tid, current_user.id) if tid else None
    if not _can_edit(role, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner/rop can delete stages")
    ok, msg = await crud.delete_pipeline_stage(db, stage_id, tid)
    if not ok:
        if msg == "not_found":
            raise HTTPException(status_code=404, detail="Stage not found")
        raise HTTPException(status_code=400, detail="Stage has leads, cannot delete")
    return {"ok": True}
