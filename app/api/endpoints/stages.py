"""
API endpoints for stage management (Pipeline Builder)
Matches frontend spec: /api/stages and /api/tenants/me/stages
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import logging

from app.api.deps import get_current_user
from app.api.deps import get_db
from app.database.models import User, TenantUser
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

router = APIRouter()
log = logging.getLogger(__name__)


async def get_user_tenant_id(db: AsyncSession, user: User) -> int:
    """Helper to get user's tenant ID"""
    # 1. Check if user is created by a tenant (e.g. invited) - usually via TenantUser
    # We take the first active tenant found for the user
    query = select(TenantUser).where(TenantUser.user_id == user.id)
    result = await db.execute(query)
    tenant_user = result.scalars().first()
    
    if not tenant_user:
        # Check if user is a default owner of a tenant
        from app.database.models import Tenant
        query = select(Tenant).where(
            Tenant.default_owner_user_id == user.id,
            Tenant.is_active == True
        )
        result = await db.execute(query)
        tenant = result.scalars().first()
        if tenant:
            return tenant.id
            
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not associated with any active tenant"
        )
        
    return tenant_user.tenant_id


async def require_stage_manage_access(db: AsyncSession, user: User, tenant_id: int):
    """Ensure user is owner/admin/ROP"""
    role = await crud.get_tenant_user_role(db, tenant_id, user.id)
    
    # Allow owner, rop, admin
    if role not in ("owner", "rop", "admin"):
        # Check if default owner
        from app.database.models import Tenant
        tenant = await crud.get_tenant_by_id(db, tenant_id)
        if not tenant or tenant.default_owner_user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin/owner can manage stages"
            )


# 1. GET /api/tenants/me/stages
@router.get("/tenants/me/stages", response_model=TenantStagesResponse)
async def list_my_stages(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all stages for current user's tenant"""
    tenant_id = await get_user_tenant_id(db, current_user)
    stages = await get_tenant_stages(db, tenant_id, active_only=active_only)
    
    return TenantStagesResponse(
        ok=True,
        stages=[TenantStageResponse.model_validate(s) for s in stages],
        total=len(stages)
    )


# 2. POST /api/stages
@router.post("/stages", response_model=TenantStageResponse, status_code=status.HTTP_201_CREATED)
async def create_new_stage(
    body: TenantStageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new stage"""
    tenant_id = await get_user_tenant_id(db, current_user)
    await require_stage_manage_access(db, current_user, tenant_id)
    
    # Check limit (e.g. 20 stages)
    all_stages = await get_tenant_stages(db, tenant_id, active_only=True)
    if len(all_stages) >= 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 20 active stages allowed"
        )
    
    try:
        stage = await create_tenant_stage(
            db,
            tenant_id=tenant_id,
            stage_key=body.stage_key,
            title_ru=body.title_ru,
            title_kz=body.title_kz,
            order_index=body.order_index,
            color=body.color
        )
        log.info(f"[STAGE] Created {body.stage_key} for tenant {tenant_id}")
        return TenantStageResponse.model_validate(stage)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stage key '{body.stage_key}' already exists for this tenant"
        )


# 3. PUT /api/stages/{id}
@router.put("/stages/{stage_id}", response_model=TenantStageResponse)
async def update_existing_stage(
    stage_id: int,
    body: TenantStageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update stage"""
    tenant_id = await get_user_tenant_id(db, current_user)
    await require_stage_manage_access(db, current_user, tenant_id)
    
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
        raise HTTPException(status_code=404, detail="Stage not found or access denied")
        
    return TenantStageResponse.model_validate(stage)


# 4. PUT /api/stages/reorder
@router.put("/stages/reorder", response_model=dict)
async def reorder_pipeline_stages(
    body: TenantStageReorderBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """bulk reorder"""
    tenant_id = await get_user_tenant_id(db, current_user)
    await require_stage_manage_access(db, current_user, tenant_id)
    
    stage_updates = [{"stage_id": item.stage_id, "order_index": item.order_index} for item in body.stages]
    count = await bulk_reorder_stages(db, tenant_id, stage_updates)
    
    return {"success": True, "updated_count": count}


# 5. DELETE /api/stages/{id}
@router.delete("/stages/{stage_id}")
async def archive_stage(
    stage_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Archive stage (soft delete)"""
    tenant_id = await get_user_tenant_id(db, current_user)
    await require_stage_manage_access(db, current_user, tenant_id)
    
    # Check if leads exist
    if not force:
        from app.database.models import Lead, TenantStage
        stage = await get_tenant_stage_by_id(db, stage_id, tenant_id)
        if not stage:
             raise HTTPException(status_code=404, detail="Stage not found")
             
        # Count leads in this stage
        query = select(Lead).where(
            Lead.tenant_id == tenant_id, 
            Lead.stage_key == stage.stage_key
        )
        result = await db.execute(query)
        leads_count = len(result.scalars().all())
        
        if leads_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot archive stage with {leads_count} active leads. Please move leads first."
            )
            
    success = await delete_tenant_stage(db, stage_id, tenant_id, soft_delete=True)
    if not success:
        raise HTTPException(status_code=404, detail="Stage not found")
        
    return {"success": True, "archived_stage_id": stage_id}
