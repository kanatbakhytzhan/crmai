"""
API endpoints for tenant stage management (owner-managed pipelines)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import logging

from app.database.session import get_async_session
from app.api.dependencies import get_current_user
from app.database.models import User
from app.database import crud
from app.database.crud_stages import (
    get_tenant_stages,
    get_tenant_stage_by_id,
    create_tenant_stage,
    update_tenant_stage,
    bulk_reorder_stages,
    delete_tenant_stage
)
from app.schemas.tenant_stage import (
    TenantStageCreate,
    TenantStageUpdate,
    TenantStageResponse,
    TenantStagesResponse,
    TenantStageReorderBody
)

router = APIRouter(prefix="/tenants", tags=["tenant_stages"])
log = logging.getLogger(__name__)


async def require_owner_rop(db: AsyncSession, tenant_id: int, current_user: User):
    """Check if user is owner or ROP for the tenant. Raises HTTPException if not."""
    role = await crud.get_tenant_user_role(db, tenant_id, current_user.id)
    
    if role not in ("owner", "rop"):
        # Also check if user is default_owner
        tenant = await crud.get_tenant_by_id(db, tenant_id)
        if not tenant or tenant.default_owner_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant owner or ROP can manage stages"
            )


@router.get("/{tenant_id}/stages", response_model=TenantStagesResponse)
async def list_tenant_stages(
    tenant_id: int,
    active_only: bool = True,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get all stages for a tenant (Kanban columns).
    
    Query params:
    - active_only: if True, only return active stages (default: True)
    
    Returns stages sorted by order_index.
    """
    # Check if user has access to this tenant
    role = await crud.get_tenant_user_role(db, tenant_id, current_user.id)
    if not role:
        # Check default_owner
        tenant = await crud.get_tenant_by_id(db, tenant_id)
        if not tenant or tenant.default_owner_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this tenant"
            )
    
    stages = await get_tenant_stages(db, tenant_id, active_only=active_only)
    
    return TenantStagesResponse(
        ok=True,
        stages=[TenantStageResponse.model_validate(s) for s in stages],
        total=len(stages)
    )


@router.post("/{tenant_id}/stages", response_model=TenantStageResponse, status_code=status.HTTP_201_CREATED)
async def create_stage(
    tenant_id: int,
    body: TenantStageCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new stage for the tenant (owner/ROP only).
    
    Body:
    - key: unique stage identifier (e.g. "custom_stage")
    - title_ru: Russian display name
    - title_kz: Kazakh display name
    - order_index: display order (optional, default: 0)
    - color: hex color code (optional)
    """
    await require_owner_rop(db, tenant_id, current_user)
    
    try:
        stage = await create_tenant_stage(
            db,
            tenant_id=tenant_id,
            key=body.key,
            title_ru=body.title_ru,
            title_kz=body.title_kz,
            order_index=body.order_index,
            color=body.color
        )
        log.info(f"[STAGE] Created stage key={body.key} for tenant={tenant_id} by user={current_user.id}")
        return TenantStageResponse.model_validate(stage)
    
    except IntegrityError as e:
        log.warning(f"[STAGE] Duplicate key={body.key} for tenant={tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stage with key '{body.key}' already exists for this tenant"
        )


@router.put("/{tenant_id}/stages/{stage_id}", response_model=TenantStageResponse)
async def update_stage(
    tenant_id: int,
    stage_id: int,
    body: TenantStageUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing stage (owner/ROP only).
    
    Body (all fields optional):
    - title_ru: update Russian title
    - title_kz: update Kazakh title
    - order_index: change display order
    - color: change color
    - is_active: activate/deactivate stage
    
    Note: Cannot change 'key' as it's used by AI rules.
    """
    await require_owner_rop(db, tenant_id, current_user)
    
    stage = await update_tenant_stage(
        db,
        stage_id=stage_id,
        tenant_id=tenant_id,
        title_ru=body.title_ru,
        title_kz=body.title_kz,
        order_index=body.order_index,
        color=body.color,
        is_active=body.is_active
    )
    
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage with ID {stage_id} not found for tenant {tenant_id}"
        )
    
    log.info(f"[STAGE] Updated stage id={stage_id} for tenant={tenant_id} by user={current_user.id}")
    return TenantStageResponse.model_validate(stage)


@router.put("/{tenant_id}/stages/reorder", response_model=dict)
async def reorder_stages(
    tenant_id: int,
    body: TenantStageReorderBody,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk reorder stages (owner/ROP only).
    
    Body:
    - stages: array of {stage_id: int, order_index: int}
    
    Example:
    ```
    {
      "stages": [
        {"stage_id": 1, "order_index": 0},
        {"stage_id": 2, "order_index": 1},
        {"stage_id": 3, "order_index": 2}
      ]
    }
    ```
    
    Returns: {ok: true, updated: N}
    """
    await require_owner_rop(db, tenant_id, current_user)
    
    stage_updates = [{"stage_id": item.stage_id, "order_index": item.order_index} for item in body.stages]
    updated_count = await bulk_reorder_stages(db, tenant_id, stage_updates)
    
    log.info(f"[STAGE] Reordered {updated_count} stages for tenant={tenant_id} by user={current_user.id}")
    return {"ok": True, "updated": updated_count}


@router.delete("/{tenant_id}/stages/{stage_id}", response_model=dict)
async def deactivate_stage(
    tenant_id: int,
    stage_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """
    Soft-delete a stage (owner/ROP only).
    
    Sets is_active = false instead of hard delete to preserve data integrity.
    Leads in this stage will remain but the stage won't appear in UI.
    
    Returns: {ok: true, message: "..."}
    """
    await require_owner_rop(db, tenant_id, current_user)
    
    success = await delete_tenant_stage(db, stage_id, tenant_id, soft_delete=True)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage with ID {stage_id} not found for tenant {tenant_id}"
        )
    
    log.info(f"[STAGE] Deactivated stage id={stage_id} for tenant={tenant_id} by user={current_user.id}")
    return {"ok": True, "message": f"Stage {stage_id} deactivated successfully"}
