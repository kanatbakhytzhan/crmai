# Admin Users API (BuildCRM PWA)

Эндпоинты для управления пользователями. Доступ только для админа (Bearer token + is_admin или ADMIN_EMAILS).

**Base URL:** `https://crm-api-5vso.onrender.com` (или ваш хост)

**Авторизация:** тот же токен, что и для `/api/leads`: `POST /api/auth/login` → `Authorization: Bearer <token>`.

---

## Эндпоинты

### GET /api/admin/users

Список пользователей (без паролей).

**Ответ 200:**
```json
{
  "users": [
    {
      "id": 1,
      "email": "admin@example.com",
      "company_name": "Company",
      "is_active": true,
      "is_admin": true,
      "created_at": "2025-01-01T12:00:00",
      "updated_at": "2025-01-01T12:00:00"
    }
  ],
  "total": 1
}
```

**Ошибки:** 401 (нет/неверный токен), 403 (не админ).

---

### POST /api/admin/users

Создать пользователя.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "secret123",
  "company_name": "Optional Company"
}
```
`company_name` опционально; если не передан, берётся часть до `@` из email.

**Ответ 201:** объект пользователя (как в списке, без пароля).

**Ошибки:** 401, 403, 409 (email already exists).

---

### PATCH /api/admin/users/{user_id}

Обновить пользователя.

**Body (все поля опциональны):**
```json
{
  "is_active": false,
  "company_name": "New Name",
  "is_admin": false
}
```

**Ответ 200:** обновлённый объект пользователя.

**Ошибки:** 401, 403, 404 (user not found).

---

### POST /api/admin/users/{user_id}/reset-password

Сброс пароля.

**Body:**
```json
{
  "password": "newpassword123"
}
```

**Ответ 200:** `{"ok": true}`

**Ошибки:** 401, 403, 404.

---

## Включение админки на Render

В Environment сервиса `crm-api` добавьте:

```
ADMIN_EMAILS=kana.bahytzhan@gmail.com
```

Пользователь с этим email получает доступ к `/api/admin/*` без поля `is_admin` в БД.

Если таблица `users` уже была создана без колонки `is_admin`, выполните в БД:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
```

Подробнее: `ADMIN_GUIDE.md` (раздел BuildCRM PWA).
