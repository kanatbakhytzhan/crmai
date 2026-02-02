# WhatsApp/ChatFlow привязка — UPSERT и ответ

## Как работает attach/upsert

- **Одна запись на tenant:** для каждого tenant допускается одна активная привязка (одна запись в `whatsapp_accounts`).
- **POST** `/api/admin/tenants/{tenant_id}/whatsapp` (Attach) ведёт себя как **UPSERT**:
  - если у tenant уже есть запись — она **обновляется** (chatflow_token, chatflow_instance_id, phone_number, is_active);
  - если записи нет — **создаётся** новая;
  - дубликаты не создаются.
- **Ответ:** JSON с **сохранёнными** значениями: id, tenant_id, phone_number, chatflow_token_masked (первые 4 символа + "***"), chatflow_instance_id, is_active, created_at, updated_at. Полный `chatflow_token` в ответ не отдаётся.

## Валидация

- **active=true** → обязательны непустые `chatflow_token` и `chatflow_instance_id` (иначе 400).
- **active=false** → можно сохранять с пустыми token/instance_id; при обновлении существующей записи пустые значения **не затирают** уже сохранённые token/instance_id.

## Логи

- В attach/upsert при входе: `tenant_id`, `active`, `phone_number`, `token_len`, `instance_len`.
- После сохранения: `id` сохранённой записи.

## Изменённые файлы

- **app/database/models.py** — `WhatsAppAccount.updated_at`, свойство `chatflow_token_masked`
- **app/database/session.py** — миграция `whatsapp_accounts.updated_at` (Postgres + SQLite)
- **app/schemas/tenant.py** — `WhatsAppAccountCreate.is_active`, `WhatsAppAccountResponse`: убран `chatflow_token`, добавлены `chatflow_token_masked`, `updated_at`
- **app/database/crud.py** — `update_whatsapp_account`: не затирать token/instance при None; проставление `updated_at`
- **app/api/endpoints/admin_tenants.py** — POST attach = UPSERT, валидация, логи, ответ с masked token; PUT upsert — логи saved id
- **app/api/endpoints/admin_diagnostics.py** — smoke-test: upsert whatsapp для первого tenant, затем list и проверка
