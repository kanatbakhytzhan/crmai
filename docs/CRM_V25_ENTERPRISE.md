# CRM v2.5 Enterprise

Новые возможности: иерархия ролей (Owner→ROP→Manager), лид с первого сообщения, per-chat mute без ошибки tenant_id, применение tenant ai_prompt, гибкое распределение лидов, уведомления.

---

## Новые эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | /api/admin/tenants/{tenant_id}/users | Список пользователей (parent_user_id, is_active) |
| POST | /api/admin/tenants/{tenant_id}/users | Добавить пользователя (email, role, parent_user_id?, is_active?) |
| PATCH | /api/admin/tenants/users/{tenant_user_id}?tenant_id= | Обновить role/parent_user_id/is_active |
| DELETE | /api/admin/tenants/users/{tenant_user_id}?tenant_id= | Soft delete (is_active=false) |
| GET | /api/admin/diagnostics/leads-health | Доля лидов без tenant_id, sample |
| POST | /api/leads/{lead_id}/ai-mute | Mute по лиду (исправлено: резолв tenant по me) |
| POST | /api/ai/mute | Mute по chat_key (body: chat_key, muted) |
| POST | /api/leads/selection | Отбор lead_ids по фильтрам |
| POST | /api/leads/assign/plan | Распределение по плану (by_ranges, dry_run) |
| GET | /api/notifications?unread=true | Список уведомлений |
| POST | /api/notifications/{id}/read | Отметить прочитанным |
| POST | /api/notifications/read-all | Отметить все прочитанными |

---

## Примеры curl

### Selection (отбор лидов)

```bash
export TOKEN="your_jwt"
curl -s -X POST "http://localhost:8000/api/leads/selection" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": { "status": ["new", "in_progress"], "assigned": "none" },
    "sort": "created_at",
    "direction": "desc",
    "limit": 100
  }'
# Ответ: { "ok": true, "lead_ids": [1,2,...], "total": N }
```

### Assign plan (dry_run)

```bash
curl -s -X POST "http://localhost:8000/api/leads/assign/plan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_ids": [10,11,12,13,14,15],
    "mode": "by_ranges",
    "plans": [
      { "manager_user_id": 5, "from_index": 1, "to_index": 3 },
      { "manager_user_id": 6, "from_index": 4, "to_index": 6 }
    ],
    "set_status": "in_progress",
    "dry_run": true
  }'
# Ответ: { "ok": true, "preview": [{ "lead_id": 10, "to_manager_id": 5 }, ...], "errors": [] }
```

### Assign plan (execute)

```bash
curl -s -X POST "http://localhost:8000/api/leads/assign/plan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_ids": [10,11,12],
    "mode": "by_ranges",
    "plans": [{ "manager_user_id": 5, "from_index": 1, "to_index": 3 }],
    "dry_run": false
  }'
# Ответ: { "ok": true, "assigned": 3, "errors": [] }
```

### Mute по chat_key

```bash
curl -s -X POST "http://localhost:8000/api/ai/mute" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "chat_key": "77001234567@s.whatsapp.net", "muted": true }'
# Ответ: { "ok": true, "muted": true, "chat_key": "..." }
```

---

## Проверка применения tenant prompt

1. Включите в env: `CRM_DEBUG_PROMPT=true`.
2. Отправьте сообщение в WhatsApp (ChatFlow) в чат tenant, у которого задан `ai_prompt` в настройках.
3. В логах stdout должно появиться:
   `[CRM_DEBUG_PROMPT] tenant_id=1 ai_prompt_len=... using_default_prompt=false lead_id=...`
4. Если `using_default_prompt=true` — tenant.ai_prompt пустой или не подставляется; проверьте, что в админке у tenant заполнен AI prompt и что в webhook используется tenant_id из привязки.

---

## Чеклист ручной проверки (5–8 шагов)

1. **Роли и команда**  
   GET /api/admin/tenants/{tenant_id}/users — в ответе есть `parent_user_id`, `is_active`.  
   POST пользователя с role=manager, parent_user_id=id_rop.  
   PATCH /api/admin/tenants/users/{id}?tenant_id= — смена role/is_active.  
   DELETE (soft) — запись остаётся с is_active=false.

2. **Лид с первого сообщения**  
   Отправить первое сообщение с нового номера в ChatFlow — в CRM должен появиться лид со стадией «Новые», tenant_id заполнен.

3. **Leads health**  
   GET /api/admin/diagnostics/leads-health — проверить total_leads, leads_without_tenant_id и sample.

4. **Per-chat mute**  
   Открыть лид без tenant_id (или с) в CRM, нажать «Отключить AI в этом чате» — не должно быть 400/422.  
   POST /api/ai/mute с chat_key=remoteJid, muted=true — в логах /stop по этому чату должен учитываться mute.

5. **Tenant prompt**  
   Заполнить ai_prompt в настройках tenant, отправить сообщение в WhatsApp — в логах при CRM_DEBUG_PROMPT=true: using_default_prompt=false.

6. **Selection и assign plan**  
   POST /api/leads/selection с фильтрами — получить lead_ids.  
   POST /api/leads/assign/plan с dry_run=true — проверить preview.  
   POST с dry_run=false — лиды должны назначиться, в audit_log — запись bulk_assign_plan.

7. **Уведомления**  
   Создать лид через webhook — owner/rop получают запись в notifications.  
   Назначить лид на менеджера — у менеджера появляется уведомление.  
   GET /api/notifications?unread=true, POST read и read-all.

8. **Обратная совместимость**  
   GET/POST /api/leads, assign/unassign, comments, WhatsApp/ChatFlow webhook, reset-password, change-password, ai_prompt/ai_enabled, whatsapp attach/list — работают без изменений контрактов.
