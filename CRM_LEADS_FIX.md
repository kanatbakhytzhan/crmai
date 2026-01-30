# Исправление: лиды из ИИ-менеджера в GET /api/leads для CRM

## Проблема

- Лиды создаются через POST /api/chat, уходят в Telegram, но GET /api/leads возвращал 0 для аккаунта kana.bahytzhan@gmail.com.

## Причина

- GET /api/leads фильтрует по `owner_id = current_user.id`.
- В гостевом режиме (без токена) владелец лида брался из `get_first_user()` — первый пользователь по `User.id ASC`.
- Если в БД несколько пользователей или порядок другой, «первый» пользователь мог быть не тем, кто логинится в CRM (kana). Тогда лиды создавались с другим `owner_id`, и при запросе GET /api/leads под kana возвращался пустой список.

## Что сделано (минимальный патч)

### 1. Гарантированный владелец для гостевых лидов

**Файл:** `app/core/config.py`

- Добавлена опция `default_owner_id: Optional[int] = None`.
- Если в env задан `DEFAULT_OWNER_ID` (например `1`), гостевые лиды всегда создаются с этим `owner_id`, а не «первым пользователем» из БД.

**Файл:** `app/api/endpoints/chat.py`

- В гостевом режиме:
  - если задан `settings.default_owner_id`, берётся пользователь с этим id (`get_user_by_id`);
  - если такого пользователя нет, используется прежняя логика `get_first_user()`.
- Так лиды с веб-чата гарантированно привязываются к нужному аккаунту (например, kana с id=1).

### 2. Диагностические логи

**В `chat.py` после `crud.create_lead(...)`:**

- Логируется: `lead.id`, `lead.owner_id`, `lead.status` (значение, например `"new"`).
- По логам видно, что лид создан и с каким владельцем.

**В GET /api/leads:**

- Логируется: `current_user.id`, `current_user.email`, `leads_count`.
- По логам видно, под кем запрашиваются лиды и сколько их вернулось.

### 3. Статус лида и ответ API

- `crud.create_lead` по-прежнему создаёт лид со статусом `LeadStatus.NEW` (в БД это уже было).
- Ответ GET /api/leads сериализуется через `LeadResponse`: поле `status` всегда строка (`"new"`, `"in_progress"`, `"done"`, `"cancelled"`), в т.ч. для CRM.

**Файлы:** `app/schemas/lead.py`, `app/api/endpoints/chat.py`

- В `LeadResponse` добавлен `field_validator` для `status`: enum из БД приводится к строке (`.value`).
- В эндпоинте GET /api/leads возвращается `{"leads": [LeadResponse.model_validate(l) for l in leads], "total": ...}`.

### 4. Render

**Файл:** `render.yaml`

- В env веб-сервиса добавлена переменная `DEFAULT_OWNER_ID=1`.
- На Render все гостевые лиды будут с `owner_id=1`. Нужно, чтобы аккаунт kana (kana.bahytzhan@gmail.com) был зарегистрирован первым и имел `id=1`.

## Как проверить

1. **Убедиться, что kana — пользователь с id=1**
   - Зарегистрировать kana первым: POST /api/auth/register (email, password, company_name).
   - Либо в БД: `SELECT id, email FROM users ORDER BY id;` — kana должен быть с `id=1`.

2. **На Render**
   - В Environment сервиса `crm-api` задать `DEFAULT_OWNER_ID=1` (если ещё не добавлено через render.yaml).
   - Задеплоить последнюю версию.

3. **Создать лид через чат**
   - Открыть веб-чат (без авторизации): например `https://crm-api-5vso.onrender.com/`.
   - Пройти диалог до момента, когда ИИ создаёт заявку (имя + телефон).
   - Проверить: в Telegram приходит уведомление о новом лиде.

4. **Проверить GET /api/leads**
   - Залогиниться: POST /api/auth/login (username=kana.bahytzhan@gmail.com, password=...).
   - Получить токен, затем: GET /api/leads с заголовком `Authorization: Bearer <token>`.
   - Ожидание: в ответе хотя бы один лид (только что созданный), с `owner_id=1` и `status="new"`.

5. **Логи на Render**
   - При создании лида: строка вида `[OK] Lid sozdan: id=..., owner_id=1, status=new`.
   - При запросе лидов: строка вида `[GET /api/leads] current_user.id=1, email=kana.bahytzhan@gmail.com, leads_count=1`.

## Ограничения (соблюдены)

- Контракт эндпоинтов не менялся: auth/login и GET/PATCH/DELETE /api/leads работают как раньше.
- Интеграций с WhatsApp/парсингом не добавлялось.
- Изменения только в описанных файлах; причина (owner_id для гостей + сериализация status) устранена минимально.

## Итог

- Гостевые лиды привязываются к владельцу по `DEFAULT_OWNER_ID` (на Render = 1).
- GET /api/leads возвращает лиды по `current_user.id`; при id=1 для kana лиды из чата попадают в выдачу.
- В CRM (PWA) во вкладке «Необработанные» можно показывать лиды с `status === "new"` из ответа GET /api/leads.
