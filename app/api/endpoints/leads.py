"""
Leads API Endpoints

Endpoints for lead management including handoff control.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import logging

from app.api.deps import get_db
from app.database.models import Lead, User
from app.api.dependencies import get_current_user
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
