# 🏗️ Архитектура SaaS платформы

## Структура проекта

```
bot_test/
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                 # Зависимости (get_db, get_current_user)
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       ├── auth.py             # Регистрация + Логин
│   │       └── chat.py             # AI чат (защищен JWT)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Настройки (Pydantic Settings)
│   │   └── security.py             # JWT + Password Hashing
│   ├── database/
│   │   ├── __init__.py
│   │   ├── session.py              # Async Engine (PostgreSQL)
│   │   ├── models.py               # SQLAlchemy модели
│   │   └── crud.py                 # CRUD операции (async)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py                 # User схемы
│   │   ├── auth.py                 # Token схемы
│   │   └── lead.py                 # Lead схемы
│   ├── services/
│   │   ├── __init__.py
│   │   ├── openai_service.py       # OpenAI API (Whisper + GPT-4o)
│   │   └── telegram_service.py     # Telegram уведомления
│   └── static/
│       └── index.html              # Web интерфейс чата
├── migrations/
│   └── init_postgres.sql           # SQL скрипт для создания таблиц
├── main.py                         # Точка входа
├── requirements.txt                # Зависимости
├── .env                            # Переменные окружения
├── MIGRATION_GUIDE.md              # Руководство по миграции
└── ARCHITECTURE.md                 # Этот файл
```

---

## Слои приложения

### 1. API Layer (`app/api/`)

**Endpoints:**
- `auth.py` - Публичные (регистрация, логин)
- `chat.py` - Защищенные JWT (чат с AI, получение заявок)

**Dependencies:**
- `get_db()` - Асинхронная сессия БД
- `get_current_user()` - JWT авторизация

### 2. Business Logic Layer (`app/services/`)

**OpenAI Service:**
- Whisper для распознавания речи
- GPT-4o для диалога и квалификации лидов
- Function Calling для автоматического создания заявок

**Telegram Service:**
- Отправка уведомлений админу
- Форматирование сообщений с emoji

### 3. Data Access Layer (`app/database/`)

**Models (SQLAlchemy):**
- `User` - Владельцы аккаунтов (компании)
- `BotUser` - Клиенты бота (конечные пользователи)
- `Message` - История диалогов
- `Lead` - Заявки (лиды)

**CRUD (Async):**
- Все операции с БД асинхронные
- Multi-tenancy через `owner_id`

### 4. Security Layer (`app/core/security.py`)

- Password Hashing (bcrypt)
- JWT Token generation/validation
- Access token lifespan: 7 дней

---

## Поток данных

### Регистрация и авторизация:

```
1. POST /api/auth/register
   → Проверка email
   → Хэширование пароля
   → Создание User
   → Возврат UserResponse

2. POST /api/auth/login
   → Проверка email + password
   → Генерация JWT токена
   → Возврат Token
```

### Обработка сообщения клиента:

```
1. POST /api/chat
   → Проверка JWT токена
   → Извлечение current_user (owner_id)
   
2. Получение/создание BotUser
   → Привязка к owner_id
   
3. Обработка аудио (если есть)
   → Whisper API
   → Transcription
   
4. Сохранение сообщения
   → Message (role=user)
   
5. Получение истории
   → Последние 20 сообщений
   
6. OpenAI GPT-4o
   → Диалог + Function Calling
   
7. Если вызвана register_lead:
   → Проверка дублей (5 минут)
   → Создание Lead (owner_id из токена!)
   → Telegram уведомление
   
8. Сохранение ответа
   → Message (role=assistant)
   
9. Возврат ответа клиенту
```

---

## Multi-tenancy

### Принцип разделения:

**Каждая таблица с данными пользователя содержит `owner_id`:**
- `bot_users.owner_id` → users.id
- `leads.owner_id` → users.id

**Все SELECT запросы фильтруются по `owner_id`:**
```python
# Пример в CRUD
async def get_user_leads(db: AsyncSession, owner_id: int):
    result = await db.execute(
        select(Lead).where(Lead.owner_id == owner_id)
    )
    return result.scalars().all()
```

**JWT токен содержит email:**
- Декодируем токен → получаем email
- Ищем User по email → получаем owner_id
- Используем owner_id во всех запросах

### Безопасность:

- ✅ Пользователь А НИКОГДА не увидит данные Пользователя Б
- ✅ Все запросы фильтруются на уровне БД
- ✅ JWT токен подписан SECRET_KEY (нельзя подделать)

---

## База данных (PostgreSQL)

### Индексы:

```sql
-- Для быстрого поиска
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_bot_users_owner_id ON bot_users(owner_id);
CREATE INDEX idx_leads_owner_id ON leads(owner_id);
CREATE INDEX idx_leads_status ON leads(status);
```

### Relationships:

```python
# User → BotUser (one-to-many)
user.bot_users

# User → Lead (one-to-many)
user.leads

# BotUser → Message (one-to-many)
bot_user.messages

# BotUser → Lead (one-to-many)
bot_user.leads
```

---

## API Endpoints

### Public (без токена):
- `POST /api/auth/register` - Регистрация
- `POST /api/auth/login` - Логин
- `GET /` - Web интерфейс
- `GET /health` - Health check

### Protected (требуют JWT):
- `POST /api/chat` - Отправка сообщения
- `GET /api/leads` - Получение заявок
- `GET /api/auth/me` - Информация о текущем пользователе

---

## Переменные окружения

```env
# OpenAI
OPENAI_API_KEY=sk-...

# Telegram
TELEGRAM_BOT_TOKEN=123:ABC...
TELEGRAM_CHAT_ID=123456

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db

# JWT Security
SECRET_KEY=random-32-byte-hex-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Dev Mode
DEV_MODE=TRUE  # FALSE для продакшена
```

---

## Тестирование

### 1. Swagger UI:
http://localhost:8000/docs

### 2. Сценарий:

```
1. Регистрация компании
   → POST /api/auth/register

2. Логин
   → POST /api/auth/login
   → Получаем access_token

3. Отправка сообщения (с токеном!)
   → POST /api/chat
   → Headers: Authorization: Bearer <token>

4. Получение заявок
   → GET /api/leads
   → Видим ТОЛЬКО свои заявки
```

---

## Масштабирование

### Горизонтальное:
- PostgreSQL поддерживает множество подключений
- FastAPI может работать с несколькими worker'ами
- Используйте Gunicorn + Uvicorn для production

### Вертикальное:
- Connection pooling (настроено в `session.py`)
- Индексы в БД для быстрых запросов
- Кэширование частых запросов (Redis)

---

## Roadmap для production

1. ✅ Multi-tenancy (готово)
2. ✅ JWT Auth (готово)
3. ✅ PostgreSQL (готово)
4. ⏳ Email верификация
5. ⏳ Refresh tokens
6. ⏳ Rate limiting
7. ⏳ Monitoring (Sentry, Prometheus)
8. ⏳ CI/CD (GitHub Actions)
9. ⏳ Billing (Stripe)
10. ⏳ Admin dashboard
