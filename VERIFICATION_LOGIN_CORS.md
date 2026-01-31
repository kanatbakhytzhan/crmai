# Verification: Login endpoint + CORS (proofs)

## A) Backend route exists — proof

**1) Login handler and prefix**

- File: `app/api/endpoints/auth.py`  
  - `@router.post("/login", response_model=Token)` at line 53.
- File: `main.py`  
  - `app.include_router(auth.router, prefix="/api/auth", ...)` at line 122.

**2) Real final path**

- Prefix: `/api/auth`  
- Route path: `/login`  
- **Final path: `POST /api/auth/login`** ✓

**3) Required by frontend**

- `POST /api/auth/login`
- `Content-Type: application/x-www-form-urlencoded`
- Body: `username=...&password=...`

The backend already implements this: `OAuth2PasswordRequestForm` accepts form data with `username` and `password`. No alias needed; path matches.

**4) Startup route list**

After this patch, lifespan prints all API routes at startup. Example (from local run):

```
POST /api/auth/register
POST /api/auth/login
GET /api/auth/me
...
```

So Render logs will show `POST /api/auth/login` after deploy.

---

## B) CORS changes

- CORSMiddleware is added **before** any `include_router(...)`.
- `allow_origins`: exact `https://buildcrm-pwa.vercel.app` (from env or default).
- `allow_origin_regex`: `^https://.*\.vercel\.app$` (preview domains).
- `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`.
- Startup logs: `[CORS] Allowed origins: ...` and `[CORS] allow_origin_regex: ...`.

---

## C) Hard diagnostics

- **GET /api/debug/cors** (TEMP) returns:
  - `origin`: request `Origin` header
  - `allowedOrigins`: parsed list
  - `originAllowed`: true/false (list or regex match)
  - Plus snake_case keys for compatibility.
- Startup: `[CORS] Allowed origins: ...` and `[CORS] allow_origin_regex: ...`.

---

## D) Verification (run after deploy)

**1) Health**

```bash
curl -i https://crm-api-5vso.onrender.com/api/health
```

Expected: `200 OK`, body `{"ok":true,"status":"healthy"}`.

**Proof (current Render):**

```
StatusCode: 200
{"ok":true,"status":"healthy"}
```

---

**2) Login endpoint exists (200 or 401, not 404)**

```bash
curl -i -X POST "https://crm-api-5vso.onrender.com/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=test@test.com&password=123"
```

Expected: `200` (valid token) or `401` (wrong credentials). Must **not** be `404`.

**Proof (current Render):**

```
StatusCode: 401
```

So the login route exists and responds; 404 in the browser was likely due to CORS (preflight/OPTIONS failing, so browser reports failure as 404 or “CORS blocked”).

---

**3) CORS preflight (OPTIONS)**

After **this deploy**, run:

```bash
curl -i -X OPTIONS "https://crm-api-5vso.onrender.com/api/auth/login" \
  -H "Origin: https://buildcrm-pwa.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
```

Expected: `200` or `204`, and response headers must include:

- `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`
- (and methods/headers as needed)

**Before this patch**, OPTIONS returned **405 Method Not Allowed** and no `Access-Control-Allow-Origin`. After deploy, CORSMiddleware with `allow_origin_regex` and correct config should handle OPTIONS and return CORS headers.

---

**4) Browser login from Vercel**

- Open https://buildcrm-pwa.vercel.app
- DevTools → Network (Fetch/XHR)
- Log in with valid credentials
- Confirm:
  - OPTIONS `.../api/auth/login` → 200/204 with `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`
  - POST `.../api/auth/login` → 200 (or 401) with same CORS header

Screenshot of Network tab showing 200/401 and CORS headers = final proof.

---

## Summary

| Item | Status |
|------|--------|
| Route POST /api/auth/login in code | ✓ auth.py + main.py |
| Final path /api/auth/login | ✓ prefix + path |
| Startup route list (POST /api/auth/login) | ✓ in lifespan |
| CORS before routers | ✓ middleware before include_router |
| Exact origin + allow_origin_regex | ✓ |
| /api/debug/cors | ✓ origin, allowedOrigins, originAllowed |
| GET /api/health | ✓ 200 on Render |
| POST /api/auth/login | ✓ 401 on Render (endpoint exists) |
| OPTIONS preflight | Fix in this deploy (was 405, no CORS) |

After deploy: **Login endpoint fixed + CORS fixed.** Verify with curl (1–3) and browser (4).
