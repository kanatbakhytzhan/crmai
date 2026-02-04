"""
Universal Message Router: handles incoming messages for both ChatFlow and AmoCRM modes.
Normalizes messages into a common structure and routes to appropriate handlers.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import crud
from app.services import amocrm_service

log = logging.getLogger(__name__)


@dataclass
class NormalizedMessage:
    """Common message structure for all sources."""
    tenant_id: int
    channel: str  # "chatflow" | "amomarket"
    sender_phone: str  # normalized phone number
    sender_name: str
    message_type: str  # "text" | "voice" | "image" | "other"
    text: str  # message text or transcript
    timestamp: datetime
    conversation_id: Optional[str] = None  # external conversation id
    external_message_id: Optional[str] = None  # for deduplication
    raw: Optional[dict] = None  # original payload


def normalize_phone(raw: str) -> str:
    """Normalize phone to format 7xxxxxxxxxx."""
    import re
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10:
        return digits
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    elif digits.startswith("+7"):
        digits = digits[1:]
    elif not digits.startswith("7") and len(digits) == 10:
        digits = "7" + digits
    return digits[:11] if len(digits) >= 11 else digits


async def handle_inbound_message(
    db: AsyncSession,
    msg: NormalizedMessage,
) -> dict:
    """
    Universal handler for inbound messages.
    Routes to ChatFlow mode or AmoCRM mode based on tenant settings.
    Returns: {"ok": bool, "mode": str, "details": ...}
    """
    tenant = await crud.get_tenant_by_id(db, msg.tenant_id)
    if not tenant:
        log.warning("[ROUTER] tenant not found: %s", msg.tenant_id)
        return {"ok": False, "error": "tenant_not_found"}
    
    whatsapp_source = getattr(tenant, "whatsapp_source", "chatflow") or "chatflow"
    log.info("[ROUTER] tenant_id=%s whatsapp_source=%s channel=%s phone=%s", 
             msg.tenant_id, whatsapp_source, msg.channel, msg.sender_phone[-4:] if msg.sender_phone else "?")
    
    if whatsapp_source == "amomarket":
        return await _handle_amomarket_mode(db, tenant, msg)
    else:
        # chatflow mode - return early, let existing webhook handle
        return {"ok": True, "mode": "chatflow", "details": "handled_by_webhook"}


async def _handle_amomarket_mode(
    db: AsyncSession,
    tenant: Any,
    msg: NormalizedMessage,
) -> dict:
    """
    AmoCRM mode: sync message to AmoCRM as note, manage leads in amoCRM.
    """
    tenant_id = tenant.id
    
    # 1) Get AmoCRM client
    amo_client = await amocrm_service.get_amocrm_client(db, tenant_id)
    if not amo_client:
        log.error("[ROUTER] amocrm client not available for tenant_id=%s", tenant_id)
        return {"ok": False, "error": "amocrm_not_connected", "mode": "amomarket"}
    
    # 2) Find or create contact by phone
    phone = msg.sender_phone
    contact = await amo_client.find_contact_by_phone(phone)
    contact_id = None
    if contact:
        contact_id = contact.get("id")
        log.info("[ROUTER] found contact_id=%s for phone=%s", contact_id, phone[-4:])
    else:
        # Create new contact
        contact_name = msg.sender_name or f"Клиент {phone[-4:]}"
        new_contact = await amo_client.create_contact(contact_name, phone)
        if new_contact:
            contact_id = new_contact.get("id")
            log.info("[ROUTER] created contact_id=%s for phone=%s", contact_id, phone[-4:])
    
    if not contact_id:
        log.error("[ROUTER] cannot find/create contact for phone=%s", phone[-4:])
        return {"ok": False, "error": "cannot_create_contact", "mode": "amomarket"}
    
    # 3) Find existing open lead for contact
    # Get pipeline_id from mappings
    mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
    pipeline_id = None
    unsorted_stage_id = None
    for m in mappings:
        if m.pipeline_id:
            pipeline_id = m.pipeline_id
        if m.stage_key == "unprocessed" and m.stage_id:
            unsorted_stage_id = int(m.stage_id)
    
    amo_lead = await amo_client.find_open_lead_for_contact(contact_id, pipeline_id)
    amo_lead_id = None
    
    if amo_lead:
        amo_lead_id = amo_lead.get("id")
        log.info("[ROUTER] found open lead_id=%s for contact_id=%s", amo_lead_id, contact_id)
    else:
        # Create new lead in UNSORTED stage
        if not unsorted_stage_id:
            log.warning("[ROUTER] no unsorted stage mapped, using default")
            # Fallback: try to get first stage from pipeline
            unsorted_stage_id = 0  # AmoCRM will use default
        
        new_lead = await amo_client.create_lead_in_stage(
            contact_id=contact_id,
            status_id=unsorted_stage_id or 0,
            name=f"Заявка от {msg.sender_name or phone[-4:]}",
            pipeline_id=int(pipeline_id) if pipeline_id else None,
        )
        if new_lead:
            amo_lead_id = new_lead.get("id")
            log.info("[ROUTER] created lead_id=%s in stage=%s", amo_lead_id, unsorted_stage_id)
    
    if not amo_lead_id:
        log.error("[ROUTER] cannot find/create lead in amoCRM")
        return {"ok": False, "error": "cannot_create_lead", "mode": "amomarket"}
    
    # 4) Add message as note to lead
    note_text = f"[{msg.message_type.upper()}] {msg.sender_name or 'Клиент'}: {msg.text}"
    note = await amo_client.add_note_to_lead(amo_lead_id, note_text)
    if note:
        log.info("[ROUTER] added note to lead_id=%s", amo_lead_id)
    
    # 5) Also save to our DB for history
    from app.services import conversation_service
    try:
        conv = await conversation_service.get_or_create_conversation(
            db, tenant_id=tenant_id, channel="amomarket", 
            external_id=msg.conversation_id or msg.sender_phone, 
            phone_number_id=""
        )
        await conversation_service.append_user_message(
            db, conv.id, msg.text, 
            raw_json=msg.raw, 
            external_message_id=msg.external_message_id
        )
    except Exception as e:
        log.warning("[ROUTER] save to local DB failed: %s", type(e).__name__)
    
    return {
        "ok": True, 
        "mode": "amomarket",
        "amo_contact_id": contact_id,
        "amo_lead_id": amo_lead_id,
        "note_added": bool(note),
    }


async def should_ai_reply(
    db: AsyncSession,
    tenant_id: int,
    remote_jid: str,
    tenant: Any = None,
) -> tuple[bool, str]:
    """
    Check if AI should reply to this chat.
    Returns: (should_reply: bool, reason: str)
    """
    if tenant is None:
        tenant = await crud.get_tenant_by_id(db, tenant_id)
    
    if not tenant:
        return False, "tenant_not_found"
    
    # Check global AI enabled
    ai_enabled_global = getattr(tenant, "ai_enabled_global", True)
    if not ai_enabled_global:
        return False, "ai_enabled_global=false"
    
    # Legacy ai_enabled field (backward compat)
    ai_enabled = getattr(tenant, "ai_enabled", True)
    if not ai_enabled:
        return False, "ai_enabled=false"
    
    # Check per-chat mute
    chat_enabled = await crud.get_chat_ai_state(db, tenant_id, remote_jid)
    if not chat_enabled:
        return False, "chat_muted"
    
    return True, "ok"


def get_system_prompt(tenant: Any, default_prompt: str = "") -> tuple[str, str]:
    """
    Get system prompt for AI.
    Returns: (prompt, source) where source is "tenant" or "default"
    """
    tenant_prompt = (getattr(tenant, "ai_prompt", None) or "").strip()
    if tenant_prompt:
        return tenant_prompt, "tenant"
    return default_prompt, "default"


async def process_mute_command(
    db: AsyncSession,
    tenant_id: int,
    remote_jid: str,
    command: str,  # "stop" | "start" | "stop_all" | "start_all"
) -> dict:
    """
    Process mute commands (/stop, /start, /stop all, /start all).
    Returns response dict with message.
    """
    if command == "stop":
        await crud.set_chat_ai_state(db, tenant_id, remote_jid, False)
        log.info("[MUTE] stop jid=...%s tenant_id=%s", remote_jid[-4:] if remote_jid else "?", tenant_id)
        return {"muted": True, "scope": "chat", "message": "Ок ✅ AI в этом чате выключен. Чтобы включить — /start"}
    
    elif command == "start":
        await crud.set_chat_ai_state(db, tenant_id, remote_jid, True)
        log.info("[MUTE] start jid=...%s tenant_id=%s", remote_jid[-4:] if remote_jid else "?", tenant_id)
        return {"muted": False, "scope": "chat", "message": "Ок ✅ AI снова включён в этом чате."}
    
    elif command == "stop_all":
        await crud.set_all_muted(db, "chatflow", "", True, tenant_id=tenant_id)
        log.info("[MUTE] stop_all tenant_id=%s", tenant_id)
        return {"muted": True, "scope": "all", "message": "Ок. AI отключен для всех чатов этого номера."}
    
    elif command == "start_all":
        await crud.set_all_muted(db, "chatflow", "", False, tenant_id=tenant_id)
        log.info("[MUTE] start_all tenant_id=%s", tenant_id)
        return {"muted": False, "scope": "all", "message": "Ок. AI для всех чатов снова включён."}
    
    return {"muted": None, "scope": None, "message": None}


async def ensure_lead_tenant_id(
    db: AsyncSession,
    lead: Any,
    fallback_tenant_id: Optional[int] = None,
) -> Optional[int]:
    """
    Ensure lead has tenant_id. Try to resolve if missing.
    Returns the tenant_id (or None if cannot resolve).
    """
    if getattr(lead, "tenant_id", None):
        return lead.tenant_id
    
    # Try to resolve
    resolved = await crud.resolve_lead_tenant_id(db, lead)
    if resolved:
        lead.tenant_id = resolved
        await db.commit()
        await db.refresh(lead)
        log.info("[LEAD] resolved tenant_id=%s for lead_id=%s", resolved, lead.id)
        return resolved
    
    # Use fallback
    if fallback_tenant_id:
        lead.tenant_id = fallback_tenant_id
        await db.commit()
        await db.refresh(lead)
        log.info("[LEAD] set fallback tenant_id=%s for lead_id=%s", fallback_tenant_id, lead.id)
        return fallback_tenant_id
    
    return None
