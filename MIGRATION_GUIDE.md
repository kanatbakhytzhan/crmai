# 🚀 Migration Guide: MVP → SaaS Platform

## Что изменилось?

### До (MVP):
- ✅ Один пользователь
- ✅ SQLite база данных
- ✅ Без авторизации
- ✅ Все заявки в одной куче

### После (SaaS):
- 🎯 Multi-tenant архитектура
- 🎯 PostgreSQL (Supabase ready)
- 🎯 JWT авторизация
- 🎯 Каждый пользователь видит ТОЛЬКО свои заявки

---

## Новая архитектура

### Модели данных:

```
User (Владелец аккаунта)
  ↓ owner_id
BotUser (Клиент бота) ←→ Message (История диалогов)
  ↓ bot_user_id
Lead (Заявка)
```

### Безопасность:

1. **Регистрация**: POST `/api/auth/register`
   - Email + Password + CompanyName
   - Возвращает данные пользователя

2. **Логин**: POST `/api/auth/login`
   - Email + Password
   - Возвращает JWT токен

3. **Защищенные эндпоинты**:
   - `/api/chat` - требует токен
   - `/api/leads` - требует токен
   - Каждый пользователь видит только свои данные

---

## Установка PostgreSQL

### Вариант 1: Docker (рекомендуется для разработки)

```bash
docker run --name postgres-sales \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sales_bot \
  -p 5432:5432 \
  -d postgres:15
```

### Вариант 2: Supabase (рекомендуется для продакшена)

1. Создайте проект на https://supabase.com
2. Перейдите в SQL Editor
3. Выполните скрипт из `migrations/init_postgres.sql`
4. Скопируйте Connection String из Settings → Database
5. Вставьте в `.env` файл (формат: `postgresql+asyncpg://...`)

---

## Настройка .env

```env
# OpenAI API
OPENAI_API_KEY=your-key

# Telegram
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sales_bot

# Security (ОБЯЗАТЕЛЬНО измените!)
SECRET_KEY=your-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Development mode
DEV_MODE=TRUE  # FALSE для продакшена
```

---

## Запуск

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Убедитесь что PostgreSQL запущен

3. Запустите сервер:
```bash
python main.py
```

4. Откройте Swagger UI: http://localhost:8000/docs

---

## Тестирование API

### 1. Регистрация нового пользователя

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@company.kz",
    "password": "securepass123",
    "company_name": "Строй Компания"
  }'
```

### 2. Логин и получение токена

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=manager@company.kz&password=securepass123"
```

Ответ:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 3. Отправка сообщения в чат (с токеном!)

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -F "user_id=client_123" \
  -F "text=Хочу построить дом"
```

### 4. Получение всех заявок

```bash
curl -X GET http://localhost:8000/api/leads \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## Multi-tenancy в действии

### Сценарий:

**Компания А** (user_id=1):
- Регистрируется: `company_a@example.com`
- Получает токен: `token_A`
- Клиент пишет боту → создается Lead с `owner_id=1`

**Компания Б** (user_id=2):
- Регистрируется: `company_b@example.com`
- Получает токен: `token_B`
- Клиент пишет боту → создается Lead с `owner_id=2`

**Изоляция данных:**
- GET `/api/leads` с `token_A` → видит ТОЛЬКО заявки компании А
- GET `/api/leads` с `token_B` → видит ТОЛЬКО заявки компании Б

---

## Что дальше?

### Для продакшена:

1. Измените `DEV_MODE=FALSE` в `.env`
2. Сгенерируйте SECRET_KEY: `openssl rand -hex 32`
3. Настройте Supabase вместо локального PostgreSQL
4. Добавьте HTTPS (например через Nginx или Cloudflare)
5. Настройте Rate Limiting для защиты API

### Возможные улучшения:

- 🔐 Email верификация при регистрации
- 🔄 Refresh tokens (для обновления access token)
- 👥 Роли и права (admin, manager, viewer)
- 📊 Dashboard для просмотра статистики
- 🔔 Webhook для Telegram кнопок (вместо polling)
- 💳 Billing и подписки (Stripe integration)
