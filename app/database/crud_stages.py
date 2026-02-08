"""
CRUD operations for TenantStage (owner-managed pipeline stages)
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

from app.database.models import TenantStage


async def get_tenant_stages(
    db: AsyncSession,
    tenant_id: int,
    active_only: bool = True
) -> List[TenantStage]:
    """Get all stages for a tenant, sorted by order_index"""
    query = select(TenantStage).where(TenantStage.tenant_id == tenant_id)
    if active_only:
        query = query.where(TenantStage.is_active == True)
    query = query.order_by(TenantStage.order_index.asc())
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_tenant_stage_by_id(
    db: AsyncSession,
    stage_id: int,
    tenant_id: int
) -> Optional[TenantStage]:
    """Get a specific stage by ID (with tenant check)"""
    result = await db.execute(
        select(TenantStage).where(
            TenantStage.id == stage_id,
            TenantStage.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_stage_by_key(
    db: AsyncSession,
    tenant_id: int,
    stage_key: str
) -> Optional[TenantStage]:
    """Get stage by key within tenant"""
    result = await db.execute(
        select(TenantStage).where(
            TenantStage.tenant_id == tenant_id,
            TenantStage.stage_key == stage_key
        )
    )
    return result.scalar_one_or_none()


async def create_tenant_stage(
    db: AsyncSession,
    tenant_id: int,
    stage_key: str,
    title_ru: str,
    title_kz: str,
    order_index: int = 0,
    color: Optional[str] = None
) -> TenantStage:
    """Create a new stage for tenant"""
    # Check for duplicate key
    existing = await get_tenant_stage_by_key(db, tenant_id, stage_key)
    if existing:
        raise IntegrityError("duplicate_key", "Stage with this key already exists", None)
    
    stage = TenantStage(
        tenant_id=tenant_id,
        stage_key=stage_key,
        title_ru=title_ru,
        title_kz=title_kz,
        order_index=order_index,
        color=color,
        is_active=True
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return stage


async def update_tenant_stage(
    db: AsyncSession,
    stage_id: int,
    tenant_id: int,
    *,
    title_ru: Optional[str] = None,
    title_kz: Optional[str] = None,
    order_index: Optional[int] = None,
    color: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[TenantStage]:
    """Update an existing stage"""
    stage = await get_tenant_stage_by_id(db, stage_id, tenant_id)
    if not stage:
        return None
    
    if title_ru is not None:
        stage.title_ru = title_ru
    if title_kz is not None:
        stage.title_kz = title_kz
    if order_index is not None:
        stage.order_index = order_index
    if color is not None:
        stage.color = color
    if is_active is not None:
        stage.is_active = is_active
    
    stage.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(stage)
    return stage


async def bulk_reorder_stages(
    db: AsyncSession,
    tenant_id: int,
    stage_updates: List[dict]  # [{"stage_id": int, "order_index": int}, ...]
) -> int:
    """Bulk update stage order_index values. Returns count updated."""
    updated = 0
    for item in stage_updates:
        stage_id = item.get("stage_id")
        order_index = item.get("order_index")
        
        if stage_id is None or order_index is None:
            continue
        
        stage = await get_tenant_stage_by_id(db, stage_id, tenant_id)
        if stage:
            stage.order_index = order_index
            stage.updated_at = datetime.utcnow()
            updated += 1
    
    if updated:
        await db.commit()
    
    return updated


async def delete_tenant_stage(
    db: AsyncSession,
    stage_id: int,
    tenant_id: int,
    soft_delete: bool = True
) -> bool:
    """Delete or deactivate a stage. Returns True if successful."""
    stage = await get_tenant_stage_by_id(db, stage_id, tenant_id)
    if not stage:
        return False
    
    if soft_delete:
        stage.is_active = False
        stage.updated_at = datetime.utcnow()
        await db.commit()
    else:
        await db.delete(stage)
        await db.commit()
    
    return True


async def update_lead_stage(
    db: AsyncSession,
    lead_id: int,
    stage_key: str,
    auto_moved: bool = False,
    reason: Optional[str] = None
) -> bool:
    """
    Update lead's stage_key and metadata.
    This function is called by both manual updates and AI transitions.
    
    Returns True if update was successful.
    """
    from app.database.models import Lead
    
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    
    if not lead:
        return False
    
    lead.stage_key = stage_key
    lead.stage_updated_at = datetime.utcnow()
    lead.stage_auto_moved = auto_moved
    
    await db.commit()
    return True
