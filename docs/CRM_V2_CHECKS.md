# CRM v2: быстрые проверки

## 1) Tenant + rop + manager (админка)

- GET /api/admin/tenants — список tenants.
- POST /api/admin/tenants/{tenant_id}/users с body `{ "email": "rop@test.com", "role": "rop" }` — если пользователя нет, создаётся с временным паролем (поле `temporary_password` в ответе).
- Аналогично добавить manager: `{ "email": "manager@test.com", "role": "manager" }`.
- GET /api/admin/tenants/{tenant_id}/users — список пользователей tenant (должны быть rop и manager).

## 2) Новый лид с WhatsApp — tenant_id и lead_number

- Отправить сообщение в WhatsApp/ChatFlow (webhook), чтобы создался лид.
- GET /api/leads (JWT владельца или rop) — у нового лида должны быть `tenant_id` и `lead_number` не null.

## 3) owner видит все лиды, manager — только назначенные

- Залогиниться как owner (или rop): GET /api/leads — все лиды tenant.
- Назначить лид manager: PATCH /api/leads/{id}/assign `{ "assigned_user_id": <manager_user_id> }`.
- Залогиниться как manager: GET /api/leads — только лиды, где `assigned_user_id` = этот manager.

## 4) bulk assign

- POST /api/leads/assign/bulk body: `{ "lead_ids": [1, 2, 3], "assigned_user_id": <manager_id>, "set_status": "in_progress" }`.
- Ответ: `{ "ok": true, "assigned": N, "skipped": M, "skipped_ids": [...] }`.

## 5) next_call_at сохраняется и возвращается

- PATCH /api/leads/{id} body: `{ "next_call_at": "2025-12-01T12:00:00" }`.
- GET /api/leads или GET /api/leads/{id} — в ответе поле `next_call_at` с указанной датой.
