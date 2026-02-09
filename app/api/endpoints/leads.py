"""
Leads API Endpoints

Endpoints for lead management including handoff control.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.schemas.tenant_stage import LeadStageUpdateBody
import logging

from app.api.deps import get_db, get_current_user
from app.database.models import Lead, User
from app.services.followup_scheduler import cancel_followups_for_lead, schedule_followups_for_lead

router = APIRouter(prefix="/leads", tags=["leads"])
log = logging.getLogger(__name__)


class HandoffRequest(BaseModel):
    mode: str  # "ai" | "human"


@router.post("/{lead_id}/handoff")
async def set_lead_handoff(
    lead_id: int,
    body: HandoffRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manual handoff: switch between AI and human modes
    
    **Mode: 'human'**:
    - AI stops responding to messages
    - All pending followups cancelled
    - Manager takes over conversation
    
    **Mode: 'ai'**:
    - Resume AI responses
    - Schedule followups if category=no_reply
    """
    mode = body.mode.strip().lower()
    
    if mode not in ('ai', 'human'):
        raise HTTPException(status_code=400, detail="mode must be 'ai' or 'human'")
    
    # Get lead
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Check access (Admin/Owner/ROP/Manager for tenant)
    # For simplicity: require user to be authenticated (extend with tenant check if needed)
    tenant_id = getattr(lead, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Lead has no tenant")
    
    # TODO: Add proper tenant access check via crud or middleware
    # For now: allow if user is authenticated
    
    old_mode = getattr(lead, 'handoff_mode', 'ai')
    
    if old_mode == mode:
        # No change needed
        return {
            "ok": True,
            "lead_id": lead_id,
            "handoff_mode": mode,
            "message": f"Already in {mode} mode"
        }
    
    # Update handoff_mode
    lead.handoff_mode = mode
    
    if mode == 'human':
        # Cancel all pending followups
        cancelled_count = await cancel_followups_for_lead(db, lead_id)
        log.info(f"[HANDOFF] Lead {lead_id}: AI → Human by user {current_user.id}. Cancelled {cancelled_count} followups")
        
        await db.commit()
        
        return {
            "ok": True,
            "lead_id": lead_id,
            "handoff_mode": "human",
            "followups_cancelled": cancelled_count,
            "message": f"Human takeover by user {current_user.username or current_user.id}"
        }
    
    else:  # mode == 'ai'
        # Resume AI mode
        await db.commit()
        
        # Schedule followups if category is no_reply
        category = getattr(lead, 'category', None)
        scheduled = False
        
        if category == 'no_reply':
            try:
                await schedule_followups_for_lead(db, lead_id, tenant_id)
                scheduled = True
                log.info(f"[HANDOFF] Lead {lead_id}: Human → AI. Scheduled followups (category=no_reply)")
            except Exception as e:
                log.error(f"[HANDOFF] Error scheduling followups: {type(e).__name__}")
        
        return {
            "ok": True,
            "lead_id": lead_id,
            "handoff_mode": "ai",
            "followups_scheduled": scheduled,
            "message": "AI resumed" + (" & followups scheduled" if scheduled else "")
        }



@router.patch("/{lead_id}/stage")
async def change_lead_stage(
    lead_id: int,
    body: LeadStageUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Move lead to another stage (Kanban drag & drop).
    
    Validates that:
    1. Lead exists and belongs to user's tenant
    2. Target stage_key exists and is active for that tenant
    """
    from app.database import crud
    from app.database.crud_stages import update_lead_stage, get_tenant_stage_by_key, get_tenant_stage_by_id, get_tenant_stages
    log.info("[LEADS] change_lead_stage lead_id=%s stage_key=%s stage_id=%s user_id=%s", lead_id, getattr(body, "stage_key", None), getattr(body, "stage_id", None), current_user.id)
    
    # 1. Get lead
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=True)
    if not lead:
         raise HTTPException(status_code=404, detail="Lead not found or access denied")
         
    if not lead.tenant_id:
        raise HTTPException(status_code=400, detail="Lead is not associated with a tenant")
        
    # 2. Validate stage exists and is active (stage_key or stage_id)
    stage_key = (getattr(body, "stage_key", None) or "").strip()
    stage_id = getattr(body, "stage_id", None)
    stage = None
    tenant_stages = await get_tenant_stages(db, lead.tenant_id, active_only=True)
    has_tenant_stages = len(tenant_stages) > 0

    if stage_id:
        stage = await get_tenant_stage_by_id(db, stage_id, lead.tenant_id)
        if stage and stage.is_active:
            stage_key = stage.stage_key
        else:
            # Fallback to stage_key if provided
            if stage_key:
                stage = await get_tenant_stage_by_key(db, lead.tenant_id, stage_key)
                if stage and stage.is_active:
                    stage_key = stage.stage_key
                else:
                    if has_tenant_stages:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid stage_key: '{stage_key}' does not exist or is inactive"
                        )
            elif has_tenant_stages:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid stage_id: {stage_id}"
                )
    elif stage_key:
        stage = await get_tenant_stage_by_key(db, lead.tenant_id, stage_key)
        if stage and stage.is_active:
            stage_key = stage.stage_key
        else:
            if has_tenant_stages:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid stage_key: '{stage_key}' does not exist or is inactive"
                )
    else:
        raise HTTPException(status_code=400, detail="stage_id or stage_key is required")

    # If tenant has no stages configured, allow any non-empty stage_key (frontend defaults)
    if not has_tenant_stages and not stage_key:
        raise HTTPException(status_code=400, detail="stage_key is required when no tenant stages configured")
        
    # 3. Update lead
    success = await update_lead_stage(
        db,
        lead_id=lead.id,
        stage_key=stage_key,
        auto_moved=False, # Manual move
        reason=body.reason or "Manual update via API"
    )
    
    if success:
        await db.refresh(lead)
        return {
            "id": lead.id,
            "stage_key": lead.stage_key,
            "updated_at": lead.updated_at
            # "updated_at": lead.stage_updated_at # if available
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to update lead stage")
