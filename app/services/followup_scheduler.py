"""
Followup Scheduler Service

Schedule and manage automated followup messages for leads that haven't replied.
"""
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models import LeadFollowup, Lead, Tenant
import logging

log = logging.getLogger(__name__)


async def schedule_followups_for_lead(db: AsyncSession, lead_id: int, tenant_id: int):
    """
    Schedule followup messages for a lead based on tenant's followup_delays_minutes
    
    Args:
        db: Database session
        lead_id: Lead ID
        tenant_id: Tenant ID
        
    Creates followup records with scheduled_at = NOW + delay from tenant settings
    Skips if:
    - handoff_mode='human'
    - Existing pending followups
    """
    try:
        # Get lead
        lead_result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead =lead_result.scalar_one_or_none()
        
        if not lead:
            log.warning("[FOLLOWUP] Lead %s not found, skip scheduling", lead_id)
            return
        
        # Check handoff_mode
        if getattr(lead, 'handoff_mode', 'ai') == 'human':
            log.info("[FOLLOWUP] Lead %s in human mode, skip scheduling", lead_id)
            return
        
        # Check for existing pending followups
        existing_result = await db.execute(
            select(LeadFollowup).where(
                LeadFollowup.lead_id == lead_id,
                LeadFollowup.status == 'pending'
            )
        )
        existing = existing_result.scalars().all()
        
        if existing:
            log.info("[FOLLOWUP] Lead %s already has %d pending followups, skip", lead_id, len(existing))
            return
        
        # Get tenant settings
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        
        if not tenant:
            log.warning("[FOLLOWUP] Tenant %s not found", tenant_id)
            return
        
        followup_enabled = getattr(tenant, 'followup_enabled', True)
        if not followup_enabled:
            log.info("[FOLLOWUP] Tenant %s has followups disabled", tenant_id)
            return
        
        # Get delay sequence
        delays = getattr(tenant, 'followup_delays_minutes', None)
        if not delays:
            delays = [5, 30]  # Default: 5 min, then 30 min later (total 35 min)
        
        if not isinstance(delays, list):
            delays = [5, 30]
        
        # Create followup records
        now = datetime.utcnow()
        cumulative_delay = 0
        
        for i, delay_minutes in enumerate(delays, start=1):
            cumulative_delay += delay_minutes
            scheduled_at = now + timedelta(minutes=cumulative_delay)
            
            followup = LeadFollowup(
                lead_id=lead_id,
                tenant_id=tenant_id,
                scheduled_at=scheduled_at,
                followup_number=i,
                status='pending',
                template_used=None,  # Will be filled when sent
            )
            db.add(followup)
            log.info("[FOLLOWUP] Scheduled followup #%d for lead %s at +%d min", i, lead_id, cumulative_delay)
        
        await db.commit()
        log.info("[FOLLOWUP] Created %d followups for lead %s", len(delays), lead_id)
        
    except Exception as e:
        log.error("[FOLLOWUP] Error scheduling for lead %s: %s", lead_id, type(e).__name__, exc_info=True)
        await db.rollback()


async def cancel_followups_for_lead(db: AsyncSession, lead_id: int):
    """
    Cancel all pending followups for a lead (when user replies or human takes over)
    
    Args:
        db: Database session
        lead_id: Lead ID
    """
    try:
        stmt = (
            update(LeadFollowup)
            .where(
                LeadFollowup.lead_id == lead_id,
                LeadFollowup.status == 'pending'
            )
            .values(status='cancelled')
        )
        
        result = await db.execute(stmt)
        await db.commit()
        
        count = result.rowcount
        if count > 0:
            log.info("[FOLLOWUP] Cancelled %d pending followups for lead %s", count, lead_id)
        
        return count
        
    except Exception as e:
        log.error("[FOLLOWUP] Error cancelling for lead %s: %s", lead_id, type(e).__name__, exc_info=True)
        await db.rollback()
        return 0
