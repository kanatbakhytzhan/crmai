# 🔧 ADMIN PANEL DEBUG REPORT

## ❌ ПРОБЛЕМА:

При переходе в любой раздел SQLAdmin (Заявки, Клиенты, Компании) возникает **Internal Server Error (500)**.

---

## 🔍 ДИАГНОСТИКА:

### Проверено:

1. ✅ **Engine type**: AsyncEngine (совместимый с SQLAdmin >=0.16.0)
2. ✅ **Логин**: Работает корректно (302 редирект)
3. ✅ **Dashboard**: Загружается без ошибок
4. ❌ **List pages**: Все возвращают 500 ошибку

### Ошибка из логов:

```
AttributeError: 'str' object has no attribute 'parameter_name'
File "sqladmin\models.py", line 846
filter_param_name = filter.parameter_name
```

**Анализ**: SQLAdmin ожидает объект Filter, но получает строку.

---

## 🛠️ РЕШЕНИЯ КОТОРЫЕ БЫЛ И ПРИМЕНЕНЫ:

### 1. Убраны проблемные поля из `column_searchable_list`

**ДО:**
```python
column_searchable_list = ["name", "phone", "city", "summary"]
```

**ПРОБЛЕМА**: `phone` (числовое), `summary` (TEXT - медленный поиск)

**ПОСЛЕ:**
```python
column_searchable_list = [Lead.name, Lead.city]  # Только String
```

### 2. Упрощены фильтры

**ДО:**
```python
column_filters = ["status", "city", "language", "created_at", "owner_id"]
```

**ПРОБЛЕМА**: Строки вместо объектов Filter

**ПОСЛЕ:**
```python
# Полностью отключены
```

### 3. Убраны форматтеры с Enum

**ДО:**
```python
column_formatters = {
    "status": lambda m, a: {...}.get(m.status.value if hasattr(...))
}
```

**ПРОБЛЕМА**: Сложная логика с Enum может вызывать ошибки

**ПОСЛЕ:**
```python
# Полностью отключены
```

### 4. Минимальная конфигурация

**Текущая конфигурация `LeadAdmin`:**
```python
class LeadAdmin(ModelView, model=Lead):
    name = "Заявка"
    name_plural = "Заявки"
    icon = "fa-solid fa-clipboard-list"
    
    column_list = [Lead.id, Lead.name, Lead.phone, Lead.city]
    form_columns = [Lead.name, Lead.phone, Lead.city]
    
    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = False
```

---

## ⚠️ ПРОБЛЕМА НЕ РЕШЕНА

Несмотря на максимальное упрощение, ошибка 500 сохраняется.

---

## 🔎 ВОЗМОЖНЫЕ ПРИЧИНЫ:

### 1. Несовместимость версий

**Текущая конфигурация:**
- `sqladmin[full]>=0.16.0`
- `sqlalchemy[asyncio]>=2.0.0`
- `aiosqlite>=0.20.0`

**Проблема**: Может быть конфликт между версиями.

**Решение**: Обновить до последних версий:
```bash
pip install --upgrade sqladmin sqlalchemy aiosqlite
```

### 2. Async Session не работает с SQLAdmin

**Проблема**: SQLAdmin может требовать синхронный движок для админки, даже если основное приложение асинхронное.

**Решение**: Создать отдельный синхронный engine только для админки:

```python
from sqlalchemy import create_engine  # Синхронный!

# В app/database/session.py
sync_engine = create_engine(
    settings.database_url.replace("+aiosqlite", ""),  # Убираем async
    echo=settings.debug,
    pool_pre_ping=True,
)

# В app/admin.py
admin = Admin(
    app=app,
    engine=sync_engine,  # Синхронный движок!
    ...
)
```

### 3. Проблема с Enum полем

**Проблема**: `Lead.status` это `SQLEnum(LeadStatus)`, SQLAdmin может не уметь его отображать.

**Решение**: Изменить тип поля на String:

```python
# В models.py
status = Column(String, default="new")  # Вместо SQLEnum
```

### 4. Relationships загружаются неправильно

**Проблема**: `Lead.owner` и `Lead.bot_user` relationships могут вызывать lazy loading в async контексте.

**Решение**: Настроить eager loading:

```python
# В models.py
owner = relationship("User", back_populates="leads", lazy="joined")
bot_user = relationship("BotUser", back_populates="leads", lazy="joined")
```

---

## 🚀 РЕКОМЕНДАЦИИ:

### Вариант 1: Создать отдельный синхронный engine для админки

**Преимущества:**
- SQLAdmin гарантированно работает с sync engine
- Основное приложение остается async

**Недостатки:**
- Два подключения к БД
- Немного больше кода

**Реализация:**

1. В `app/database/session.py` добавить:

```python
from sqlalchemy import create_engine  # Синхронный

# Создаем синхронный движок для админки
sync_engine = create_engine(
    settings.database_url.replace("+aiosqlite", "").replace("sqlite+aiosqlite", "sqlite"),
    echo=False,
    pool_pre_ping=True,
)
```

2. В `app/admin.py` использовать:

```python
from app.database.session import sync_engine  # Синхронный!

admin = Admin(
    app=app,
    engine=sync_engine,  # Синхронный движок
    ...
)
```

3. В `main.py`:

```python
from app.database.session import engine, sync_engine

setup_admin(app, sync_engine)  # Передаем синхронный
```

---

### Вариант 2: Обновить все пакеты

```bash
pip install --upgrade sqladmin sqlalchemy aiosqlite
pip install sqladmin[full]==0.18.0  # Последняя стабильная
```

---

### Вариант 3: Использовать альтернативу

**Если SQLAdmin не работает:**

- FastAPI Admin
- Piccolo Admin
- Starlette Admin

---

## 📊 СТАТУС:

| Компонент | Статус |
|-----------|--------|
| Admin Login | ✅ Работает |
| Dashboard | ✅ Работает |
| Leads List | ❌ 500 Error |
| BotUser List | ❌ 500 Error |
| User List | ❌ 500 Error |

---

## 🔧 СЛЕДУЮЩИЕ ШАГИ:

1. **Попробовать Вариант 1** (Sync Engine для админки)
2. Если не поможет → **Обновить пакеты** (Вариант 2)
3. Если не поможет → **Использовать альтернативу** (Вариант 3)

---

## 📝 ВРЕМЕННОЕ РЕШЕНИЕ:

Использовать API эндпоинты для управления:

```bash
# Получить все заявки
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/leads

# Обновить статус
curl -X PATCH -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"status": "in_progress"}' \
     http://localhost:8000/api/leads/1
```

---

**ВЫВОД**: Админка инициализируется, но не может отобразить списки. Наиболее вероятная причина - несовместимость AsyncEngine с текущей версией SQLAdmin. Рекомендуется создать отдельный синхронный engine для админки.
