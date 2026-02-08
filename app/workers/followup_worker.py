"""
Followup Worker - Background process for sending automated followups

Runs as separate process or async task. Checks every 60 seconds for pending followups
and sends them via ChatFlow when scheduled_at is reached.
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_session_generator
from app.database.models import LeadFollowup, Lead, Tenant, WhatsAppAccount
from app.services import chatflow_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60


async def process_pending_followup(db: AsyncSession, followup: LeadFollowup):
    """
    Process a single pending followup: check conditions, send message, update status
    
    Args:
        db: Database session
        followup: LeadFollowup instance
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Load related lead and tenant
        lead_result = await db.execute(select(Lead).where(Lead.id == followup.lead_id))
        lead = lead_result.scalar_one_or_none()
        
        if not lead:
            log.warning("[FOLLOWUP] Lead %s not found, cancelling followup %s", followup.lead_id, followup.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Check handoff_mode
        if getattr(lead, 'handoff_mode', 'ai') == 'human':
            log.info("[FOLLOWUP] Lead %s in human mode, cancelling followup %s", lead.id, followup.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Check if user replied after followup was created
        last_inbound = getattr(lead, 'last_inbound_at', None)
        if last_inbound and last_inbound > followup.created_at:
            log.info("[FOLLOWUP] Lead %s replied after followup created, cancelling %s", lead.id, followup.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Load tenant
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == followup.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        
        if not tenant:
            log.warning("[FOLLOWUP] Tenant %s not found, cancelling followup %s", followup.tenant_id, followup.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Check if followup is enabled
        if not getattr(tenant, 'followup_enabled', True):
            log.info("[FOLLOWUP] Tenant %s has followups disabled, cancelling %s", tenant.id, followup.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Get followup template
        lead_language = getattr(lead, 'language', 'ru')
        if lead_language == 'kz':
            template = getattr(tenant, 'followup_template_kz', None)
        else:
            template = getattr(tenant, 'followup_template_ru', None)
        
        if not template:
            # Default template
            if lead_language == 'kz':
                template = "Salem! Sizdiң zhobaңyz usһіn qұnyn eseptep bere alamyz ba?"
            else:
                template = "Здравствуйте! Можем рассчитать стоимость для вашего проекта?"
        
        # Format template with lead data
        lead_name = getattr(lead, 'name', '')
        if lead_name and lead_name != 'Клиент':
            message_text = template.replace('{name}', f', {lead_name}')
        else:
            message_text = template.replace('{name}', '')
        
        # Get remote_jid from bot_user
        bot_user_id = getattr(lead, 'bot_user_id', None)
        if not bot_user_id:
            log.warning("[FOLLOWUP] Lead %s has no bot_user_id", lead.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Get jid from bot_user
        from app.database.models import BotUser
        bot_user_result = await db.execute(select(BotUser).where(BotUser.id == bot_user_id))
        bot_user = bot_user_result.scalar_one_or_none()
        
        if not bot_user:
            log.warning("[FOLLOWUP] BotUser %s not found for lead %s", bot_user_id, lead.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        remote_jid = getattr(bot_user, 'user_id', None)
        if not remote_jid:
            log.warning("[FOLLOWUP] BotUser %s has no user_id", bot_user_id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        # Get ChatFlow credentials from whatsapp_accounts
        acc_result = await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.tenant_id == tenant.id,
                WhatsAppAccount.is_active == True
            ).limit(1)
        )
        acc = acc_result.scalar_one_or_none()
        
        if not acc:
            log.warning("[FOLLOWUP] No active WhatsApp account for tenant %s", tenant.id)
            followup.status = 'cancelled'
            await db.commit()
            return False
        
        token = getattr(acc, 'chatflow_token', None)
        instance_id = getattr(acc, 'chatflow_instance_id', None)
        
        # Send message
        try:
            result = await chatflow_client.send_text(remote_jid, message_text, token=token, instance_id=instance_id)
            
            if result.ok:
                # Success
                followup.status = 'sent'
                followup.sent_at = datetime.utcnow()
                followup.template_used = message_text
                
                # Update lead.last_outbound_at
                lead.last_outbound_at = datetime.utcnow()
                
                await db.commit()
                log.info("[FOLLOWUP] ✅ Sent followup #%d for lead %s", followup.followup_number, lead.id)
                return True
            else:
                log.error("[FOLLOWUP] Failed to send followup %s: %s", followup.id, result.error)
                # Don't cancel, will retry next cycle
                return False
                
        except Exception as e:
            log.error("[FOLLOWUP] Exception sending followup %s: %s", followup.id, type(e).__name__, exc_info=True)
            return False
            
    except Exception as e:
        log.error("[FOLLOWUP] Error processing followup %s: %s", followup.id, type(e).__name__, exc_info=True)
        await db.rollback()
        return False


async def run_followup_worker():
    """
    Main worker loop: check for pending followups every 60 seconds and process them
    Includes retry logic with exponential backoff on database errors
    """
    # Import health module (avoids circular import with API endpoints)
    from app.workers.health import update_tick
    
    log.info("[FOLLOWUP_WORKER] Starting followup worker (checks every 60s)")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            # Update health tick
            update_tick()
            
            async for db in get_async_session_generator():
                now = datetime.utcnow()
                
                # Query pending followups that are due
                stmt = select(LeadFollowup).where(
                    LeadFollowup.status == 'pending',
                    LeadFollowup.scheduled_at <= now
                ).order_by(LeadFollowup.scheduled_at)
                
                result = await db.execute(stmt)
                pending_followups = result.scalars().all()
                
                count = len(pending_followups)
                if count > 0:
                    log.info("[FOLLOWUP WORKER] Found %d pending followups to process", count)
                    
                    for followup in pending_followups:
                        await process_pending_followup(db, followup)
                        # Small delay between sends to avoid rate limiting
                        await asyncio.sleep(1)
                else:
                    log.debug("[FOLLOWUP WORKER] No pending followups at this time")
                
                break  # Exit the async for loop after processing
            
            # Reset error counter on success
            consecutive_errors = 0
                
        except Exception as e:
            consecutive_errors += 1
            log.error(
                "[FOLLOWUP WORKER] Error in main loop (%d/%d): %s", 
                consecutive_errors, max_consecutive_errors, 
                type(e).__name__, 
                exc_info=True
            )
            
            # Exponential backoff on consecutive errors
            if consecutive_errors >= max_consecutive_errors:
                backoff = min(300, 10 * (2 ** (consecutive_errors - max_consecutive_errors)))
                log.error(
                    "[FOLLOWUP WORKER] Too many consecutive errors, backing off for %ds", 
                    backoff
                )
                await asyncio.sleep(backoff)
            else:
                # Short delay before retry
                await asyncio.sleep(5)
                continue
        
        # Wait before next check
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    """
    Run worker as standalone process:
    python -m app.workers.followup_worker
    
    Environment variables required:
    - DATABASE_URL: PostgreSQL connection string (from Render)
    """
    import sys
    import os
    
    # Log startup info
    log.info("=" * 60)
    log.info("[FOLLOWUP_WORKER] Starting as standalone process")
    log.info("[FOLLOWUP_WORKER] Python: %s", sys.version)
    log.info("[FOLLOWUP_WORKER] DATABASE_URL: %s", 
             "SET" if os.getenv("DATABASE_URL") else "NOT SET")
    log.info("=" * 60)
    
    try:
        asyncio.run(run_followup_worker())
    except KeyboardInterrupt:
        log.info("[FOLLOWUP_WORKER] Stopped by user (Ctrl+C)")
    except Exception as e:
        log.error("[FOLLOWUP_WORKER] Fatal error: %s", type(e).__name__, exc_info=True)
        sys.exit(1)
