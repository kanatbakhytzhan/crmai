"""
Stage Transition Service - AI-driven automatic lead movement across pipeline stages

Uses deterministic rules as priority, falls back to LLM for ambiguous cases.
"""
import logging
from typing import Tuple, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database.models import Lead
from app.database.crud_stages import update_lead_stage
from app.services.field_extraction import calculate_data_completeness
from app.database import crud

log = logging.getLogger(__name__)


async def determine_stage_transition(
    lead: Lead,
    conversation_messages: list,
    intent_data: Dict[str, Any],
    extracted_fields: Dict[str, Any],
    language: str
) -> Tuple[str, str]:
    """
    Determine target stage using deterministic rules first, LLM if needed.
    
    Args:
        lead: Current lead object
        conversation_messages: Recent message history
        intent_data: Detected intents (wants_call, refused, etc.)
        extracted_fields: Structured data from conversation
        language: ru or kz
    
    Returns:
        (target_stage_key, reason)
    
    Priority Rules:
    1. User refused / negative → "lost"
    2. User wants_call intent → "wants_call"
    3. Measurement scheduled → "measurement_scheduled"
    4. Full data (completeness >= 0.7) → "full_data"
    5. Partial data (completeness >= 0.3) → "partial_data"
    6. No user reply after 3 messages → "no_reply"
    7. Default → keep current or "in_work"
    """
    current_stage = lead.stage_key or "no_reply"
    
    # Rule 1: User refused
    if intent_data.get("refused") or intent_data.get("negative"):
        return ("lost", "user_refused_or_negative_intent")
    
    # Rule 2: Wants callback
    if intent_data.get("wants_call") or extracted_fields.get("wants_call"):
        return ("wants_call", "user_requested_callback")
    
    # Rule 3: Measurement scheduled (from extracted fields or calendar)
    if extracted_fields.get("measurement_scheduled") or extracted_fields.get("measurement_date"):
        return ("measurement_scheduled", "measurement_appointment_confirmed")
    
    # Rule 4: Full data check
    completeness = calculate_data_completeness(extracted_fields)
    if completeness >= 0.7:
        return ("full_data", f"data_completeness_{int(completeness*100)}%")
    
    # Rule 5: Partial data
    if completeness >= 0.3:
        # Don't downgrade from full_data to partial_data
        if current_stage not in ["full_data", "measurement_scheduled", "success"]:
            return ("partial_data", f"data_completeness_{int(completeness*100)}%")
    
    # Rule 6: No reply detection (needs conversation analysis)
    if lead.last_outbound_at and lead.last_inbound_at:
        # If last outbound is after last inbound by more than 24h → no_reply
        time_since_inbound = (datetime.utcnow() - lead.last_inbound_at).total_seconds() / 3600
        if time_since_inbound > 24 and lead.last_outbound_at > lead.last_inbound_at:
            # Count outbound messages since last inbound
            if len(conversation_messages) >= 3:
                outbound_count = sum(1 for m in conversation_messages[-3:] if m.get("role") == "assistant")
                if outbound_count >= 2:
                    return ("no_reply", "no_user_response_after_multiple_attempts")
    
    # Rule 7: Default - move to in_work if user engaged
    if current_stage == "no_reply" and lead.last_inbound_at:
        return ("in_work", "user_started_engagement")
    
    # Keep current stage if no transition needed
    return (current_stage, "no_transition_needed")


async def apply_stage_transition(
    db: AsyncSession,
    lead: Lead,
    target_stage_key: str,
    reason: str,
    auto_moved: bool = True
) -> bool:
    """
    Apply stage transition + trigger AmoCRM sync + log event.
    
    Args:
        db: Database session
        lead: Lead to update
        target_stage_key: Target stage key
        reason: Reason for transition (for logging)
        auto_moved: True if AI moved, False if manual
    
    Returns:
        True if transition was applied
    """
    old_stage = lead.stage_key
    
    # No change needed
    if old_stage == target_stage_key:
        return False
    
    # Update lead stage
    success = await update_lead_stage(
        db, 
        lead_id=lead.id,
        stage_key=target_stage_key,
        auto_moved=auto_moved,
        reason=reason
    )
    
    if not success:
        log.error(f"[STAGE] Failed to update lead {lead.id} stage")
        return False
    
    # Refresh lead to get updated fields
    await db.refresh(lead)
    
    # Log event
    if lead.tenant_id:
        try:
            await crud.create_lead_event(
                db,
                tenant_id=lead.tenant_id,
                lead_id=lead.id,
                event_type="stage_changed",
                payload={
                    "old_stage": old_stage,
                    "new_stage": target_stage_key,
                    "reason": reason,
                    "auto_moved": auto_moved
                }
            )
        except Exception as e:
            log.error(f"[STAGE] Failed to log stage event: {e}", exc_info=True)
    
    log.info(
        f"[STAGE] Lead {lead.id}: {old_stage or 'null'} → {target_stage_key} "
        f"(reason={reason}, auto={auto_moved})"
    )
    
    # Trigger AmoCRM sync (if integration enabled)
    if lead.tenant_id:
        try:
            from app.services.amocrm_service import AmoCRMService
            
            tenant = await crud.get_tenant_by_id(db, lead.tenant_id)
            if tenant:
                amo = AmoCRMService(db)
                sync_result = await amo.sync_lead_to_amocrm_by_stage(lead, tenant)
                
                if sync_result.get("ok"):
                    log.info(f"[AMO_SYNC] Lead {lead.id} synced to AmoCRM after stage change")
                else:
                    log.warning(f"[AMO_SYNC] Failed for lead {lead.id}: {sync_result.get('reason')}")
        except Exception as e:
            # Never crash on AmoCRM errors
            log.error(f"[AMO_SYNC] Error syncing lead {lead.id}: {e}", exc_info=True)
    
    return True


async def should_cancel_followups(lead: Lead, new_stage_key: str) -> bool:
    """
    Determine if followups should be cancelled based on new stage.
    
    Terminal stages (no followups needed):
    - success (deal won)
    - lost (deal lost)
    - measurement_scheduled (next action scheduled)
    - wants_call with human handoff
    """
    terminal_stages = ["success", "lost", "measurement_scheduled"]
    
    if new_stage_key in terminal_stages:
        return True
    
    # Cancel if wants_call and handoff_mode is human
    if new_stage_key == "wants_call" and lead.handoff_mode == "human":
        return True
    
    return False
