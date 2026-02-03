# Назначение лидов (Owner / ROP / Manager)

## Роли

- **owner** — видит все лиды tenant, может назначать и снимать назначение.
- **rop** — то же.
- **manager** — видит только лиды, где `assigned_to_user_id == current_user.id`; не может назначать.

## Эндпоинты

### GET /api/me/role

Роль и tenant текущего пользователя.

```bash
curl -s -H "Authorization: Bearer YOUR_JWT" https://your-api.com/api/me/role
```

Ответ: `{ "tenant_id": 1, "role": "owner" }` или `{ "tenant_id": null, "role": null }`.

### PATCH /api/leads/{lead_id}/assign

Назначить лид на менеджера (или снять: `assigned_to_user_id: null`). Только owner/rop.

```bash
# Назначить на user_id=5
curl -X PATCH -H "Authorization: Bearer YOUR_JWT" -H "Content-Type: application/json" \
  -d '{"assigned_to_user_id": 5}' \
  https://your-api.com/api/leads/1/assign

# Снять назначение
curl -X PATCH -H "Authorization: Bearer YOUR_JWT" -H "Content-Type: application/json" \
  -d '{"assigned_to_user_id": null}' \
  https://your-api.com/api/leads/1/assign
```

### PATCH /api/leads/{lead_id}/unassign

Снять назначение (assigned_to_user_id = null). Только owner/rop.

```bash
curl -X PATCH -H "Authorization: Bearer YOUR_JWT" \
  https://your-api.com/api/leads/1/unassign
```

### POST /api/leads/assign/bulk

Массовое назначение. Только owner/rop.

```bash
curl -X POST -H "Authorization: Bearer YOUR_JWT" -H "Content-Type: application/json" \
  -d '{"lead_ids": [1, 2, 3], "assigned_to_user_id": 5}' \
  https://your-api.com/api/leads/assign/bulk
```

Ответ: `{ "ok": true, "assigned": 3, "skipped": 0, "skipped_ids": [] }`.

### GET /api/leads

В каждом лиде добавлены поля: `assigned_to_user_id`, `assigned_at` (и по-прежнему `assigned_user_id`, `assigned_user_email`, `assigned_user_name`).

## Что проверить в /docs

1. **GET /api/me/role** — описание и схема ответа (tenant_id, role).
2. **PATCH /api/leads/{lead_id}/assign** — тело с `assigned_to_user_id` (optional integer).
3. **PATCH /api/leads/{lead_id}/unassign** — без тела.
4. **POST /api/leads/assign/bulk** — тело: `lead_ids`, `assigned_to_user_id`.
5. **GET /api/leads** — в схеме ответа лида: `assigned_to_user_id`, `assigned_at`.
