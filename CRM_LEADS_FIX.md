# Исправление: лиды из ИИ-менеджера в GET /api/leads для CRM

## Проблема

- Лиды создаются через POST /api/chat, уходят в Telegram, но GET /api/leads возвращал 0 для аккаунта kana.bahytzhan@gmail.com.

## Причина

- GET /api/leads фильтрует по `owner_id = current_user.id`.
- В гостевом режиме (без токена) владелец лида брался из `get_first_user()` — первый пользователь по `User.id ASC`.
- Если в БД несколько пользователей или порядок другой, «первый» пользователь мог быть не тем, кто логинится в CRM. Тогда лиды создавались с другим `owner_id`, и при запросе GET /api/leads под своим аккаунтом возвращался пустой список.

## Что сделано (минимальный патч)

### 1. Гарантированный владелец для гостевых лидов (по email)

**Файл:** `app/core/config.py`

- Добавлена опция `default_owner_email: Optional[str] = None`.
- Если в env задан `DEFAULT_OWNER_EMAIL` (например `kana.bahytzhan@gmail.com`), гостевые лиды привязываются к пользователю с этим email, а не к «первому по id».

**Файл:** `app/api/endpoints/chat.py`

- В гостевом режиме:
  - если задан `settings.default_owner_email`, ищется пользователь по email (`get_user_by_email`);
  - если не найден — fallback на `get_first_user()`;
  - если email не задан — как раньше, только `get_first_user()`.
- Зависимость от того, что владелец должен иметь id=1, убрана: владелец определяется по email.

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

- В env веб-сервиса добавлена переменная `DEFAULT_OWNER_EMAIL` (sync: false — вводится вручную в дашборде).
- На Render в Environment задайте `DEFAULT_OWNER_EMAIL=kana.bahytzhan@gmail.com` (или ваш email). Все гостевые лиды будут привязаны к этому пользователю по email; id=1 не требуется.

## Как проверить

1. **Пользователь с нужным email зарегистрирован**
   - POST /api/auth/register (email, password, company_name) для вашего аккаунта, либо он уже есть в БД.

2. **На Render**
   - В Environment сервиса `crm-api` задать `DEFAULT_OWNER_EMAIL=ваш@email.com` (тот же email, под которым логинитесь в CRM).
   - Задеплоить последнюю версию.

3. **Создать лид через чат**
   - Открыть веб-чат (без авторизации): например `https://crm-api-5vso.onrender.com/`.
   - Пройти диалог до момента, когда ИИ создаёт заявку (имя + телефон).
   - Проверить: в Telegram приходит уведомление о новом лиде.

4. **Проверить GET /api/leads**
   - Залогиниться: POST /api/auth/login (username=kana.bahytzhan@gmail.com, password=...).
   - Получить токен, затем: GET /api/leads с заголовком `Authorization: Bearer <token>`.
   - Ожидание: в ответе хотя бы один лид (только что созданный), с `owner_id` вашего пользователя и `status="new"`.

5. **Логи на Render**
   - При создании лида: строка вида `[OK] Lid sozdan: id=..., owner_id=..., status=new`.
   - При запросе лидов: строка вида `[GET /api/leads] current_user.id=..., email=..., leads_count=1`.

## Ограничения (соблюдены)

- Контракт эндпоинтов не менялся: auth/login и GET/PATCH/DELETE /api/leads работают как раньше.
- Интеграций с WhatsApp/парсингом не добавлялось.
- Изменения только в описанных файлах; причина (owner_id для гостей + сериализация status) устранена минимально.

## Итог

- Гостевые лиды привязываются к владельцу по `DEFAULT_OWNER_EMAIL` (email пользователя, под которым вы логинитесь в CRM).
- GET /api/leads возвращает лиды по `current_user.id`; лиды из чата попадают в выдачу тому, чей email задан в `DEFAULT_OWNER_EMAIL`.
- В CRM (PWA) во вкладке «Необработанные» можно показывать лиды с `status === "new"` из ответа GET /api/leads.
