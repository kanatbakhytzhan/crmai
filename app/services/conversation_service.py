"""
Unified conversation history engine for WhatsApp webhook and /api/chat.
DB-backed conversations/messages per (channel, external_id [, phone_number_id]).
Prevents cross-user context mixing.
"""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import crud
from app.database.models import Conversation


async def get_or_create_conversation(
    db: AsyncSession,
    tenant_id: Optional[int],
    channel: str,
    external_id: str,
    phone_number_id: Optional[str] = None,
) -> Conversation:
    """
    Get or create a conversation by (channel, phone_number_id, external_id).
    For web chat: phone_number_id=None -> stored as "".
    """
    pid = (phone_number_id or "").strip()
    external_id = str(external_id).strip()
    return await crud.get_or_create_conversation(
        db,
        tenant_id=tenant_id,
        phone_number_id=pid,
        wa_from=external_id,
        channel=channel,
    )


async def append_user_message(
    db: AsyncSession,
    conversation_id: int,
    text: str,
    raw_json: Optional[dict] = None,
):
    """Append a user message to the conversation."""
    await crud.add_conversation_message(db, conversation_id, "user", text or "", raw_json=raw_json)


async def append_assistant_message(
    db: AsyncSession,
    conversation_id: int,
    text: str,
    raw_json: Optional[dict] = None,
):
    """Append an assistant message to the conversation."""
    await crud.add_conversation_message(db, conversation_id, "assistant", text or "", raw_json=raw_json)


async def build_context_messages(
    db: AsyncSession,
    conversation_id: int,
    limit: int = 20,
) -> List[dict]:
    """Load last N messages and return list of {role, content} for OpenAI (chronological order)."""
    messages = await crud.get_last_messages(db, conversation_id, limit=limit)
    return [{"role": m.role, "content": m.text} for m in messages]


async def trim_if_needed(
    db: AsyncSession,
    conversation_id: int,
    keep_last: int = 50,
) -> int:
    """Delete older messages, keep last keep_last. Returns number deleted."""
    return await crud.trim_conversation_messages(db, conversation_id, keep_last=keep_last)
