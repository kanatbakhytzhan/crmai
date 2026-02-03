# CRM v2: Воронки, Задачи, SSE

Документация по API воронок (pipelines/stages), задач по лидам (follow-ups) и realtime-событиям (SSE).

В Swagger (`/docs`) используются теги: **Pipelines**, **Tasks**, **Events**.

---

## 1. Воронки (Pipelines / Stages)

### Роли
- **owner / rop / admin** — полный доступ: создание/редактирование воронок и стадий.
- **manager** — только чтение: `GET /api/pipelines`.

### Эндпоинты

**Список воронок (со стадиями)**  
`GET /api/pipelines?tenant_id=...`  
Header: `Authorization: Bearer <token>`

Ответ:
```json
{
  "pipelines": [
    {
      "id": 1,
      "tenant_id": 1,
      "name": "Основная",
      "is_default": true,
      "created_at": "2025-01-28T12:00:00",
      "stages": [
        { "id": 1, "pipeline_id": 1, "name": "Новые", "order_index": 0, "color": null, "is_closed": false, "created_at": "..." },
        { "id": 2, "pipeline_id": 1, "name": "В работе", "order_index": 1, "color": null, "is_closed": false, "created_at": "..." }
      ]
    }
  ],
  "total": 1
}
```

**Создать воронку** (owner/rop/admin)  
`POST /api/pipelines`  
Body: `{ "name": "Вторая воронка", "is_default": false }`

**Обновить воронку**  
`PATCH /api/pipelines/{pipeline_id}`  
Body: `{ "name": "Новое имя", "is_default": true }`

**Добавить стадию**  
`POST /api/pipelines/{pipeline_id}/stages`  
Body: `{ "name": "Новая стадия", "order_index": 5, "color": "#00ff00", "is_closed": false }`

**Обновить стадию**  
`PATCH /api/pipelines/stages/{stage_id}`  
Body: `{ "name": "Переименованная", "order_index": 1, "color": "#ff0000", "is_closed": false }`

**Удалить стадию** (если нет лидов в этой стадии)  
`DELETE /api/pipelines/stages/{stage_id}`

**Переместить лид в стадию**  
`PATCH /api/leads/{lead_id}/stage`  
Body: `{ "stage_id": 2 }`  
- Manager может менять стадию только у лидов, назначенных ему.  
- owner/rop/admin — у всех лидов tenant.

Пример (curl):
```bash
export TOKEN="your_jwt_token"
curl -s -X PATCH "http://localhost:8000/api/leads/42/stage" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"stage_id": 2}'
```

---

## 2. Задачи по лидам (Follow-ups)

Типы: `call`, `meeting`, `note`. Статусы: `open`, `done`, `cancelled`.

### Эндпоинты

**Список задач по лиду**  
`GET /api/leads/{lead_id}/tasks`  
Manager — только для лидов, назначенных ему.

**Создать задачу**  
`POST /api/leads/{lead_id}/tasks`  
Body: `{ "type": "call", "due_at": "2025-01-29T14:00:00", "note": "Перезвонить", "assigned_to_user_id": 3 }`  
(если `assigned_to_user_id` не передан — назначается текущий пользователь)

**Обновить задачу**  
`PATCH /api/leads/tasks/{task_id}`  
Body: `{ "status": "done", "due_at": "2025-01-30T10:00:00", "note": "Обновлённый текст" }`

**Список задач пользователя / tenant**  
`GET /api/tasks?status=open&due=today`  
- **Manager** — только свои задачи.  
- **owner/rop/admin** — все задачи по своему tenant.  
Параметры: `status` (open | done | cancelled), `due` (today | overdue | week).

Примеры curl:
```bash
# Задачи по лиду
curl -s "http://localhost:8000/api/leads/42/tasks" -H "Authorization: Bearer $TOKEN"

# Создать задачу
curl -s -X POST "http://localhost:8000/api/leads/42/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"call","due_at":"2025-01-29T15:00:00","note":"Перезвон"}'

# Задачи на сегодня
curl -s "http://localhost:8000/api/tasks?status=open&due=today" -H "Authorization: Bearer $TOKEN"
```

---

## 3. Realtime: SSE (Events)

**Поток событий**  
`GET /api/events/stream`  
Header: `Authorization: Bearer <token>`

Соединение держится открытым. События:
- `connected` — после подключения.
- `ping` — каждые ~30 сек при отсутствии других событий.
- `lead_created` — новый лид (WhatsApp/Chatflow/сайт).
- `lead_updated` — обновление лида (стадия, назначение, комментарий, задача).

Формат каждого события (в теле `data:`):
```json
{"event": "lead_created", "data": {"lead_id": 123, "tenant_id": 1}}
```
или
```json
{"event": "lead_updated", "data": {"lead_id": 123, "tenant_id": 1}}
```

Пример (curl, вывод сырых SSE строк):
```bash
curl -s -N "http://localhost:8000/api/events/stream" \
  -H "Authorization: Bearer $TOKEN"
```

Если SSE недоступно (прокси/среда), фронт может продолжать опрос `GET /api/leads` или `GET /api/v2/leads/table` как раньше.

---

## Проверка после деплоя

1. **Воронка**: `GET /api/pipelines` — у tenant должна быть воронка «Основная» со стадиями (Новые, В работе, …).  
2. **Новый лид из webhook** — у лида должны быть заполнены `pipeline_id`, `stage_id` (стадия «Новые»), `moved_to_stage_at`.  
3. **Перемещение**: `PATCH /api/leads/{id}/stage` с `stage_id` из списка стадий.  
4. **Задачи**: `POST /api/leads/{id}/tasks`, затем `GET /api/leads/{id}/tasks` и `GET /api/tasks?status=open&due=today`.  
5. **SSE**: открыть `GET /api/events/stream` с Bearer, создать лид через webhook — в потоке должно прийти событие `lead_created`.
