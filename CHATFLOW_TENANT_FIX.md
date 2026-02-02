# ChatFlow/WhatsApp tenant — исправления

## Список изменённых/новых файлов

- **app/database/models.py** — модель `ChatAIState`, поле `Lead.phone_from_message`
- **app/database/crud.py** — `get_chat_ai_state`, `set_chat_ai_state`, `get_active_chatflow_account_for_tenant`, `update_lead_phone(..., phone_from_message=...)`
- **app/database/session.py** — миграции: таблица `chat_ai_states`, колонка `leads.phone_from_message` (Postgres + SQLite)
- **app/api/endpoints/chatflow_webhook.py** — жёсткая привязка tenant, проверка WhatsApp, chat_ai_states для /stop /start, обработка «только номер», tenant.ai_prompt из БД
- **app/api/endpoints/whatsapp_webhook.py** — tenant.ai_prompt из БД перед GPT + лог
- **main.py** — импорт `ChatAIState` для create_all

## Добавленные SQL таблицы/поля

| Где | Что |
|-----|-----|
| **chat_ai_states** (новая таблица) | `id`, `tenant_id` (FK tenants), `remote_jid` (VARCHAR 255), `is_enabled` (BOOLEAN DEFAULT TRUE), `updated_at`, UNIQUE(tenant_id, remote_jid) |
| **leads** | `phone_from_message` VARCHAR(32) NULL — номер, присланный текстом в чате |

## Команды для быстрого теста

```bash
# 1. Запуск приложения (миграции выполнятся при старте)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 2. Проверка ChatFlow webhook без привязки (должен вернуть {"ok": true}, без ответа бота)
curl -X POST http://localhost:8000/api/chatflow/webhook \
  -H "Content-Type: application/json" \
  -d '{"metadata":{"remoteJid":"79001234567@s.whatsapp.net","messageId":"test1"},"messageType":"text","message":"Привет"}'
# В логах: [AI] SKIP tenant not found for chatflow instance

# 3. Проверка с instance_id, но без активного whatsapp (должен {"ok": true}, без ответа)
# Сначала в админке: tenant + whatsapp_account с chatflow_instance_id, но без chatflow_token и без instance_id — или is_active=false
# В логах: [AI] SKIP whatsapp not attached/inactive

# 4. После привязки WhatsApp к tenant (chatflow_token или chatflow_instance_id) — бот должен отвечать
# В логах перед GPT: [GPT] tenant_id=... use_tenant_prompt=... prompt_len=...

# 5. /stop и /start — по remoteJid (кто бы ни писал)
# POST webhook с message "/stop" → ответ "Ок ✅ AI в этом чате выключен..."
# Следующее сообщение → бот не отвечает (chat_ai_state=false)
# POST webhook с message "/start" → ответ "Ок ✅ AI снова включён..."
```

## Поведение (кратко)

- **A)** Tenant только по привязке (instance_id в payload или webhook_key в URL). Нет fallback на «первый tenant». Если нет tenant или нет активного WhatsApp с token/instance_id → `{"ok": true}`, без ответа.
- **B)** /stop и /start меняют только `chat_ai_states` по (tenant_id, remote_jid). Критерий один: входящий remoteJid.
- **C)** Сообщение «только номер» (10–15 цифр/пробелы/+-) → сохраняем в lead.phone и lead.phone_from_message, ответ «Спасибо! Номер записал ✅», контекст не сбрасывается.
- **D)** Перед вызовом GPT tenant загружается из БД; system_override = tenant.ai_prompt (если не пусто). В логах: `[GPT] tenant_id=... use_tenant_prompt=... prompt_len=...`.
