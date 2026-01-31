# 🚀 RENDER.COM DEPLOY GUIDE

## ✅ ФАЙЛ `render.yaml` СОЗДАН!

---

## 📦 ЧТО ВНУТРИ:

### 1️⃣ **PostgreSQL Database (Free Tier)**

```yaml
- type: pserv
  name: crm-db
  plan: free
  databaseName: crmdb
  databaseUser: crmuser
```

**Параметры:**
- ✅ Тип: PostgreSQL
- ✅ Имя: `crm-db`
- ✅ План: **Free** (0$)
- ✅ База: `crmdb`
- ✅ Пользователь: `crmuser`
- ✅ Доступ: Открыт для всех IP

---

### 2️⃣ **FastAPI Web Service (Free Tier)**

```yaml
- type: web
  name: crm-api
  runtime: python
  plan: free
  buildCommand: pip install -r requirements.txt
  startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Параметры:**
- ✅ Тип: Web Service
- ✅ Имя: `crm-api`
- ✅ Runtime: Python
- ✅ План: **Free** (0$)
- ✅ Регион: Oregon (бесплатный)
- ✅ Health Check: `/health`

**Build:**
```bash
pip install -r requirements.txt
```

**Start:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

### 3️⃣ **Переменные окружения**

#### Автоматические:
- ✅ `DATABASE_URL` - из `crm-db` (автоматически)
- ✅ `PYTHON_VERSION` - `3.11.0`
- ✅ `SECRET_KEY` - автогенерация
- ✅ `DEV_MODE` - `FALSE`

#### Требуют ручного ввода:
- ⚠️ `OPENAI_API_KEY` - нужно ввести вручную
- ⚠️ `TELEGRAM_BOT_TOKEN` - нужно ввести вручную
- ⚠️ `TELEGRAM_CHAT_ID` - нужно ввести вручную
- ⚠️ `DEFAULT_OWNER_EMAIL` - email пользователя, которому привязываются гостевые лиды с веб-чата
- ⚠️ `CORS_ORIGINS` - разрешённые origins для CRM/админки (через запятую), например: `http://localhost:5173,https://your-pwa.onrender.com`

---

## 🛠️ КАК ЗАДЕПЛОИТЬ:

### ШАГ 1: Загрузить на GitHub

```bash
git add render.yaml
git commit -m "Add Render.com configuration"
git push
```

---

### ШАГ 2: Создать Blueprint на Render

1. Зайдите на **[render.com](https://render.com)**
2. Нажмите **"New +"** → **"Blueprint"**
3. Выберите репозиторий: **`kanatbakhytzhan/crmai`**
4. Render найдет `render.yaml` и покажет:
   ```
   ✓ crm-db (PostgreSQL Database)
   ✓ crm-api (Web Service)
   ```
5. Нажмите **"Apply"**

---

### ШАГ 3: Добавить секретные ключи

После создания сервисов, в дашборде `crm-api`:

1. Перейдите в **Environment**
2. Добавьте:

```env
OPENAI_API_KEY=sk-proj-...
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_CHAT_ID=1234567890
```

3. Нажмите **"Save Changes"**
4. Сервис автоматически перезапустится!

---

### ШАГ 4: Проверка

**Ваш API будет доступен на:**
```
https://crm-api.onrender.com/
```

**Проверьте:**
1. Главная страница (чат):
   ```
   https://crm-api.onrender.com/
   ```

2. API Docs:
   ```
   https://crm-api.onrender.com/docs
   ```

3. Health Check:
   ```
   https://crm-api.onrender.com/health
   ```

4. Админка:
   ```
   https://crm-api.onrender.com/admin
   ```

---

## 📊 СРАВНЕНИЕ: RAILWAY vs RENDER

| Параметр | Railway | Render |
|----------|---------|--------|
| **Free Tier** | 500 часов/мес | Всегда включено |
| **БД** | PostgreSQL (5$) | PostgreSQL (Free) |
| **Деплой** | Git push | Git push |
| **Config** | `Procfile` | `render.yaml` |
| **Sleep** | Нет | После 15 мин без запросов |
| **Пробуждение** | - | ~30 секунд |

**Render Free Tier особенности:**
- ✅ Бесплатно навсегда
- ⚠️ Засыпает после 15 минут без запросов
- ⚠️ Пробуждение: 30 секунд
- ✅ 750 часов работы в месяц
- ✅ PostgreSQL включен

---

## 🔍 ЛОГИ:

**В Render Dashboard → Logs увидите:**

```
[Render] Using DATABASE_URL from environment
[*] Zapusk prilozheniya (SaaS versiya)...
[*] Initializaciya PostgreSQL...
[OK] Baza dannyh initializirovana
[*] Telegram bot gotov dlya otpravki uvedomleniy
[OK] Prilozhenie zapushcheno!
INFO:     Uvicorn running on http://0.0.0.0:10000
```

---

## 🐛 TROUBLESHOOTING:

### Ошибка: "Build failed"
**Решение:** Проверьте `requirements.txt`, убедитесь что все зависимости корректны

### Ошибка: "Health check failed"
**Решение:** 
1. Убедитесь, что эндпоинт `/health` работает
2. Увеличьте Health Check Timeout в настройках

### Ошибка: "Database connection failed"
**Решение:** 
1. Проверьте, что `crm-db` успешно создана
2. Убедитесь, что `DATABASE_URL` установлена автоматически

### Сервис засыпает:
**Это нормально для Free Tier!**
- Первый запрос после сна: ~30 секунд
- Решение: UptimeRobot (ping каждые 14 минут)

---

## ⚡ УЛУЧШЕНИЯ (Опционально):

### 1. Health Check Endpoint

Убедитесь, что в `main.py` есть:

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

### 2. Keep-Alive Service (против засыпания)

Используйте [UptimeRobot](https://uptimerobot.com):
- Создайте HTTP(s) Monitor
- URL: `https://crm-api.onrender.com/health`
- Интервал: 14 минут
- Бесплатно до 50 мониторов!

### 3. Custom Domain

В Render Dashboard → Settings → Custom Domain:
```
crm.yourdomain.com
```

---

## 📝 СТРУКТУРА RENDER.YAML:

```yaml
services:
  # 1. База данных
  - type: pserv                    # PostgreSQL
    name: crm-db
    plan: free
    
  # 2. Веб-сервис
  - type: web
    name: crm-api
    runtime: python
    plan: free
    buildCommand: ...
    startCommand: ...
    envVars:
      - key: DATABASE_URL
        fromDatabase:              # Автолинк к БД
          name: crm-db
          property: connectionString
      - key: SECRET_KEY
        generateValue: true        # Автогенерация
      - key: OPENAI_API_KEY
        sync: false                # Ручной ввод
```

---

## ✅ ЧЕКЛИСТ:

- ✅ `render.yaml` создан
- ✅ PostgreSQL настроен (free)
- ✅ Web Service настроен (free)
- ✅ DATABASE_URL автоматически
- ✅ SECRET_KEY автогенерация
- ✅ Health Check настроен
- ⏳ Нужно добавить вручную:
  - OPENAI_API_KEY
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID

---

## 🎉 ГОТОВО!

**Следующие шаги:**

1. **Загрузить на GitHub:**
   ```bash
   git add render.yaml
   git commit -m "Add Render.com config"
   git push
   ```

2. **Создать Blueprint на Render:**
   - New + → Blueprint
   - Выбрать репозиторий
   - Apply

3. **Добавить секреты:**
   - Environment → Add OPENAI_API_KEY, etc.

4. **Проверить:**
   - `https://crm-api.onrender.com/`

**ВСЁ ГОТОВО К ДЕПЛОЮ! 🚀**

---

## 📚 ПОЛЕЗНЫЕ ССЫЛКИ:

- Render Docs: https://render.com/docs
- Blueprint Spec: https://render.com/docs/blueprint-spec
- PostgreSQL on Render: https://render.com/docs/databases
- Health Checks: https://render.com/docs/health-checks

**ДЕПЛОЙТЕ НА RENDER! БЕСПЛАТНО! 🎉**
