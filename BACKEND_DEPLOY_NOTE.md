# Backend deploy note — /api/auth/login + CORS

## What changed

### 1) Login endpoint

- **Original login:** `app/api/endpoints/auth.py` — `@router.post("/login")` with `OAuth2PasswordRequestForm`; router is included in `main.py` as `app.include_router(auth.router, prefix="/api/auth")`, so the path is **POST /api/auth/login**. Response: `{"access_token": "...", "token_type": "bearer"}`.
- **Alias added:** In `main.py`, an explicit **POST /api/auth/login** handler is registered **before** the auth router. It calls the same `auth.login(form_data, db)` so logic is not duplicated. This guarantees the frontend contract is served even if router registration order or middleware interfered.
- **Contract:** POST /api/auth/login, `Content-Type: application/x-www-form-urlencoded`, body `username=...&password=...`, response JSON with `access_token` and `token_type="bearer"`. Backwards-compatible; existing auth endpoints unchanged.

### 2) CORS

- **CORSMiddleware** is added **before** any routers (middleware block runs before `include_router`).
- **Allowed origins (explicit list, no `*`):**
  - `https://buildcrm-pwa.vercel.app`
  - `http://localhost:5173` (dev)
  - Plus `allow_origin_regex`: `^https://.*\.vercel\.app$` (preview deployments).
- **Settings:** `allow_methods=["*"]`, `allow_headers=["*"]`, `expose_headers=["*"]`, `allow_credentials=True`.

### 3) Health

- **GET /api/health** returns `{"ok": true, "status": "healthy"}` without auth. Confirmed in `main.py`.

---

## Verification commands (after deploy or locally)

Replace `<BASE>` with `http://localhost:8000` (local) or `https://crm-api-5vso.onrender.com` (Render).

**a) Health**

```bash
curl -i https://crm-api-5vso.onrender.com/api/health
```

Expected: **200**, body includes `"ok":true`.

**b) Login (must NOT be 404)**

```bash
curl -i -X POST "https://crm-api-5vso.onrender.com/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=x&password=y"
```

Expected: **200** (valid token) or **401** (invalid credentials). Must **not** be **404**.

---

## Git & Render

- Commit: `fix: add /api/auth/login alias + vercel cors`
- Push to `main`. Render auto-deploy uses `main`; `render.yaml` is correct for the web service.
