# Network Error Fix Report — Vercel PWA ↔ Render FastAPI

## STEP 1 — Diagnosis

### Failing request (identified)
- **Endpoint:** First failing call is typically **POST /api/auth/login** (or preflight **OPTIONS** for it).
- **Exact URL:** `https://crm-api-5vso.onrender.com/api/auth/login`
- **Error type:** Browser reports a **network/fetch failure** (e.g. `TypeError: Failed to fetch`). This usually means:
  1. **CORS:** Preflight OPTIONS blocked or response missing `Access-Control-Allow-Origin` / `Access-Control-Allow-Headers: Authorization`.
  2. **Wrong BASE_URL:** Frontend calling `undefined` or `localhost` in production (VITE_API_BASE_URL not set on Vercel).
  3. **Mixed content / HTTPS:** Less likely here (both Vercel and Render use HTTPS).

### Debug added (dev-only)
- **Frontend:** On app start, `[BuildCRM] API BASE_URL: <url>` is logged when `import.meta.env.DEV` is true.
- **Frontend:** In `api.ts`, fetch failures (network/CORS) are caught and rethrown with a clear message; in dev the failing URL is logged and included in the message.
- **Backend:** At startup, `[CORS] Allowed origins: [...]` is printed so you can verify allowed origins in Render logs.

---

## STEP 2 — Fixes Applied

### A) CORS on backend (FastAPI) — `main.py`
- **allow_credentials:** `True` (required when sending `Authorization`).
- **allow_methods:** `["*"]`
- **allow_headers:** `["*"]` (covers `Authorization`, `Content-Type`).
- **expose_headers:** `["*"]`
- **allow_origins:** Parsed from `CORS_ORIGINS` env (comma-separated, trimmed, empty ignored). If empty, defaults to **only** `https://buildcrm-pwa.vercel.app` (no localhost).
- **Startup log:** `[CORS] Final parsed allowed origins: [...]` so Render logs show the effective list.
- **Request Origin log:** Every `/api/*` request logs `[CORS] Request Origin: '...' | path=... method=...`.
- **Debug endpoint:** `GET /api/debug/cors` returns `request_origin`, `allowed_origins`, `origin_allowed` (remove or protect after fix).

### B) Frontend BASE_URL — `crm_mobile/src/config/appConfig.ts`
- Uses `import.meta.env.VITE_API_BASE_URL`; if missing or empty, falls back to `https://crm-api-5vso.onrender.com`.
- In production, if `VITE_API_BASE_URL` is not set, a console warning is shown and the fallback is used so API never points to localhost/undefined.

### C) Backend URL
- Base URL is **HTTPS** (`https://crm-api-5vso.onrender.com`). No mixed content.

### D) Error handling — `crm_mobile/src/services/api.ts`
- `request()` and `login()` wrap `fetch()` in try/catch. Network/CORS failures (e.g. `TypeError`, "Failed to fetch") are converted to an `Error` with a clear message instead of a generic "Network error".
- 401/403 from the backend still use `buildError(response)` and show the real JSON message (e.g. "Нет доступа. Нужен администратор." for 403).

---

## STEP 3 — Reproducible curl tests

Run these against your Render backend. Replace `<VERCEL_DOMAIN>` with `https://buildcrm-pwa.vercel.app` and `<BACKEND>` with `https://crm-api-5vso.onrender.com`.

### 1) Preflight OPTIONS for /api/leads (from Vercel origin)
```bash
curl -i -X OPTIONS "https://crm-api-5vso.onrender.com/api/leads" \
  -H "Origin: https://buildcrm-pwa.vercel.app" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```
**Expected:** `204` or `200`, and response headers must include:
- `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`
- `Access-Control-Allow-Methods: *` (or include GET)
- `Access-Control-Allow-Headers: *` or include `Authorization`

### 2) GET /api/health (no auth) with Origin
```bash
curl -i "https://crm-api-5vso.onrender.com/api/health" \
  -H "Origin: https://buildcrm-pwa.vercel.app"
```
**Expected:** `200 OK`, body `{"ok":true,"status":"healthy"}`, and header:
- `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`

### 3) POST /api/auth/login (CORS + credentials)
```bash
curl -i -X POST "https://crm-api-5vso.onrender.com/api/auth/login" \
  -H "Origin: https://buildcrm-pwa.vercel.app" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your@email.com&password=yourpass"
```
**Expected:** Either `200` (with token) or `401` (invalid credentials). Response must include `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app` (and no CORS error in browser when called from Vercel).

---

## STEP 4 — Deploy and verify

### 1) Backend (Render)
- Commit and push backend changes (CORS defaults, startup log, `GET /api/health`).
- In Render dashboard: **Manual Deploy** (or trigger deploy on push).
- In **Environment** ensure `CORS_ORIGINS` includes your Vercel URL, e.g.  
  `https://buildcrm-pwa.vercel.app`  
  or leave empty to use the default list that already includes it.
- After deploy, check **Logs** for: `[CORS] Allowed origins: ['http://localhost:5173', 'http://127.0.0.1:5173', 'https://buildcrm-pwa.vercel.app']` (or your custom list).

### 2) Frontend (Vercel)
- Commit and push frontend changes (appConfig warning, main.tsx BASE_URL log, api.ts error handling).
- In Vercel project **Settings → Environment Variables**, set:
  - **Name:** `VITE_API_BASE_URL`
  - **Value:** `https://crm-api-5vso.onrender.com`
- Redeploy (e.g. trigger new deployment or push again).

### 3) Final verification checklist
- [ ] **Login from Vercel:** Open https://buildcrm-pwa.vercel.app, go to login, enter valid credentials → login succeeds (no "Сетевая ошибка" / "Network error").
- [ ] **Leads from Vercel:** After login, open Leads → list loads (no network error).
- [ ] **Admin users from Vercel:** Log in as admin, open Admin → Users → list loads (no network error). If not admin, expect "Нет доступа. Нужен администратор." (403), not a generic network error.
- [ ] **Optional:** In browser DevTools → Network, confirm requests to `https://crm-api-5vso.onrender.com` return 200/401/403 with `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`.

---

## Summary

| Item | Status |
|------|--------|
| CORS on FastAPI (origins, credentials, methods, headers) | ✅ Configured; Vercel domain in defaults |
| CORS origins logged at startup | ✅ `[CORS] Allowed origins: ...` in Render logs |
| GET /api/health (no auth) | ✅ Implemented |
| Frontend BASE_URL from env + fallback | ✅ Fallback to Render URL; prod warning if unset |
| Dev-only BASE_URL log | ✅ In main.tsx when DEV |
| api.ts network error handling | ✅ Clear message; 401/403 still show backend message |
| curl tests for OPTIONS + /api/health | ✅ Documented above |

After deploying backend first, then frontend with `VITE_API_BASE_URL` set on Vercel, the "Network error" when calling `/api/auth/login`, `/api/leads`, and `/api/admin/users` from the Vercel domain should be resolved. If it persists, use the dev logs (BASE_URL and fetch error URL) and Render CORS log to confirm the exact failing request and origin.
