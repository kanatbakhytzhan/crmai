"""
Verify chat mute functionality for Universal Admin Console.
Creates lead+conversation with tenant_id, sets mute, verifies AI check.

Usage: python scripts/verify_chat_mute.py
"""
import asyncio
import sys
sys.path.insert(0, ".")

from sqlalchemy import select
from app.database.session import AsyncSessionLocal, init_db
from app.database.models import Lead, Conversation, Tenant, BotUser, ChatAIState
from app.database import crud


async def main():
    print("=== Verify Chat Mute ===\n")
    
    async with AsyncSessionLocal() as db:
        # 1. Get or create test tenant
        tenants = await crud.list_tenants(db, active_only=True)
        if not tenants:
            print("[ERROR] No active tenants found. Create a tenant first.")
            return
        
        tenant = tenants[0]
        print(f"[OK] Using tenant: id={tenant.id} name={tenant.name}")
        
        # 2. Check if tenant has owner
        owner_id = tenant.default_owner_user_id
        if not owner_id:
            first_user = await crud.get_first_user(db)
            if not first_user:
                print("[ERROR] No users found.")
                return
            owner_id = first_user.id
            print(f"[WARN] Tenant has no default_owner_user_id, using first user: {owner_id}")
        
        # 3. Create test bot_user
        test_jid = "test_verify_mute_77001234567@s.whatsapp.net"
        bot_user = await crud.get_or_create_bot_user(db, user_id=test_jid, owner_id=owner_id, language="ru")
        print(f"[OK] BotUser: id={bot_user.id} user_id={bot_user.user_id}")
        
        # 4. Create test conversation
        from app.services import conversation_service
        conv = await conversation_service.get_or_create_conversation(
            db, tenant_id=tenant.id, channel="chatflow", external_id=test_jid, phone_number_id=""
        )
        print(f"[OK] Conversation: id={conv.id} tenant_id={conv.tenant_id} external_id={conv.external_id}")
        
        # 5. Create test lead WITH tenant_id
        lead = await crud.create_lead(
            db,
            owner_id=owner_id,
            bot_user_id=bot_user.id,
            name="Test Mute Lead",
            phone="+77001234567",
            summary="Test lead for mute verification",
            language="ru",
            tenant_id=tenant.id,
            source="manual",
        )
        print(f"[OK] Lead created: id={lead.id} tenant_id={lead.tenant_id}")
        
        # 6. Verify lead has tenant_id
        if not lead.tenant_id:
            print("[FAIL] Lead does not have tenant_id!")
            return
        print(f"[OK] Lead has tenant_id={lead.tenant_id}")
        
        # 7. Mute chat via lead
        result = await crud.mute_chat_for_lead(db, lead.id, muted=True, muted_by_user_id=owner_id)
        print(f"[OK] Mute result: {result}")
        
        if not result.get("ok"):
            print(f"[FAIL] Mute failed: {result.get('error')}")
            return
        
        # 8. Verify chat_ai_state is False
        state = await crud.get_chat_ai_state(db, tenant.id, test_jid)
        if state:
            print(f"[OK] Chat AI is enabled={state} (should be False for muted)")
            if state:
                print("[WARN] Chat is not muted! get_chat_ai_state returned True")
        else:
            print(f"[OK] Chat is muted (get_chat_ai_state returned False)")
        
        # 9. Unmute
        result2 = await crud.mute_chat_for_lead(db, lead.id, muted=False, muted_by_user_id=owner_id)
        print(f"[OK] Unmute result: {result2}")
        
        # 10. Verify chat_ai_state is True
        state2 = await crud.get_chat_ai_state(db, tenant.id, test_jid)
        print(f"[OK] Chat AI after unmute: enabled={state2}")
        
        # Cleanup
        await db.delete(lead)
        result_state = await db.execute(
            select(ChatAIState).where(ChatAIState.tenant_id == tenant.id).where(ChatAIState.remote_jid == test_jid)
        )
        state_row = result_state.scalar_one_or_none()
        if state_row:
            await db.delete(state_row)
        await db.commit()
        print("\n[OK] Cleanup done. Test passed!")


if __name__ == "__main__":
    asyncio.run(main())
