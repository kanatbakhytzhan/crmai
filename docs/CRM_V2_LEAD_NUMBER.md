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
   `GET /api/v2/leads/table` с JWT админа — в `rows[]` у каждого лида есть поле `lead_number`.

Старые лиды не трогаются: у них `lead_number` остаётся `NULL`. Новые получают `max(lead_number)+1`.
