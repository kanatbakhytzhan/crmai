# 🤖 AI Sales Manager - SaaS Platform

Многопользовательская платформа ИИ-менеджеров по продажам для строительных компаний.

## 🎯 Возможности

- 🤖 **AI Sales Bot** - Автоматическая квалификация лидов через GPT-4o
- 🎤 **Voice Recognition** - Распознавание речи через Whisper API
- 🌐 **Multi-language** - Русский и Казахский
- 🔐 **JWT Auth** - Безопасная авторизация
- 🏢 **Multi-tenant** - Каждая компания видит только свои заявки
- 📱 **Telegram Integration** - Мгновенные уведомления
- 💾 **PostgreSQL** - Готовность к production

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка PostgreSQL

**Docker:**
```bash
docker run --name postgres-sales \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sales_bot \
  -p 5432:5432 \
  -d postgres:15
```

**Или используйте Supabase** (см. MIGRATION_GUIDE.md)

### 3. Настройка .env

Скопируйте и отредактируйте:

```env
OPENAI_API_KEY=your-key
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sales_bot
SECRET_KEY=generate-with-openssl-rand-hex-32
DEV_MODE=TRUE
```

### 4. Запуск

```bash
python main.py
```

Откройте: http://localhost:8000/

---

## 📡 API Documentation

### Authentication

**Регистрация:**
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "manager@company.kz",
  "password": "securepass123",
  "company_name": "Моя Компания"
}
```

**Логин:**
```http
POST /api/auth/login
Content-Type: application/x-www-form-urlencoded

username=manager@company.kz&password=securepass123
```

**Ответ:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer"
}
```

### Chat API (требует токен)

**Отправка сообщения:**
```http
POST /api/chat
Authorization: Bearer YOUR_TOKEN
Content-Type: multipart/form-data

user_id=client_telegram_123
text=Хочу построить дом
```

**Получение заявок:**
```http
GET /api/leads
Authorization: Bearer YOUR_TOKEN
```

---

## 🏢 Multi-tenancy

Каждая компания работает в изолированном пространстве:

- ✅ Свои клиенты (BotUser)
- ✅ Свои заявки (Lead)
- ✅ Своя история сообщений (Message)

**Пример:**

| Компания | Email | Заявок | Клиентов |
|----------|-------|--------|----------|
| Строй А | a@example.com | 150 | 45 |
| Строй Б | b@example.com | 89 | 32 |

Данные **полностью изолированы** на уровне БД.

---

## 🛡️ Безопасность

### JWT Token:
- Алгоритм: HS256
- Срок жизни: 7 дней (настраивается)
- Payload: `{"sub": "user_email", "exp": timestamp}`

### Password Hashing:
- Алгоритм: bcrypt
- Rounds: auto (passlib default)

### API Security:
- Rate limiting (TODO)
- CORS настроен
- HTTPS ready

---

## 🗄️ Database Schema

### Таблицы:

**users** - Владельцы аккаунтов
- id, email, hashed_password, company_name, is_active

**bot_users** - Клиенты бота
- id, owner_id (FK), user_id, name, phone, language

**messages** - История диалогов
- id, bot_user_id (FK), role, content

**leads** - Заявки
- id, owner_id (FK), bot_user_id (FK), name, phone, city, object_type, area, summary, status

---

## 📊 Мониторинг

### Логи:

Все операции логируются в консоль:

```
[*] Novoe soobshchenie ot user_id: client_123
[*] Owner ID: 5 (Строй Компания)
[*] BotUser ID: 12
[*] Otpravka v GPT-4o...
[OK] Polucheno ot GPT
[*] Function call: register_lead
[OK] Lid sozdan s ID: 8 (owner: 5)
[OK] Uvedomlenie v Telegram otpravleno
```

### Health Check:

```http
GET /health
```

Ответ:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "database": "PostgreSQL",
  "auth": "JWT"
}
```

---

## 🧪 Тестирование

### Swagger UI:
http://localhost:8000/docs

### Postman Collection:
Импортируйте OpenAPI схему из Swagger

### Ручное тестирование:

1. Регистрация → Получение токена
2. Отправка сообщений с токеном
3. Проверка изоляции данных (разные токены = разные данные)

---

## 🚀 Deploy

### Vercel / Railway / Render:

1. Создайте PostgreSQL БД (Supabase/Neon/Railway)
2. Настройте переменные окружения
3. Деплой FastAPI приложения
4. Готово!

### Docker:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 📞 Поддержка

Для вопросов и предложений:
- Email: support@example.com
- Документация: См. MIGRATION_GUIDE.md

### �������� ���� ������ (Render / PostgreSQL)

**�������������� ��������**:
��� ������ ������� (main.py startup event) ���������� �������� init_db().
��� ������� ��������� ������� � **������������� ��������� ����������� �������** (��������, 	enants.amocrm_base_domain), ��������� ALTER TABLE IF NOT EXISTS.

**������ ��������**:
���� �� ������������ ���������� �����, ����������� ����� ��������������� �������� (������ Admin):
GET /api/admin/diagnostics/db/schema
�� ������ ������ ����������� �������.

**������**:
���� webhook ������ � UndefinedColumnError, ������ **������������� ������ �� Render** (Deploy / Restart Service). ��� ������ �������� ���������.
