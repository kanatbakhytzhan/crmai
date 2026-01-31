# Unified Conversation History

История чатов хранится в БД по каналам и пользователям. Один движок используется и для WhatsApp webhook, и для `/api/chat` (веб-чат). Контекст пользователей не смешивается.

## Сервис

**Файл:** `app/services/conversation_service.py`

- **get_or_create_conversation(db, tenant_id, channel, external_id, phone_number_id=None)** — получить или создать conversation по `(channel, phone_number_id, external_id)`. Для веба `phone_number_id=None` (в БД хранится как пустая строка).
- **append_user_message(db, conversation_id, text, raw_json=None)** — добавить сообщение пользователя.
- **append_assistant_message(db, conversation_id, text, raw_json=None)** — добавить ответ ассистента.
- **build_context_messages(db, conversation_id, limit=20)** — последние N сообщений в формате `[{role, content}]` для OpenAI (хронологический порядок).
- **trim_if_needed(db, conversation_id, keep_last=50)** — удалить старые сообщения, оставить последние (опционально).

## Схема (таблицы)

- **conversations** — ключ `(channel, phone_number_id, external_id)`; один чат на канал и пользователя.
- **conversation_messages** — роль (user/assistant/system), текст, created_at.

## Идентификация сессии

### WhatsApp (webhook)

- **channel:** `"whatsapp"`
- **tenant_id:** из `whatsapp_accounts` по `phone_number_id`.
- **external_id:** номер отправителя (`from` в payload).
- **phone_number_id:** бизнес-номер (metadata.phone_number_id).

### Веб-чат (/api/chat)

- **channel:** `"web"`
- **tenant_id:** пока `null` (при MULTITENANT_ENABLED можно расширить).
- **external_id:** при авторизации — `current_user.email` или `str(current_user.id)`; без токена — `"guest:<ip>"` (request.client.host).
- **phone_number_id:** не используется (пустая строка в БД).

В результате у каждого пользователя (email или guest:ip) и у каждого WA-номера — свой conversation, контекст между пользователями не смешивается.

## Интеграция

- **WhatsApp:** после определения tenant и создания лида вызывается conversation_service: get_or_create_conversation → append_user_message → build_context_messages → OpenAI → append_assistant_message. Лид и webhook-ответ не меняются.
- **/api/chat:** после get_or_create_bot_user (для лидов) вызывается conversation_service для истории: get_or_create_conversation(web, external_id) → append_user_message → build_context_messages → OpenAI → append_assistant_message. Создание лида и уведомление в Telegram без изменений.

## Проверка изоляции

- Два разных **external_id** (например `user1@test.com` и `guest:127.0.0.1`) — создаются два разных conversation, сообщения не смешиваются.
- Один и тот же **external_id** дважды — переиспользуется один conversation, количество сообщений растёт.

Скрипт: `scripts/verify_conversation_isolation.py` (см. вывод в консоль).
