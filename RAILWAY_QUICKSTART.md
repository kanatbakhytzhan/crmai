# ⚡ RAILWAY DEPLOY - БЫСТРЫЙ СТАРТ

## 🚀 4 ШАГА ДО ДЕПЛОЯ:

---

### 1️⃣ GIT PUSH

```bash
git init
git add .
git commit -m "Ready for Railway deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

### 2️⃣ RAILWAY - NEW PROJECT

1. Зайдите на **[railway.app](https://railway.app)**
2. Нажмите **"New Project"**
3. Выберите **"Deploy from GitHub repo"**
4. Выберите свой репозиторий
5. Railway автоматически задеплоит! ✅

---

### 3️⃣ ДОБАВИТЬ POSTGRESQL

1. В проекте нажмите **"+ New"**
2. Выберите **"Database" → "PostgreSQL"**
3. Railway автоматически установит `DATABASE_URL` ✅

---

### 4️⃣ НАСТРОИТЬ ПЕРЕМЕННЫЕ

В Railway Dashboard → **Settings → Variables**, добавьте:

```env
OPENAI_API_KEY=sk-proj-...
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_CHAT_ID=1234567890
SECRET_KEY=ваш_секретный_ключ_для_jwt
DEV_MODE=FALSE
```

**Сгенерировать SECRET_KEY:**
```bash
openssl rand -hex 32
```

---

## ✅ ГОТОВО!

Ваш бот работает на:
```
https://your-app.railway.app/
```

**Админка:**
```
https://your-app.railway.app/admin
```
(Логин: `admin` / `admin123`)

---

## 🔍 ПРОВЕРКА:

**В логах Railway должно быть:**
```
[Railway] Using DATABASE_URL from environment
[OK] Prilozhenie zapushcheno!
```

**Если увидите:**
```
[Local] Using SQLite
```
→ Добавьте PostgreSQL в проект!

---

## 📝 ЧТО БЫЛО СДЕЛАНО:

- ✅ **Procfile** - команда запуска
- ✅ **requirements.txt** - с `psycopg2-binary`
- ✅ **.gitignore** - защита от мусора
- ✅ **Database Switcher** - автоматическое переключение БД

**Полная документация:** `RAILWAY_DEPLOY_READY.md`

**ВСЁ ГОТОВО! ДЕПЛОЙТЕ! 🚀**
