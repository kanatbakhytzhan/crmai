# 📡 API Examples - SaaS Platform

## Базовый URL
```
http://localhost:8000
```

---

## 🔐 АУТЕНТИФИКАЦИЯ

### 1. Регистрация компании

**Request:**
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "manager@construction.kz",
  "password": "securepass123",
  "company_name": "СтройКомпания Алматы"
}
```

**Response (201):**
```json
{
  "id": 1,
  "email": "manager@construction.kz",
  "company_name": "СтройКомпания Алматы",
  "is_active": true,
  "created_at": "2026-01-28T15:30:00"
}
```

**Errors:**
```json
// 400 - Email уже используется
{
  "detail": "Email already registered"
}
```

---

### 2. Логин (получение JWT токена)

**Request:**
```http
POST /api/auth/login
Content-Type: application/x-www-form-urlencoded

username=manager@construction.kz&password=securepass123
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJtYW5hZ2VyQGNvbnN0cnVjdGlvbi5reiIsImV4cCI6MTczMzQ5MjQwMH0.xyz...",
  "token_type": "bearer"
}
```

**Errors:**
```json
// 401 - Неверный email или пароль
{
  "detail": "Incorrect email or password"
}
```

---

### 3. Получение информации о текущем пользователе

**Request:**
```http
GET /api/auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response (200):**
```json
{
  "id": 1,
  "email": "manager@construction.kz",
  "company_name": "СтройКомпания Алматы",
  "is_active": true,
  "created_at": "2026-01-28T15:30:00"
}
```

---

## 💬 ЧАТ С AI (Защищен JWT)

### 4. Отправка текстового сообщения

**Request:**
```http
POST /api/chat
Authorization: Bearer YOUR_TOKEN_HERE
Content-Type: multipart/form-data

user_id=client_telegram_12345
text=Хочу построить дом в Алматы
```

**Response (200):**
```json
{
  "status": "success",
  "user_id": "client_telegram_12345",
  "response": "Здравствуйте! У вас уже есть участок в Алматы?",
  "function_called": null
}
```

---

### 5. Отправка аудио сообщения

**Request:**
```http
POST /api/chat
Authorization: Bearer YOUR_TOKEN_HERE
Content-Type: multipart/form-data

user_id=client_telegram_12345
audio_file=<audio_file.ogg>
```

**Response (200):**
```json
{
  "status": "success",
  "user_id": "client_telegram_12345",
  "response": "Хорошо. Какую площадь дома рассматриваете?",
  "function_called": null
}
```

---

### 6. Полный диалог → Создание заявки

**Сценарий:**
```
Client: "Хочу дом"
Bot: "В каком городе?"
Client: "Алматы"
Bot: "Какую площадь рассматриваете?"
Client: "150 квадратов"
Bot: "Как вас зовут и на какой номер перезвонить?"
Client: "Канат, 87768776637"
```

**Последний Response:**
```json
{
  "status": "success",
  "user_id": "client_telegram_12345",
  "response": "Спасибо, Канат! Наш менеджер свяжется с вами по номеру 87768776637 в ближайшее время.",
  "function_called": "register_lead"
}
```

**Что происходит:**
1. ✅ Создается Lead в БД (owner_id из JWT токена)
2. ✅ Отправляется уведомление в Telegram
3. ✅ Бот завершает диалог

---

## 📋 РАБОТА С ЗАЯВКАМИ

### 7. Получение всех заявок

**Request:**
```http
GET /api/leads
Authorization: Bearer YOUR_TOKEN_HERE
```

**Response (200):**
```json
{
  "leads": [
    {
      "id": 1,
      "owner_id": 1,
      "bot_user_id": 1,
      "name": "Канат",
      "phone": "87768776637",
      "city": "Алматы",
      "object_type": "дом",
      "area": "150 м²",
      "summary": "Строительство дома с нуля, есть участок",
      "language": "ru",
      "status": "new",
      "created_at": "2026-01-28T16:00:00"
    },
    {
      "id": 2,
      "owner_id": 1,
      "bot_user_id": 2,
      "name": "Айгуль",
      "phone": "87051234567",
      "city": "Астана",
      "object_type": "квартира",
      "area": "80 м²",
      "summary": "Ремонт квартиры под ключ",
      "language": "kk",
      "status": "in_progress",
      "created_at": "2026-01-28T17:30:00"
    }
  ],
  "total": 2
}
```

**Важно:**
- Вы видите ТОЛЬКО свои заявки (owner_id из JWT токена)
- Другие компании НЕ видят ваши заявки

---

## 🏢 MULTI-TENANCY В ДЕЙСТВИИ

### Сценарий:

**Компания А (manager@companyA.kz):**
```bash
# Регистрация
POST /api/auth/register
{
  "email": "manager@companyA.kz",
  "password": "pass123",
  "company_name": "Компания А"
}

# Логин → получаем token_A
POST /api/auth/login
username=manager@companyA.kz&password=pass123

# Отправляем сообщение с token_A
POST /api/chat (Authorization: Bearer token_A)
→ Создается Lead с owner_id=1

# Проверяем заявки
GET /api/leads (Authorization: Bearer token_A)
→ Видим 1 заявку (свою)
```

**Компания Б (manager@companyB.kz):**
```bash
# Регистрация
POST /api/auth/register
{
  "email": "manager@companyB.kz",
  "password": "pass123",
  "company_name": "Компания Б"
}

# Логин → получаем token_B
POST /api/auth/login
username=manager@companyB.kz&password=pass123

# Проверяем заявки
GET /api/leads (Authorization: Bearer token_B)
→ Видим 0 заявок (не видим заявки Компании А!)
```

**✅ ИЗОЛЯЦИЯ ДАННЫХ РАБОТАЕТ!**

---

## 🔒 БЕЗОПАСНОСТЬ

### JWT Token Format:
```json
{
  "sub": "user@example.com",  // Email пользователя
  "exp": 1735660800           // Timestamp expiration
}
```

### Token Lifespan:
- По умолчанию: **7 дней** (10080 минут)
- Настраивается в `.env` (ACCESS_TOKEN_EXPIRE_MINUTES)

### Password Security:
- Хэширование: **bcrypt**
- Никогда не храним пароли в открытом виде
- Хэш сохраняется в `users.hashed_password`

---

## 🌐 ПУБЛИЧНЫЕ ЭНДПОИНТЫ (без токена):

```http
GET  /                  # Web интерфейс
GET  /health            # Health check
POST /api/auth/register # Регистрация
POST /api/auth/login    # Логин
GET  /docs              # Swagger UI
GET  /redoc             # ReDoc
```

---

## 🔐 ЗАЩИЩЕННЫЕ ЭНДПОИНТЫ (требуют JWT):

```http
GET  /api/auth/me      # Информация о текущем пользователе
POST /api/chat         # Отправка сообщения боту
GET  /api/leads        # Получение заявок
```

---

## 🧪 cURL ПРИМЕРЫ

### Регистрация:
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@company.kz",
    "password": "test123",
    "company_name": "Тест"
  }'
```

### Логин:
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -d "username=test@company.kz&password=test123"
```

### Chat (с токеном):
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "user_id=client_1" \
  -F "text=Хочу дом"
```

### Получение заявок:
```bash
curl -X GET http://localhost:8000/api/leads \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🎉 ГОТОВО К ИСПОЛЬЗОВАНИЮ!

Платформа полностью функциональна и готова к масштабированию! 🚀
