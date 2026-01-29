# 🚀 ПРОЕКТ ГОТОВ К ДЕПЛОЮ НА RAILWAY!

## ✅ ВСЁ НАСТРОЕНО!

---

## 📦 ЧТО БЫЛО СДЕЛАНО:

### 1️⃣ **Procfile (Railway Entry Point)**

**Файл:** `Procfile`

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Что это:**
- Команда для запуска сервера на Railway
- `$PORT` - Railway автоматически подставит свой порт
- `0.0.0.0` - доступ из интернета

---

### 2️⃣ **requirements.txt (Обновлен)**

**Файл:** `requirements.txt`

**Добавлено:**
```diff
+ psycopg2-binary>=2.9.9  # Для Railway PostgreSQL
+ email-validator>=2.0.0   # Для Pydantic
```

**Важно:**
- `psycopg2-binary` - синхронный драйвер для PostgreSQL (нужен для SQLAdmin)
- `asyncpg` - асинхронный драйвер (уже был)
- Все зависимости актуальны

---

### 3️⃣ **.gitignore (Проверен)**

**Файл:** `.gitignore`

**Уже включено:**
- ✅ `venv/` - виртуальное окружение
- ✅ `__pycache__/` - кэш Python
- ✅ `.env` - секретные ключи
- ✅ `*.db`, `*.sqlite` - локальная база
- ✅ `.DS_Store` - MacOS
- ✅ Логи, IDE файлы

**Результат:** Мусор не попадет в Git!

---

### 4️⃣ **Database Switcher (Автоматический)**

**Файл:** `app/core/config.py`

**Логика:**

```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    
    # Railway Database Switcher
    railway_db = os.getenv("DATABASE_URL")
    if railway_db:
        # Railway: postgres:// -> postgresql+asyncpg://
        if railway_db.startswith("postgres://"):
            railway_db = railway_db.replace("postgres://", "postgresql+asyncpg://", 1)
        
        self.database_url = railway_db
        print("[Railway] Using DATABASE_URL from environment")
    else:
        print("[Local] Using SQLite")
```

**Как работает:**

1. **На Railway:**
   - Railway устанавливает переменную `DATABASE_URL`
   - Формат: `postgres://user:pass@host:5432/db`
   - Код автоматически заменяет на: `postgresql+asyncpg://...`
   - Приложение подключается к PostgreSQL ✅

2. **На локальном ПК:**
   - `DATABASE_URL` не задана
   - Используется SQLite: `sqlite+aiosqlite:///./sales_bot.db`
   - Можно тестировать без интернета ✅

---

### 5️⃣ **Sync Engine для SQLAdmin**

**Файл:** `app/database/session.py`

**Обновлена логика:**

```python
sync_database_url = settings.database_url

if "+asyncpg" in sync_database_url:
    # PostgreSQL: postgresql+asyncpg:// -> postgresql+psycopg2://
    sync_database_url = sync_database_url.replace("+asyncpg", "+psycopg2")
elif "+aiosqlite" in sync_database_url:
    # SQLite: sqlite+aiosqlite:// -> sqlite://
    sync_database_url = sync_database_url.replace("+aiosqlite", "")
```

**Зачем:**
- SQLAdmin работает синхронно
- Async драйвер (`asyncpg`) → Sync драйвер (`psycopg2`)
- Админка будет работать и на Railway! ✅

---

## 🛠️ КАК ЗАДЕПЛОИТЬ НА RAILWAY:

### ШАГ 1: Загрузить проект на GitHub

```bash
git init
git add .
git commit -m "Initial commit - Ready for Railway deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

### ШАГ 2: Создать проект на Railway

1. Зайдите на [railway.app](https://railway.app)
2. Нажмите **"New Project"**
3. Выберите **"Deploy from GitHub repo"**
4. Выберите свой репозиторий
5. Railway автоматически:
   - Найдет `Procfile`
   - Установит зависимости из `requirements.txt`
   - Запустит `uvicorn main:app`

---

### ШАГ 3: Добавить PostgreSQL

1. В проекте Railway нажмите **"New"**
2. Выберите **"Database" → "PostgreSQL"**
3. Railway автоматически:
   - Создаст базу данных
   - Установит переменную `DATABASE_URL`
   - Ваш код автоматически подключится! ✅

---

### ШАГ 4: Настроить переменные окружения

В Railway Dashboard → Settings → Variables, добавьте:

```env
OPENAI_API_KEY=sk-proj-...
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_CHAT_ID=1234567890
SECRET_KEY=ваш_секретный_ключ_для_jwt
DEV_MODE=FALSE
```

**Важно:**
- `DATABASE_URL` - Railway установит автоматически! (не трогайте)
- `SECRET_KEY` - сгенерируйте: `openssl rand -hex 32`
- `DEV_MODE=FALSE` - чтобы не удалять базу при рестарте

---

### ШАГ 5: Деплой!

1. Railway автоматически деплоит при `git push`
2. Посмотрите логи: **"View Logs"**
3. Найдите URL: **"Settings" → "Domains" → "Generate Domain"**
4. Откройте: `https://your-app.railway.app/`

**Готово! Ваш бот работает в облаке! 🎉**

---

## 🧪 ПРОВЕРКА ПОСЛЕ ДЕПЛОЯ:

### 1. Главная страница:
```
https://your-app.railway.app/
```
- ✅ Должен открыться чат (WhatsApp UI)

### 2. API Docs:
```
https://your-app.railway.app/docs
```
- ✅ Swagger UI с эндпоинтами

### 3. Админка:
```
https://your-app.railway.app/admin
```
- ✅ Вход: `admin` / `admin123`

### 4. Health Check:
```
https://your-app.railway.app/health
```
- ✅ JSON с информацией о сервере

---

## 📊 СРАВНЕНИЕ: ЛОКАЛЬНО vs RAILWAY

| Параметр | Локальный ПК | Railway |
|----------|--------------|---------|
| **База данных** | SQLite (файл) | PostgreSQL (облако) |
| **URL** | `localhost:8000` | `your-app.railway.app` |
| **DATABASE_URL** | Не задана | Автоматически |
| **Драйвер** | `aiosqlite` | `asyncpg` + `psycopg2` |
| **Секреты** | `.env` файл | Railway Variables |
| **Деплой** | `python main.py` | `git push` |

---

## 🔍 ЛОГИ НА RAILWAY:

**Что вы увидите в логах:**

```
[Railway] Using DATABASE_URL from environment
[*] Zapusk prilozheniya (SaaS versiya)...
[*] Initializaciya PostgreSQL...
[OK] Baza dannyh initializirovana
[*] Telegram bot gotov dlya otpravki uvedomleniy
[OK] Prilozhenie zapushcheno!
[OK] Kompaniya: AI Sales Manager SaaS
[OK] JWT Auth: ENABLED
INFO:     Uvicorn running on http://0.0.0.0:12345 (Press CTRL+C to quit)
```

**Если увидите:**
```
[Local] Using SQLite
```
→ Значит `DATABASE_URL` не установлена. Проверьте PostgreSQL плагин.

---

## 🐛 TROUBLESHOOTING:

### Ошибка: "No module named 'psycopg2'"
**Решение:** Проверьте `requirements.txt`, там должно быть `psycopg2-binary>=2.9.9`

### Ошибка: "connection to server failed"
**Решение:** 
1. Убедитесь, что добавили PostgreSQL в Railway
2. Проверьте переменную `DATABASE_URL` в Settings

### Ошибка: "Invalid JWT token"
**Решение:** Добавьте `SECRET_KEY` в Railway Variables

### Админка не работает:
**Решение:** Проверьте, что `psycopg2-binary` установлен (для синхронного SQLAdmin)

---

## ✅ ЧЕКЛИСТ ПЕРЕД ДЕПЛОЕМ:

- ✅ `Procfile` создан
- ✅ `requirements.txt` обновлен (с `psycopg2-binary`)
- ✅ `.gitignore` настроен (`.env` не загружается)
- ✅ `app/core/config.py` с Database Switcher
- ✅ `app/database/session.py` с Sync Engine для админки
- ✅ Все секреты в `.env` (не в коде!)
- ✅ `DEV_MODE=FALSE` (чтобы не удалять БД)

---

## 🚀 ИТОГОВАЯ КОМАНДА:

```bash
# 1. Коммит изменений
git add .
git commit -m "Add Railway deploy configuration"

# 2. Создать репозиторий на GitHub (если еще нет)
# https://github.com/new

# 3. Загрузить код
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main

# 4. Деплой на Railway:
# - Зайти на railway.app
# - New Project → Deploy from GitHub
# - Добавить PostgreSQL
# - Настроить Variables
# - Готово!
```

---

## 🎉 ГОТОВО!

**Ваш проект полностью готов к деплою на Railway!**

### Что работает:
- ✅ Автоматическое переключение БД (SQLite → PostgreSQL)
- ✅ Синхронный SQLAdmin с правильным драйвером
- ✅ Секреты через Railway Variables
- ✅ `.gitignore` защищает от загрузки мусора
- ✅ `Procfile` правильно запускает сервер

### Следующий шаг:
```bash
git push
```

**И ваш бот будет доступен в интернете! 🌍**

---

## 📝 ДОПОЛНИТЕЛЬНЫЕ ССЫЛКИ:

- Railway Docs: https://docs.railway.app
- PostgreSQL Guide: https://docs.railway.app/databases/postgresql
- Environment Variables: https://docs.railway.app/develop/variables

**ВСЁ ГОТОВО! ДЕПЛОЙТЕ! 🚀**
