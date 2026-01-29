# ⚡ Quick Start Guide - SaaS Version

## 📋 Предварительные требования

- Python 3.10+
- Docker (для PostgreSQL) или Supabase аккаунт
- OpenAI API Key
- Telegram Bot Token

---

## 🏃 Запуск за 5 минут

### 1. Клонируйте и установите зависимости

```bash
cd bot_test
pip install -r requirements.txt
```

### 2. Запустите PostgreSQL

**Через Docker:**
```bash
docker-compose up -d
```

**Или через Docker напрямую:**
```bash
docker run --name postgres-sales \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sales_bot \
  -p 5432:5432 \
  -d postgres:15
```

**Проверка:**
```bash
docker ps  # Должен быть запущен postgres
```

### 3. Настройте .env файл

```env
# OpenAI
OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE

# Telegram
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID

# PostgreSQL (локальный Docker)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sales_bot

# JWT Security
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Dev Mode (TRUE - очистка БД при перезапуске)
DEV_MODE=TRUE
```

### 4. Запустите сервер

```bash
python main.py
```

Вы увидите:
```
[*] Zapusk prilozheniya (SaaS versiya)...
[DEV] Rezim razrabotki - ochistka bazy dannyh...
[*] Initializaciya PostgreSQL...
[OK] Prilozhenie zapushcheno!
[OK] JWT Auth: ENABLED

INFO: Uvicorn running on http://0.0.0.0:8000
```

### 5. Откройте Swagger UI

http://localhost:8000/docs

---

## 🧪 Тестирование

### Через Swagger UI:

1. **Регистрация:**
   - Откройте `POST /api/auth/register`
   - Нажмите "Try it out"
   - Заполните:
     ```json
     {
       "email": "test@company.kz",
       "password": "test123",
       "company_name": "Тест Компания"
     }
     ```
   - Нажмите "Execute"

2. **Логин:**
   - Откройте `POST /api/auth/login`
   - Заполните:
     - username: `test@company.kz`
     - password: `test123`
   - Скопируйте `access_token` из ответа

3. **Авторизация в Swagger:**
   - Нажмите кнопку "Authorize" вверху справа
   - Вставьте токен в поле "Value"
   - Нажмите "Authorize"

4. **Отправка сообщения:**
   - Откройте `POST /api/chat`
   - Заполните:
     - user_id: `telegram_123`
     - text: `Хочу построить дом`
   - Нажмите "Execute"

5. **Просмотр заявок:**
   - Откройте `GET /api/leads`
   - Нажмите "Execute"
   - Увидите свои заявки

### Через cURL:

```bash
# 1. Регистрация
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@company.kz",
    "password": "test123",
    "company_name": "Тест"
  }'

# 2. Логин
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -d "username=test@company.kz&password=test123" \
  | jq -r .access_token)

# 3. Отправка сообщения
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -F "user_id=client_1" \
  -F "text=Хочу дом"

# 4. Получение заявок
curl -X GET http://localhost:8000/api/leads \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🌐 Web интерфейс

**ВАЖНО:** Сейчас web интерфейс НЕ поддерживает JWT авторизацию!

Для работы через браузер:
1. Откройте http://localhost:8000/
2. Пока работает БЕЗ токена (TODO: добавить login форму)

**Рекомендуется использовать Swagger UI или API напрямую**

---

## 🔐 Безопасность

### JWT Токен:

После логина вы получаете токен:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Используйте его в заголовке:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Multi-tenancy:

Каждый пользователь видит ТОЛЬКО свои данные:

```
User A (token_A) → видит заявки с owner_id=A
User B (token_B) → видит заявки с owner_id=B
```

---

## 📊 Структура данных

### User (Владелец аккаунта):
- Email, Password, Company Name
- Может иметь множество клиентов и заявок

### BotUser (Клиент бота):
- Telegram ID (или другой мессенджер)
- Привязан к владельцу аккаунта
- История диалогов

### Lead (Заявка):
- Имя, телефон, город, объект, площадь
- Привязана к владельцу и клиенту
- Статус: NEW, IN_PROGRESS, DONE, CANCELLED

---

## 🐛 Troubleshooting

### PostgreSQL не запускается:
```bash
# Проверьте что порт 5432 свободен
docker ps -a
docker logs postgres-sales
```

### Ошибка подключения к БД:
- Проверьте DATABASE_URL в .env
- Убедитесь что PostgreSQL запущен
- Проверьте логи сервера

### JWT токен не работает:
- Проверьте что SECRET_KEY настроен
- Убедитесь что токен передается в заголовке
- Токен истек? Залогиньтесь заново

---

## 📚 Документация

- **MIGRATION_GUIDE.md** - Подробное руководство по миграции
- **ARCHITECTURE.md** - Описание архитектуры
- **Swagger UI** - http://localhost:8000/docs
- **ReDoc** - http://localhost:8000/redoc

---

## 🎉 Готово!

Теперь у вас работает **полноценная SaaS платформа** с:
- ✅ Multi-tenancy
- ✅ JWT авторизацией
- ✅ PostgreSQL
- ✅ AI Sales Bot
- ✅ Telegram уведомлениями

**Следующие шаги:**
1. Протестируйте API через Swagger
2. Создайте несколько аккаунтов
3. Проверьте изоляцию данных
4. Настройте production окружение (см. MIGRATION_GUIDE.md)
