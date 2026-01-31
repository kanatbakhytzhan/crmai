"""
Verification: per-user WhatsApp chat history (conversations + conversation_messages).
- Inserts tenant + whatsapp_account, then simulates two messages from same "from".
- Asserts: same conversation reused, message count grows, get_last_messages returns correct order.
Run: python scripts/verify_wa_chat_history.py (from repo root; DB must be initialized).
"""
import asyncio
import os
import sys

# Ensure app is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.session import AsyncSessionLocal, init_db
from app.database import crud
from app.database.models import Tenant, WhatsAppAccount


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        tenant = await crud.get_tenant_by_slug(db, "verify-chat-tenant")
        if not tenant:
            tenant = await crud.create_tenant(db, name="Verify Chat Tenant", slug="verify-chat-tenant")
        tenant_id = tenant.id

        phone_number_id = "999888777666"
        acc = await crud.get_whatsapp_account_by_phone_number_id(db, phone_number_id)
        if not acc:
            acc = await crud.create_whatsapp_account(
                db, tenant_id=tenant_id, phone_number="+79998887776",
                phone_number_id=phone_number_id,
            )

        wa_from = "79001234567"
        conv1 = await crud.get_or_create_conversation(
            db, tenant_id=tenant_id, phone_number_id=phone_number_id, wa_from=wa_from
        )
        await crud.add_conversation_message(db, conv1.id, "user", "First message")
        msgs_after_first = await crud.get_last_messages(db, conv1.id, limit=20)

        conv2 = await crud.get_or_create_conversation(
            db, tenant_id=tenant_id, phone_number_id=phone_number_id, wa_from=wa_from
        )
        await crud.add_conversation_message(db, conv2.id, "user", "Second message")
        msgs_after_second = await crud.get_last_messages(db, conv2.id, limit=20)

        assert conv1.id == conv2.id, "Same conversation must be reused"
        assert len(msgs_after_first) == 1, "After first message: 1 message"
        assert len(msgs_after_second) == 2, "After second message: 2 messages"
        assert msgs_after_second[0].text == "First message", "Order: first message first"
        assert msgs_after_second[1].text == "Second message", "Order: second message second"

        print(f"[OK] Same conversation reused (conv_id={conv1.id})")
        print("[OK] Message count grew: 1 -> 2")
        print("[OK] get_last_messages order correct: First message, Second message")


if __name__ == "__main__":
    asyncio.run(main())
