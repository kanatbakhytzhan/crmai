# Автоназначение лидов (CRM v3)

Правила автоназначения позволяют назначать новых лидов на менеджеров по городу, языку, типу объекта, времени и нагрузке. Доступ к настройке — только **admin**, **owner**, **rop**.

## Правила (Auto Assign Rules)

### CRUD

- **GET** `/api/admin/tenants/{tenant_id}/auto-assign-rules?active_only=false`  
  Список правил по tenant (сортировка по `priority` ASC).

- **POST** `/api/admin/tenants/{tenant_id}/auto-assign-rules`  
  Создать правило (body: `name`, `is_active`, `priority`, `match_*`, `time_from`/`time_to`, `days_of_week`, `strategy`, `fixed_user_id`).

- **PATCH** `/api/admin/auto-assign-rules/{rule_id}`  
  Обновить правило (частично).

- **DELETE** `/api/admin/auto-assign-rules/{rule_id}`  
  Удалить правило.

### Поля правила

| Поле | Описание |
|------|----------|
| `name` | Название |
| `is_active` | Включено/выключено |
| `priority` | Чем меньше — тем раньше проверяется правило |
| `match_city` | Точное совпадение города (без учёта регистра) |
| `match_language` | Язык: `ru`, `kk` |
| `match_object_type` | Тип объекта (например «дом», «үй») |
| `match_contains` | Подстрока в `summary` или первом сообщении |
| `time_from`, `time_to` | Часы 0–23 (время по Алматы) |
| `days_of_week` | Дни недели: `1,2,3,4,5` (1 = понедельник) |
| `strategy` | `round_robin` \| `least_loaded` \| `fixed_user` |
| `fixed_user_id` | Обязателен при `strategy=fixed_user` |

### Стратегии

- **round_robin** — по очереди по списку менеджеров (роль manager/member в tenant). Состояние в `rr_state`.
- **least_loaded** — менеджер с минимальным числом активных лидов (NEW/IN_PROGRESS) за последние 7 дней.
- **fixed_user** — всегда назначать на `fixed_user_id`.

Если лид уже назначен (`assigned_user_id` задан), автоназначение не выполняется. Если ни одно правило не сработало или нет менеджеров — лид остаётся без назначения.

---

## Назначение по диапазону (By Range)

**POST** `/api/admin/leads/assign/by-range`

Позволяет ROP раздать лиды по диапазону индексов (например «5–12») с выбранной стратегией.

### Body

- **tenant_id** — обязателен.  
- **from_index**, **to_index** — индексы 1-based (например 5 и 12 = лиды с 5-го по 12-й).  
- **strategy** — `round_robin` \| `fixed_user` \| `custom_map`.  
- **fixed_user_id** — при `strategy=fixed_user`.  
- **custom_map** — при `strategy=custom_map`:  
  `[{"user_id": 10, "count": 5}, {"user_id": 11, "count": 3}]` — первые 5 лидов → user 10, следующие 3 → user 11.  
- **filters** — опционально:  
  `{"status": "new", "only_unassigned": true}`.

Лидовая выборка: по tenant, с учётом прав текущего пользователя (owner/rop видят все лиды tenant). Сортировка по `created_at` ASC. Из этой выборки берётся срез `[from_index - 1 : to_index]` и каждому лиду выставляется `assigned_user_id` по выбранной стратегии.

### Ответ

- `ok`, `total_selected`, `assigned`, `skipped`, `details` (до 50 записей с `lead_id` и `assigned_to_user_id` или `error`).
