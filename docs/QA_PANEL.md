# QA-панель BuildCRM

Простая HTML-страница для проверки API без Postman. Доступна только **admin** или **владелец tenant (owner)**.

---

## Как открыть

1. Получите JWT: в Swagger (`/docs`) выполните **POST /api/auth/login** (username = email, password = пароль).
2. Скопируйте из ответа поле `access_token`.
3. Откройте в браузере: **GET /api/admin/diagnostics/ui**  
   (полный URL: `https://your-api.com/api/admin/diagnostics/ui` или `http://localhost:8000/api/admin/diagnostics/ui`).
4. Если вы не залогинены — браузер отправит запрос без токена и получит **401**. Сначала выполните шаг 1 в Swagger, скопируйте токен, затем откройте страницу снова — вставьте токен в поле и нажмите **Save token** (токен сохранится в localStorage для последующих запросов).

---

## Как вставить JWT

- В поле **«JWT (Bearer)»** вставьте значение `access_token` из ответа **POST /api/auth/login** (без слова «Bearer», только сам токен).
- Нажмите **Save token** — токен сохранится в браузере (localStorage). Дальнейшие нажатия кнопок будут отправлять запросы с заголовком `Authorization: Bearer <ваш_токен>`.

---

## Что проверяют кнопки

| Кнопка | Метод | Описание |
|--------|--------|----------|
| **DB Tables Check** | GET /api/admin/diagnostics/db | Проверка наличия таблиц БД (tenants, users, leads, tenant_users, conversations, whatsapp_accounts и др.). |
| **Smoke Test Comments** | POST /api/admin/diagnostics/smoke-test | Создание тестового комментария к последнему лиду и проверка WhatsApp binding для первого tenant. |
| **Create Test Lead** | POST /api/admin/diagnostics/create-test-lead | Создание тестового лида. Tenant берётся из текущего пользователя или укажите tenant_id в body (через Swagger). |
| **Check Tenant Prompt** | POST /api/admin/diagnostics/test-tenant-prompt | Введите **Tenant ID** и **Message**. Проверяет, какой system prompt используется (tenant.ai_prompt или default), вызывает OpenAI и возвращает `reply_preview` (полный промпт не отдаётся). |
| **Mute Chat Test** | POST /api/admin/diagnostics/test-mute | Введите **Tenant ID** и **Chat key** (например `77001234567@s.whatsapp.net`). Выставляет mute=true, затем mute=false, возвращает шаги и результат чтения из БД. |
| **ChatFlow Webhook Ping** | POST /api/admin/diagnostics/ping-chatflow | Введите **Tenant ID** и при необходимости **RemoteJid**. Проверяет привязку ChatFlow (token/instance_id, active). В ответе только длина токена и превью instance_id, без секретов. Подсказка: «Send a real message via WhatsApp to trigger the webhook». |

---

## Ответы

Результат каждого запроса выводится в блок **«Ответ»** в формате JSON (status, ok, body). Ошибки сети или 401/403 также отображаются там.
