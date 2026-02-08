"""
Welcome Sequence Service - Send 3-message introduction (voice + photos + link)

Triggered on first message from new lead if tenant.welcome_sequence_enabled = True
"""
import logging
import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Lead, Tenant, WhatsAppAccount
from app.services import chatflow_client

log = logging.getLogger(__name__)


async def send_welcome_sequence(
    db: AsyncSession,
    lead: Lead,
    tenant: Tenant,
    language: str,  # "ru" or "kz"
    chatflow_account: WhatsAppAccount
):
    """
    Send 3-message welcome sequence:
    1. Voice note (RU or KZ based on language)
    2. Photos album (from tenant.welcome_photo_urls)
    3. Website link message
    
    All via ChatFlow API with delays (2s between messages)
    
    Args:
        db: Database session
        lead: Lead receiving the welcome
        tenant: Tenant configuration
        language: "ru" or "kz" for voice selection
        chatflow_account: WhatsApp account credentials
    """
    if not tenant.welcome_sequence_enabled:
        log.debug(f"[WELCOME] Skipped for lead {lead.id}: sequence disabled")
        return
    
    remote_jid = lead.bot_user.user_id
    token = chatflow_account.chatflow_token
    instance_id = chatflow_account.chatflow_instance_id
    
    if not token or not instance_id:
        log.error(f"[WELCOME] Missing ChatFlow credentials for lead {lead.id}")
        return
    
    log.info(f"[WELCOME] Starting sequence for lead {lead.id}, language={language}")
    
    try:
        # 1. Send voice message
        voice_url = tenant.welcome_voice_ru_url if language == "ru" else tenant.welcome_voice_kz_url
        
        if voice_url:
            try:
                await chatflow_client.send_audio(remote_jid, voice_url, token, instance_id)
                log.info(f"[WELCOME] Sent voice to lead {lead.id}")
                await asyncio.sleep(2)  # Delay before next message
            except Exception as e:
                log.error(f"[WELCOME] Failed to send voice: {e}", exc_info=True)
        else:
            log.warning(f"[WELCOME] No voice URL configured for language={language}")
        
        # 2. Send photos
        photo_urls = tenant.welcome_photo_urls or []
        
        if isinstance(photo_urls, list) and photo_urls:
            for idx, photo_url in enumerate(photo_urls[:5]):  # Max 5 photos to avoid spam
                try:
                    await chatflow_client.send_image(remote_jid, photo_url, token, instance_id)
                    log.info(f"[WELCOME] Sent photo {idx+1}/{min(len(photo_urls), 5)} to lead {lead.id}")
                    await asyncio.sleep(1)  # Short delay between photos
                except Exception as e:
                    log.error(f"[WELCOME] Failed to send photo #{idx+1}: {e}", exc_info=True)
        else:
            log.debug(f"[WELCOME] No photos configured for tenant {tenant.id}")
        
        # 3. Send website link
        if tenant.website_url:
            try:
                if language == "ru":
                    message = f"Сайт компании: {tenant.website_url}"
                else:  # kz
                    message = f"Kompaniyanyn sayty: {tenant.website_url}"
                
                await chatflow_client.send_text(remote_jid, message, token, instance_id)
                log.info(f"[WELCOME] Sent website link to lead {lead.id}")
            except Exception as e:
                log.error(f"[WELCOME] Failed to send website link: {e}", exc_info=True)
        else:
            log.debug(f"[WELCOME] No website URL configured for tenant {tenant.id}")
        
        log.info(f"[WELCOME] Sequence completed for lead {lead.id}")
    
    except Exception as e:
        log.error(f"[WELCOME] Unexpected error for lead {lead.id}: {e}", exc_info=True)


async def is_first_message_from_user(db: AsyncSession, lead: Lead) -> bool:
    """
    Check if this is the first inbound message from the user.
    
    Returns True if:
    - lead.last_inbound_at is None (never received inbound)
    - OR this is within first minute of lead creation
    """
    if not lead.last_inbound_at:
        return True
    
    # Check if within first minute of creation
    creation_delta = (lead.last_inbound_at - lead.created_at).total_seconds()
    return creation_delta < 60  # First message within 1 minute of lead creation
