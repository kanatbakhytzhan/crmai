# Сохранение привязки WhatsApp в админке

## Проблема
Привязка WhatsApp/ChatFlow (token, instance_id, phone_number, active) хранится в таблице **whatsapp_accounts**, а не в tenants. PATCH `/api/admin/tenants/{id}` эти поля не принимает — они игнорируются. Поэтому «Сохранить» в форме tenant не сохранял привязку.

## Решение

### Эндпоинт для сохранения привязки (фронт)

**PUT** `/api/admin/tenants/{tenant_id}/whatsapp`

**Headers:** `Authorization: Bearer <admin_jwt>`

**Body (JSON):**
```json
{
  "chatflow_token": "your_chatflow_token",
  "chatflow_instance_id": "instance_abc",
  "phone_number": "+77001234567",
  "is_active": true
}
```

- **is_active = true** → обязательны `chatflow_token` и `chatflow_instance_id` (иначе 400).
- **is_active = false** → token/instance_id могут быть пустыми (бот не отвечает).

**Ответ 200:** объект привязки (id, tenant_id, phone_number, chatflow_token, chatflow_instance_id, is_active, created_at).

**Поведение:** если у tenant уже есть запись в whatsapp_accounts — она обновляется; если нет — создаётся (upsert, одна запись на tenant).

### Как получить текущие значения

1. **GET** `/api/admin/tenants/{tenant_id}` — tenant + `whatsapp_connection` (первая привязка или null).
2. **GET** `/api/admin/tenants/{tenant_id}/whatsapp` — `{ "accounts": [...], "total": N }` (для формы можно взять `accounts[0]`).

### Проверка в /docs

1. **Сохранить:** PUT `/api/admin/tenants/{tenant_id}/whatsapp`, body как выше → 200, в ответе те же поля.
2. **Получить:** GET `/api/admin/tenants/{tenant_id}/whatsapp` или GET `/api/admin/tenants/{tenant_id}` → в ответе те же token, instance_id, phone_number, is_active.
3. Обновить страницу/повторно открыть форму — значения должны совпадать с сохранёнными.

### Лог на сервере
При сохранении: `[ADMIN] whatsapp upsert <tenant_id> <instance_id> <phone_number> <active>`.

## Изменённые файлы

- **app/database/crud.py** — `update_whatsapp_account`, `upsert_whatsapp_for_tenant`; `create_whatsapp_account(is_active=...)`
- **app/schemas/tenant.py** — `WhatsAppAccountUpsert`, `WhatsAppAccountResponse.phone_number_id` → Optional
- **app/api/endpoints/admin_tenants.py** — PUT `/tenants/{id}/whatsapp`, GET `/tenants/{id}` с whatsapp_connection

Старые контракты сохранены: POST attach и GET list работают как раньше.
