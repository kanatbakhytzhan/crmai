# WhatsApp Webhook Setup (Multi-tenant)

## Переменные окружения

- `MULTITENANT_ENABLED` — `false` (по умолчанию). При `false` лиды по `/api/leads` работают как раньше (без фильтра по tenant).
- `WHATSAPP_ENABLED` — `false` (по умолчанию). При `true` включаются эндпоинты `/api/whatsapp/webhook`.
- `WHATSAPP_VERIFY_TOKEN` — (опционально) токен для верификации Meta. Если не задан, проверяется `verify_token` в таблице `whatsapp_accounts`.

## Таблицы

- `tenants` — клиенты (id, name, slug, is_active, created_at).
- `whatsapp_accounts` — привязка номера к tenant (tenant_id, phone_number, phone_number_id, verify_token, waba_id, …).
- `leads` — добавлено поле `tenant_id` (nullable).

## Админ-эндпоинты (JWT + admin)

- `POST /api/admin/tenants` — создать tenant: `{"name": "...", "slug": "..."}`.
- `GET /api/admin/tenants` — список tenants.
- `POST /api/admin/tenants/{tenant_id}/whatsapp` — привязать номер: `{"phone_number": "...", "phone_number_id": "...", "verify_token": "..."}`.
- `GET /api/admin/tenants/{tenant_id}/whatsapp` — список номеров tenant.

## Webhook Meta

- `GET /api/whatsapp/webhook` — верификация: `hub.mode`, `hub.verify_token`, `hub.challenge`. Токен сверяется с `WHATSAPP_VERIFY_TOKEN` или с `whatsapp_accounts.verify_token`.
- `POST /api/whatsapp/webhook` — приём сообщений. По `phone_number_id` из payload находится tenant, создаётся lead с `tenant_id` и текстом сообщения.

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
