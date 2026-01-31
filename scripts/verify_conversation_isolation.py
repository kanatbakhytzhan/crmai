"""
Verification: unified conversation engine — no cross-user context mixing.
- Two different external_id -> 2 separate conversations, messages not mixed.
- Same external_id twice -> reuse same conversation, message count grows.
Run: python scripts/verify_conversation_isolation.py (from repo root; DB initialized).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.session import AsyncSessionLocal, init_db
from app.services import conversation_service


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        # 1. Two different external_ids (web channel) -> 2 conversations
        conv_a = await conversation_service.get_or_create_conversation(
            db, tenant_id=None, channel="web", external_id="user_a@test.com", phone_number_id=None
        )
        conv_b = await conversation_service.get_or_create_conversation(
            db, tenant_id=None, channel="web", external_id="guest:127.0.0.1", phone_number_id=None
        )
        assert conv_a.id != conv_b.id, "Different external_id must yield different conversations"
        print(f"[OK] Two external_ids -> 2 conversations: conv_id={conv_a.id}, conv_id={conv_b.id}")

        await conversation_service.append_user_message(db, conv_a.id, "Message from A")
        await conversation_service.append_user_message(db, conv_b.id, "Message from B")
        ctx_a = await conversation_service.build_context_messages(db, conv_a.id, limit=20)
        ctx_b = await conversation_service.build_context_messages(db, conv_b.id, limit=20)
        assert len(ctx_a) == 1 and ctx_a[0]["content"] == "Message from A"
        assert len(ctx_b) == 1 and ctx_b[0]["content"] == "Message from B"
        print("[OK] Messages not mixed: A has only A text, B has only B text")

        # 2. Same external_id twice -> same conversation
        conv_a2 = await conversation_service.get_or_create_conversation(
            db, tenant_id=None, channel="web", external_id="user_a@test.com", phone_number_id=None
        )
        assert conv_a.id == conv_a2.id, "Same external_id must reuse same conversation"
        await conversation_service.append_user_message(db, conv_a2.id, "Second message from A")
        ctx_a_after = await conversation_service.build_context_messages(db, conv_a.id, limit=20)
        assert len(ctx_a_after) == 2
        assert ctx_a_after[0]["content"] == "Message from A" and ctx_a_after[1]["content"] == "Second message from A"
        print(f"[OK] Same external_id reused conv_id={conv_a.id}, message count=2")


if __name__ == "__main__":
    asyncio.run(main())
