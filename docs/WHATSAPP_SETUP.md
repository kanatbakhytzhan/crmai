# WhatsApp Webhook Setup (Multi-tenant)

## Переменные окружения

- `MULTITENANT_ENABLED` — `false` (по умолчанию). При `false` лиды по `/api/leads` работают как раньше (без фильтра по tenant).
- `WHATSAPP_ENABLED` — `false` (по умолчанию). При `true` включаются эндпоинты `/api/whatsapp/webhook`.
- `WHATSAPP_VERIFY_TOKEN` — (опционально) токен для верификации Meta. Если не задан, проверяется `verify_token` в таблице `whatsapp_accounts`.
- `WHATSAPP_SEND_ENABLED` — `false` (по умолчанию). При `true` ответы ассистента отправляются в WhatsApp через Cloud API (нужен `WHATSAPP_ACCESS_TOKEN`).
- `WHATSAPP_ACCESS_TOKEN` — (опционально) токен доступа Meta для отправки сообщений. Используется только при `WHATSAPP_SEND_ENABLED=true`.
- `WHATSAPP_API_VERSION` — версия API (по умолчанию `v20.0`).
- `WHATSAPP_GRAPH_BASE` — базовый URL (по умолчанию `https://graph.facebook.com`).

## Таблицы

- `tenants` — клиенты (id, name, slug, is_active, default_owner_user_id, ai_enabled, ai_prompt, created_at). **Установите `default_owner_user_id`** (ID пользователя из `users`), чтобы лиды из WhatsApp попадали в CRM этому пользователю. **ai_enabled** (по умолчанию true) — вкл/выкл автоответ AI для этого tenant.
- `whatsapp_accounts` — привязка номера к tenant (tenant_id, phone_number, phone_number_id, verify_token, waba_id, …).
- `leads` — добавлено поле `tenant_id` (nullable). При создании из webhook `owner_id` берётся из `tenant.default_owner_user_id`; если NULL — fallback на первого пользователя (в лог пишется предупреждение).

## Админ-эндпоинты (JWT + admin)

- `POST /api/admin/tenants` — создать tenant: `{"name": "...", "slug": "...", "default_owner_user_id": 1}` (опционально).
- `GET /api/admin/tenants` — список tenants (включая `default_owner_user_id`).
- `PATCH /api/admin/tenants/{tenant_id}` — обновить tenant: `{"name": "...", "slug": "...", "is_active": true, "default_owner_user_id": 1}`.
- `POST /api/admin/tenants/{tenant_id}/whatsapp` — привязать номер: `{"phone_number": "...", "phone_number_id": "...", "verify_token": "..."}`.
- `GET /api/admin/tenants/{tenant_id}/whatsapp` — список номеров tenant.

**Пример: установить владельца tenant (чтобы лиды показывались в CRM)**

```bash
curl -i -X PATCH "http://localhost:8000/api/admin/tenants/1" \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"default_owner_user_id": 1}'
```

## Webhook Meta

- `GET /api/whatsapp/webhook` — верификация: `hub.mode`, `hub.verify_token`, `hub.challenge`. Токен сверяется с `WHATSAPP_VERIFY_TOKEN` или с `whatsapp_accounts.verify_token`.
- `POST /api/whatsapp/webhook` — приём сообщений. По `phone_number_id` из payload находится tenant, создаётся lead с `owner_id = tenant.default_owner_user_id` (или первый пользователь с предупреждением в лог) и текстом сообщения. Если у tenant **ai_enabled=false**, входящие сохраняются, автоответ не отправляется. В чате: текст **/stop** или **stop** — выключить AI для этого tenant; **/start** или **start** — включить AI (ответ «AI-менеджер выключен/включен ✅»).

## Проверка локально (curl)

Установите `WHATSAPP_ENABLED=true` и `WHATSAPP_VERIFY_TOKEN=my_secret_token`.

**1) Верификация (GET)**

```bash
curl -i "http://localhost:8000/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=my_secret_token&hub.challenge=CHALLENGE_STRING"
```

Ожидание: ответ `200 OK`, тело `CHALLENGE_STRING`.

**2) POST webhook (имитация payload)**

```bash
curl -i -X POST "http://localhost:8000/api/whatsapp/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "123",
      "changes": [{
        "value": {
          "metadata": { "phone_number_id": "106540352242922" },
          "messages": [{ "from": "79001234567", "type": "text", "text": { "body": "Hello" } }]
        }
      }]
    }]
  }'
```

Ожидание: `200 OK`, тело `{"ok": true}`. В логах: `[WA] webhook received phone_number_id=... tenant=... created lead id=...` (если для этого `phone_number_id` есть запись в `whatsapp_accounts` и tenant найден).

## Pytest (опционально)

Минимальная проверка верификации:

```python
def test_webhook_verify_disabled(client):
    r = client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=x&hub.challenge=ok")
    assert r.status_code == 404  # WHATSAPP_ENABLED=false
```

При `WHATSAPP_ENABLED=true` и правильном `hub.verify_token` ожидается 200 и тело challenge.

## Chat history storage (unified engine)

История чатов WhatsApp и веб-чата хранится в БД через **unified conversation engine** (`app/services/conversation_service.py`). Ключ: **tenant_id + channel + external_id** (+ phone_number_id для WhatsApp). Подробнее: [CONVERSATIONS.md](CONVERSATIONS.md).

- **WhatsApp:** channel=`whatsapp`, external_id=номер отправителя (wa_from), phone_number_id=бизнес-номер. Один conversation на (tenant + номер отправителя).
- **Таблицы:** `conversations`, `conversation_messages`. Контекст для AI — последние 20 сообщений (build_context_messages).
- **Порядок:** append_user_message → build_context_messages → OpenAI → append_assistant_message.
- **Логи:** `[WA][CHAT] conv_id=... tenant_id=... from=... stored user msg`, `[WA][CHAT] loaded N context messages`, `[WA][CHAT] stored assistant msg`.
- Отправка ответа в WhatsApp опциональна (см. раздел «Optional sending replies» ниже). По умолчанию ответ только сохраняется в БД и лог. Webhook всегда возвращает `{"ok": true}`; при ошибке AI или отправки лид создаётся, в лог пишется предупреждение.

## Optional sending replies

По умолчанию **отправка ответов в WhatsApp выключена**: ответ ассистента сохраняется в БД и в логах, но не отправляется в чат. Так прод остаётся стабильным без настройки Cloud API.

**Как включить позже (например на Render):**

1. В Environment добавьте:
   - `WHATSAPP_SEND_ENABLED` = `true`
   - `WHATSAPP_ACCESS_TOKEN` = ваш токен доступа приложения Meta (с правами на отправку сообщений WhatsApp)

2. Сохраните и перезапустите сервис.

3. **Проверка:** отправьте сообщение в WhatsApp на привязанный номер; в логах должно появиться `[WA][SEND] ok message_id=...`. Если токен не задан или отправка выключена — будет `[WA][SEND] skipped disabled` или `[WA][SEND] skipped missing_token`. При ошибке API — `[WA][SEND] failed error=...`. Webhook в любом случае возвращает `{"ok": true}`.
