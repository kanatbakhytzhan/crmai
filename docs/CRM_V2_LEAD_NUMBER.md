# CRM v2: нумерация лидов (lead_number)

## Как убедиться, что lead_number проставляется

1. **Включите CRM v2** (опционально для таблицы v2): в `.env` задайте `CRM_V2_ENABLED=true`.
2. **Создайте новый лид** — через веб-чат (`POST /api/chat`), Telegram или WhatsApp/ChatFlow webhook (логику webhook не меняем).
3. **Проверьте ответы API:**
   - `GET /api/leads` — в каждом элементе `leads[]` должно быть поле `lead_number` (число у новых лидов, `null` у старых).
   - `GET /api/leads/{id}` — у созданного лида в ответе есть `lead_number` (следующий после max по БД).
4. **Проверка в БД (опционально):**
   - PostgreSQL: `SELECT id, lead_number, name, created_at FROM leads ORDER BY id DESC LIMIT 5;`
   - У новых лидов `lead_number` заполнен (1, 2, 3, …), у старых может быть `NULL`.
5. **Таблица v2 (при CRM_V2_ENABLED=true):**  
   `GET /api/v2/leads/table` с JWT админа. **Основной ключ ответа — `leads`** (как в GET /api/leads). Поле `rows` дублирует `leads` на один релиз для обратной совместимости.

**Нумерация по tenant/owner:** при создании лида номер назначается в рамках `tenant_id` (если есть) или в рамках `owner_id` (fallback). В рамках одной группы номера уникальны (1, 2, 3, …). Старые лиды без номера можно заполнить бэкфиллом.

### Бэкфилл для старых лидов

Чтобы в CRM v2 в колонке **#** везде было число (вместо "—"):

1. Вызовите **POST /api/admin/diagnostics/backfill-lead-numbers** с JWT админа.
2. Ответ: `{ "ok": true, "updated": N }` — сколько лидов получили `lead_number`.
3. Группировка как при создании: по `tenant_id`, при его отсутствии — по `owner_id`. Внутри группы нумерация по `created_at` ASC.

После бэкфилла **GET /api/leads** и **GET /api/v2/leads/table** отдают непустой `lead_number` у всех лидов.

---

## Единый контракт списка лидов (Swagger/API)

Оба эндпоинта возвращают массив лидов под ключом **`leads`** и счётчик **`total`**:

- **GET /api/leads** → `{ "leads": [...], "total": N }`
- **GET /api/v2/leads/table** → `{ "ok": true, "leads": [...], "rows": [...], "total": N }`  
  Основной ключ — **`leads`**. Поле `rows` — дубликат (deprecated), будет удалён. В Swagger описание указано в response schema и в summary эндпоинта.
