# ChatFlow.kz — подключение к FastAPI (Render)

Интеграция с ChatFlow.kz: webhook принимает входящие сообщения, формирует ответ (OpenAI или echo) и отправляет в WhatsApp через ChatFlow API.

## Переменные окружения

- **CHATFLOW_TOKEN** — токен приложения ChatFlow (обязателен для отправки ответов).
- **CHATFLOW_INSTANCE_ID** — ID инстанса WhatsApp в ChatFlow (обязателен для отправки).
- **CHATFLOW_API_BASE** — (опционально) базовый URL API, по умолчанию `https://app.chatflow.kz/api/v1`.

На Render задайте в Environment: `CHATFLOW_TOKEN`, `CHATFLOW_INSTANCE_ID`. Токены не хранить в коде.

## Формат jid

JID (идентификатор чата в WhatsApp) в ChatFlow обычно имеет вид:

- `79001234567@s.whatsapp.net` — полный формат.
- Или только номер: `79001234567` — webhook автоматически приведёт к виду `79001234567@s.whatsapp.net` (убираются `+`, пробелы, скобки).

Входящий JSON может содержать поля: `jid`, `chatId`, `from`, `sender`, `phone` или вложенные `message.from`, `data.jid` и т.п. Текст сообщения: `msg`, `text`, `message`, `body` или вложенные `message.text`, `data.msg` и т.п.

## Эндпоинты

- **GET /api/chatflow/webhook** — проверка доступности, возвращает `{"ok": true}`.
- **GET /api/chatflow/ping** — быстрая проверка деплоя, возвращает `{"ok": true, "pong": true}`.
- **POST /api/chatflow/webhook** — приём входящего JSON от ChatFlow: извлекаются jid и текст, формируется ответ (OpenAI или «Принял: …»), отправка через ChatFlow send-text. Всегда возвращает `{"ok": true}`; ошибки логируются.
  - **AI вкл/выкл:** если у первого активного tenant `ai_enabled=false`, автоответ не отправляется (входящие сохраняются).
  - **Команды в чате:** текст `/stop` или `stop` — выключить AI для tenant, ответ «AI-менеджер выключен ✅». Текст `/start` или `start` — включить AI, ответ «AI-менеджер включен ✅».

## Как проверить

1. **Проверка деплоя:**  
   `GET https://your-app.onrender.com/api/chatflow/ping` — должен вернуть `{"ok": true, "pong": true}`.

2. **Test Webhook в ChatFlow:**  
   В настройках интеграции ChatFlow укажите URL: `https://your-app.onrender.com/api/chatflow/webhook`. Используйте «Test Webhook» — должен вернуться `200` и `{"ok": true}`.

3. **Отправка сообщения:**  
   Отправьте сообщение в WhatsApp на номер, привязанный к инстансу ChatFlow. В логах Render должны появиться строки `[CHATFLOW] INCOMING: ...`, `[CHATFLOW] SEND ok jid=...` (если CHATFLOW_TOKEN и CHATFLOW_INSTANCE_ID заданы). Ответ бота уходит через ChatFlow send-text.

4. **Ручная проверка send-text (опционально):**  
   GET-запрос к ChatFlow API с параметрами `token`, `instance_id`, `jid`, `msg` (см. документацию ChatFlow). В логах бэкенда при успешной отправке: `[CHATFLOW] SEND response status=200 body=...`.
