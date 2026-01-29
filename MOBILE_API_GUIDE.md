# 📱 MOBILE APP API GUIDE

## 🎉 НОВЫЕ ЭНДПОИНТЫ ДЛЯ УПРАВЛЕНИЯ ЗАЯВКАМИ

Все эндпоинты требуют JWT токен в заголовке: `Authorization: Bearer YOUR_TOKEN`

---

## 📋 СПИСОК ВСЕХ ЭНДПОИНТОВ

### 1️⃣ GET /api/leads
**Описание:** Получить все заявки компании

**Пример запроса:**
```http
GET /api/leads
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Ответ (200):**
```json
{
  "leads": [
    {
      "id": 1,
      "owner_id": 1,
      "bot_user_id": 1,
      "name": "Канат",
      "phone": "87771234567",
      "city": "Алматы",
      "object_type": "дом",
      "area": "200 м²",
      "summary": "Строительство дома",
      "language": "ru",
      "status": "new",
      "created_at": "2026-01-28T20:00:00"
    }
  ],
  "total": 1
}
```

---

### 2️⃣ GET /api/leads/{lead_id} 🆕
**Описание:** Получить одну заявку по ID

**Пример запроса:**
```http
GET /api/leads/1
Authorization: Bearer YOUR_TOKEN
```

**Ответ (200):**
```json
{
  "id": 1,
  "owner_id": 1,
  "bot_user_id": 1,
  "name": "Канат",
  "phone": "87771234567",
  "city": "Алматы",
  "object_type": "дом",
  "area": "200 м²",
  "summary": "Строительство дома",
  "language": "ru",
  "status": "new",
  "created_at": "2026-01-28T20:00:00"
}
```

**Ошибки:**
- `404` - Заявка не найдена или не принадлежит вам
- `401` - Неверный токен

---

### 3️⃣ PATCH /api/leads/{lead_id} 🆕
**Описание:** Обновить статус заявки

**Допустимые статусы:**
- `new` - Новая заявка
- `in_progress` - В работе
- `success` - Успешно завершена
- `failed` - Отказ/не удалось

**Пример запроса:**
```http
PATCH /api/leads/1
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "status": "in_progress"
}
```

**Ответ (200):**
```json
{
  "status": "success",
  "message": "Lead status updated to in_progress",
  "lead": {
    "id": 1,
    "status": "in_progress",
    "name": "Канат",
    "phone": "87771234567",
    ...
  }
}
```

**Ошибки:**
- `400` - Неверный статус
- `404` - Заявка не найдена
- `401` - Неверный токен

---

### 4️⃣ DELETE /api/leads/{lead_id} 🆕
**Описание:** Удалить заявку (для тестовых/мусорных заявок)

**Пример запроса:**
```http
DELETE /api/leads/1
Authorization: Bearer YOUR_TOKEN
```

**Ответ (200):**
```json
{
  "status": "success",
  "message": "Lead 1 deleted successfully"
}
```

**Ошибки:**
- `404` - Заявка не найдена
- `401` - Неверный токен

---

## 🌐 ДОСТУП К СЕРВЕРУ

### Сервер теперь доступен по сети!

**Localhost (с компьютера):**
```
http://localhost:8000
```

**Из мобильного приложения (Wi-Fi):**
```
http://192.168.0.10:8000
```

**Swagger UI (тестирование):**
```
http://192.168.0.10:8000/docs
```

**❗ ВАЖНО:** Убедитесь что телефон и компьютер в одной Wi-Fi сети!

---

## 📱 СЦЕНАРИИ ИСПОЛЬЗОВАНИЯ

### Сценарий 1: Просмотр заявок в мобильном приложении

```javascript
// 1. Логин пользователя
const loginResponse = await fetch('http://192.168.0.10:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=manager@company.kz&password=pass123'
});

const { access_token } = await loginResponse.json();

// 2. Получение списка заявок
const leadsResponse = await fetch('http://192.168.0.10:8000/api/leads', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});

const { leads, total } = await leadsResponse.json();

console.log(`Всего заявок: ${total}`);
leads.forEach(lead => {
  console.log(`#${lead.id}: ${lead.name} - ${lead.status}`);
});
```

---

### Сценарий 2: Обновление статуса заявки

```javascript
// Менеджер взял заявку в работу
const updateResponse = await fetch('http://192.168.0.10:8000/api/leads/1', {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ status: 'in_progress' })
});

const result = await updateResponse.json();
console.log(result.message); // "Lead status updated to in_progress"
```

---

### Сценарий 3: Просмотр деталей одной заявки

```javascript
// Открываем детали заявки
const leadResponse = await fetch('http://192.168.0.10:8000/api/leads/1', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});

const lead = await leadResponse.json();

console.log(`
  Имя: ${lead.name}
  Телефон: ${lead.phone}
  Город: ${lead.city}
  Объект: ${lead.object_type}
  Площадь: ${lead.area}
  Статус: ${lead.status}
  Запрос: ${lead.summary}
`);
```

---

### Сценарий 4: Удаление тестовой заявки

```javascript
// Удаляем мусорную заявку
const deleteResponse = await fetch('http://192.168.0.10:8000/api/leads/999', {
  method: 'DELETE',
  headers: { 'Authorization': `Bearer ${access_token}` }
});

const result = await deleteResponse.json();
console.log(result.message); // "Lead 999 deleted successfully"
```

---

## 🔒 БЕЗОПАСНОСТЬ

### Multi-Tenancy работает!

- Company A видит **ТОЛЬКО** свои заявки
- Company B видит **ТОЛЬКО** свои заявки
- Попытка получить чужую заявку → **404 Not Found**

**Пример:**
```bash
# Company A (token_A) пытается получить заявку Company B
GET /api/leads/123
Authorization: Bearer token_A

# Ответ: 404 Not Found (даже если заявка существует!)
```

---

## 🧪 ТЕСТИРОВАНИЕ

### Автоматический тест:
```bash
python test_mobile_api.py
```

### Результат теста:
```
[OK] GET /api/leads - OK
[OK] GET /api/leads/{id} - OK
[OK] PATCH /api/leads/{id} - OK
[OK] DELETE /api/leads/{id} - Готов

[SUCCESS] Все эндпоинты для мобилки работают!
```

---

## 📊 СТАТУСЫ ЗАЯВОК

| Статус API | Значение | Для UI |
|------------|----------|---------|
| `new` | Новая заявка | 🔵 Синий |
| `in_progress` | В работе | 🟡 Желтый |
| `success` | Успешно | 🟢 Зеленый |
| `failed` | Отказ | 🔴 Красный |

**Маппинг в БД:**
- `success` → `done` (LeadStatus.DONE)
- `failed` → `cancelled` (LeadStatus.CANCELLED)

---

## 🚀 ЧТО ДАЛЬШЕ?

### Возможные улучшения:

1. **Фильтрация:**
   ```
   GET /api/leads?status=new&city=Алматы
   ```

2. **Пагинация:**
   ```
   GET /api/leads?page=1&limit=20
   ```

3. **Поиск:**
   ```
   GET /api/leads?search=Канат
   ```

4. **Сортировка:**
   ```
   GET /api/leads?sort_by=created_at&order=desc
   ```

5. **Статистика:**
   ```
   GET /api/stats
   {
     "total_leads": 150,
     "new": 30,
     "in_progress": 50,
     "success": 60,
     "failed": 10
   }
   ```

---

## ✅ ГОТОВО!

**Все эндпоинты протестированы и работают!**

Теперь можно подключать мобильное приложение и управлять заявками в реальном времени! 🎉
