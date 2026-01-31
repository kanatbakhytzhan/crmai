# WhatsApp Chat History Persistence — Report

## Schema

### `conversations`
- **id** (PK)
- **tenant_id** (FK tenants.id, nullable)
- **channel** (string, default `"whatsapp"`)
- **external_id** (string) — WhatsApp "from" number
- **phone_number_id** (string) — metadata.phone_number_id (business number)
- **is_active** (bool, default true)
- **created_at**, **updated_at**
- **Unique:** `(channel, phone_number_id, external_id)` — one conversation per (tenant + from).

### `conversation_messages`
- **id** (PK)
- **conversation_id** (FK conversations.id)
- **role** (string): `"user"` | `"assistant"` | `"system"`
- **text** (text)
- **raw_json** (JSON, nullable)
- **created_at**

Tables are created by `Base.metadata.create_all` in `init_db()` (models imported in `main.py`). No separate ALTER migration for new tables.

## How context is built

1. On each incoming WhatsApp message (POST webhook): resolve tenant via `whatsapp_accounts.phone_number_id`.
2. **get_or_create_conversation**(tenant_id, phone_number_id, wa_from) — one row per (channel, phone_number_id, external_id); retry on IntegrityError for race safety.
3. **add_conversation_message**(conv.id, "user", text) — store user message.
4. **get_last_messages**(conv.id, limit=20) — ordered by `created_at` asc (oldest → newest).
5. Build list for GPT: `[{"role": m.role, "content": m.text} for m in last_messages]`.
6. Call **openai_service.chat_with_gpt**(messages_for_gpt) — system prompt is added inside the service.
7. **add_conversation_message**(conv.id, "assistant", reply) — store assistant reply.
8. Webhook always returns `{"ok": true}`; lead creation is unchanged; on AI error only a warning is logged.

## How to test

1. **Verification script (CRUD + conversation reuse):**
   ```bash
   cd /path/to/repo
   python scripts/verify_wa_chat_history.py
   ```
   - Ensures tenant + whatsapp_account exist (creates if missing).
   - Calls get_or_create_conversation twice with same (tenant_id, phone_number_id, wa_from).
   - Asserts same conversation id, message count 1 → 2, and get_last_messages returns messages in correct order (first message first, second second).

2. **Full webhook (manual):**
   - Set `WHATSAPP_ENABLED=true`, run app, create tenant + whatsapp_account (e.g. via admin API).
   - POST twice to `/api/whatsapp/webhook` with same `metadata.phone_number_id` and same `messages[].from`:
     ```bash
     curl -X POST "http://localhost:8000/api/whatsapp/webhook" \
       -H "Content-Type: application/json" \
       -d '{"object":"whatsapp_business_account","entry":[{"id":"1","changes":[{"value":{"metadata":{"phone_number_id":"YOUR_PHONE_NUMBER_ID"},"messages":[{"from":"79001234567","type":"text","text":{"body":"Hello"}}]}}]}]}'
     ```
   - Check logs for `[WA][CHAT] conv_id=... stored user msg` and `loaded N context messages`; in DB, same conversation_id and growing message count.

## Safety

- No in-memory global history; all state in DB.
- Existing endpoints and MULTITENANT_ENABLED / WHATSAPP_ENABLED unchanged.
- Lead creation and webhook response `{"ok": true}` preserved; AI failure does not break webhook.
