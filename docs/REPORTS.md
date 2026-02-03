# Отчёты (ROP/Owner)

Доступ к отчётам имеют только **admin**, **owner** и **rop**. Если у пользователя есть только один tenant, `tenant_id` можно не передавать (подставится из `/api/me/role`).

## 1. Сводка (Summary)

**GET** `/api/admin/reports/summary?tenant_id=&date_from=&date_to=`

Возвращает:

- **total_leads** — всего лидов за период  
- **new_leads**, **in_progress**, **done**, **cancelled** — по статусам  
- **avg_time_to_assign_sec** — среднее время от создания до назначения (сек.)  
- **avg_time_to_first_response_sec** — среднее время до первого ответа менеджера (сек.)  
- **conversion_rate_done** — доля закрытых в сделку: `done / total_leads`  
- **managers** — по каждому менеджеру:
  - `user_id`, `email`
  - `leads_assigned_count`, `leads_done_count`, `leads_new_count`
  - `avg_response_time_sec`
  - `active_load` — количество лидов в статусе NEW или IN_PROGRESS  

Агрегация только по выбранному `tenant_id` и опционально по периоду `date_from` / `date_to` (ISO формат).

---

## 2. Нагрузка (Workload)

**GET** `/api/admin/reports/workload?tenant_id=&date_from=&date_to=`

Таблица по менеджерам и «без назначения»:

- **manager_user_id**, **manager_email**
- **assigned** — сколько лидов назначено
- **unassigned** — только в первой строке (лиды без назначения)
- **active**, **done**, **cancelled**

---

## 3. SLA (скорость первого ответа)

**GET** `/api/admin/reports/sla?tenant_id=&date_from=&date_to=`

- Распределение по времени до первого ответа:
  - **under_5m** — до 5 минут  
  - **under_15m** — до 15 минут  
  - **under_1h** — до 1 часа  
  - **over_1h** — более 1 часа  
- **problem_leads** — список лидов с ответом более 1 часа (до 50 шт.):  
  `lead_id`, `created_at`, `assigned_at`, `first_response_at`, `assigned_to_user_id`.

Первый ответ фиксируется автоматически при первом комментарии менеджера/rop/owner или при смене статуса на «В работе» (in_progress).
