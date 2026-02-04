# Universal Admin Console

Универсальная админка для управления AI-агентом. Позволяет настраивать tenant без правки кода: выбрать источник WhatsApp, подключить amoCRM, настроить маппинг стадий и полей.

## Новые настройки tenant

### GET /api/admin/tenants/{id}/settings

Возвращает:

- `whatsapp_source`: `"chatflow"` | `"amomarket"` — источник WhatsApp сообщений
- `ai_enabled_global`: `true` | `false` — главный выключатель AI (если `false`, AI не отвечает вообще)
- `ai_prompt`: системный промпт для AI (если пусто — дефолтный)
- `ai_after_lead_submitted_behavior`: `"polite_close"` | `"continue"` | `"silent"` — поведение после отправки заявки

### PATCH /api/admin/tenants/{id}/settings

Обновить любое из вышеуказанных полей.

---

## Подключение ChatFlow

1. Создать tenant: POST `/api/admin/tenants`
2. Привязать WhatsApp: POST `/api/admin/tenants/{id}/whatsapp`
   - `chatflow_token`: токен из ChatFlow
   - `chatflow_instance_id`: instance_id из ChatFlow
   - `phone_number`: номер телефона
   - `is_active`: true

После привязки ChatFlow начнёт отправлять webhook на `/api/chatflow/webhook?key={webhook_key}`.

---

## Подключение amoCRM

### Шаг 1: Получить URL авторизации

```
GET /api/admin/tenants/{id}/amocrm/auth-url?base_domain=example.amocrm.ru
```

Возвращает:
```json
{"url": "https://example.amocrm.ru/oauth?client_id=...&redirect_uri=...&state=tenant_123"}
```

### Шаг 2: Перейти по URL

Пользователь переходит по URL, авторизуется в amoCRM. amoCRM редиректит на:
```
/api/integrations/amocrm/callback?code=...&state=tenant_123
```

Токены автоматически сохраняются.

### Шаг 3: Проверить статус

```
GET /api/admin/tenants/{id}/amocrm/status
```

Возвращает:
```json
{
  "is_active": true,
  "base_domain": "example.amocrm.ru",
  "token_expires_at": "2025-02-10T12:00:00",
  "connected": true
}
```

### Отключение

```
POST /api/admin/tenants/{id}/amocrm/disconnect
```

---

## Маппинг стадий (Pipeline Mappings)

Связывает наши `stage_key` со стадиями воронки в amoCRM.

### Доступные stage_key:

- `unprocessed` — необработанная заявка
- `in_work` — в работе
- `ready_call_1`, `ready_call_2`, `ready_call_3` — готов к звонку (уровни)
- `not_ready_repair` — не готов к ремонту
- `other_city` — другой город
- `ignore` — игнорировать
- `measurement_scheduled` — замер назначен
- `measurement_done` — замер проведён
- `success` — успешно закрыто
- `fail_after_measurement` — отказ после замера

### GET /api/admin/tenants/{id}/amocrm/pipeline-mapping

Список текущих маппингов.

### PUT /api/admin/tenants/{id}/amocrm/pipeline-mapping

Bulk upsert:

```json
{
  "mappings": [
    {"stage_key": "unprocessed", "stage_id": "12345678", "pipeline_id": "1234"},
    {"stage_key": "in_work", "stage_id": "12345679"},
    {"stage_key": "success", "stage_id": "12345680"}
  ]
}
```

---

## Маппинг полей (Field Mappings)

Связывает наши `field_key` с кастомными полями в amoCRM.

### Доступные field_key:

- `city` — город
- `district` — район
- `object_type` — тип объекта (дом/квартира)
- `area` — площадь
- `repair_stage` — стадия ремонта
- `preferred_call_time` — удобное время звонка
- `address` — адрес
- `stage_custom` — кастомная стадия

### GET /api/admin/tenants/{id}/amocrm/field-mapping

Список текущих маппингов.

### PUT /api/admin/tenants/{id}/amocrm/field-mapping

```json
{
  "mappings": [
    {"field_key": "city", "amo_field_id": "123456", "entity_type": "lead"},
    {"field_key": "district", "amo_field_id": "123457", "entity_type": "lead"},
    {"field_key": "object_type", "amo_field_id": "123458", "entity_type": "contact"}
  ]
}
```

---

## Команды /stop и /start

- `/stop` — отключить AI в этом чате (mute)
- `/start` — включить AI обратно
- `/stop all` — отключить AI для всех чатов этого номера
- `/start all` — включить AI для всех чатов

Команды работают для **входящих** сообщений от клиента (не от менеджера).

---

## Mute из карточки лида

```
POST /api/admin/leads/{lead_id}/mute
Body: {"muted": true}
```

Ищет conversation по `lead.bot_user_id` и ставит `is_enabled=false` в `chat_ai_states`.

**Важно:** Lead должен иметь `tenant_id`. Если `tenant_id` отсутствует — ошибка `lead_has_no_tenant_id`.

---

## Диагностика: Snapshot

```
GET /api/admin/diagnostics/tenant/{id}/snapshot
```

Возвращает полное состояние tenant:

```json
{
  "ok": true,
  "tenant_id": 1,
  "tenant_name": "Example",
  "settings": {
    "whatsapp_source": "chatflow",
    "ai_enabled_global": true,
    "ai_enabled": true,
    "ai_prompt_len": 500,
    "ai_after_lead_submitted_behavior": "polite_close"
  },
  "whatsapp": {
    "binding_exists": true,
    "is_active": true,
    "accounts_count": 1
  },
  "amocrm": {
    "connected": true,
    "is_active": true,
    "base_domain": "example.amocrm.ru",
    "token_expires_at": "2025-02-10T12:00:00"
  },
  "mappings": {
    "pipeline_count": 5,
    "field_count": 3
  }
}
```

---

## ENV переменные для amoCRM OAuth

```
AMO_CLIENT_ID=your_client_id
AMO_CLIENT_SECRET=your_client_secret
AMO_REDIRECT_URL=https://your-api.com/api/integrations/amocrm/callback
```

Получить `client_id` и `client_secret` можно в настройках интеграции в amoCRM.

---

## Access Rules (Права доступа)

Для всех endpoints `/api/admin/tenants/{id}/*` действуют следующие правила:

| Роль | Доступ |
|------|--------|
| **admin** (`is_admin=True`) | ✅ Полный доступ ко **всем** tenants |
| **owner** (default_owner_user_id или role=owner в tenant_users) | ✅ Полный доступ к своему tenant |
| **rop** (role=rop в tenant_users) | ✅ Доступ только к своему tenant |
| **manager** (role=manager в tenant_users) | ❌ Нет доступа к настройкам tenant |
| **Без роли** | ❌ 403 Forbidden |

### Ошибки доступа (403)

При отказе в доступе возвращается JSON с конкретной причиной:

```json
{
  "ok": false,
  "detail": "Forbidden: role=manager cannot access tenant settings. Contact your admin."
}
```

Или:

```json
{
  "ok": false,
  "detail": "Forbidden: user user@example.com has no access to tenant 2. Required: admin, owner, or rop role."
}
```

---

## Безопасность

- Токены amoCRM **не логируются** (только первые 4 символа при необходимости)
- Все admin endpoints требуют JWT с ролью admin/owner/rop
- Callback OAuth публичный, но state проверяется на формат `tenant_{id}`
