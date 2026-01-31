# CORS Debug — Backend Patch and Verification

## Changes in this patch

1. **Request Origin in Render logs** — Every `/api/*` request logs the exact `Origin` header:  
   `[CORS] Request Origin: 'https://buildcrm-pwa.vercel.app' | path=/api/auth/login method=POST`

2. **Final parsed allowed origins at startup** — Log line:  
   `[CORS] Final parsed allowed origins: ['https://buildcrm-pwa.vercel.app']`

3. **Robust CORS_ORIGINS parsing** — `_parse_cors_origins()`: split by comma, strip spaces, ignore empty. Default (when empty/unset) is only **Vercel** (no localhost).

4. **CORSMiddleware before routers** — CORS and Session middleware are added before `app.include_router(...)`; last-added middleware runs first, so CORS runs on every request.

5. **OPTIONS preflight** — `allow_headers=["*"]` covers `Content-Type` (login) and `Authorization` (leads/admin). No extra OPTIONS handlers needed.

6. **Debug endpoint** — `GET /api/debug/cors` returns:
   - `request_origin`: value of `Origin` header or `"(none)"`
   - `allowed_origins`: server-side list
   - `origin_allowed`: boolean  
   Remove or protect this endpoint after fixing CORS.

---

## After redeploy — Render startup log

In **Render → Your Service → Logs**, after deploy you should see something like:

```
[*] Zapusk prilozheniya (SaaS versiya)...
[*] Initializaciya PostgreSQL...
...
[CORS] Final parsed allowed origins: ['https://buildcrm-pwa.vercel.app']
...
[OK] Prilozhenie zapushcheno!
```

If you set `CORS_ORIGINS` in Render (e.g. `https://buildcrm-pwa.vercel.app`), the list will show that. For every API request you will also see:

```
[CORS] Request Origin: 'https://buildcrm-pwa.vercel.app' | path=/api/auth/login method=OPTIONS
[CORS] Request Origin: 'https://buildcrm-pwa.vercel.app' | path=/api/auth/login method=POST
```

If Origin is `(none)` or different, fix the frontend or add that origin to `CORS_ORIGINS`.

---

## Check /api/debug/cors

From browser (from your Vercel site) or curl with Vercel origin:

```bash
curl -i "https://crm-api-5vso.onrender.com/api/debug/cors" \
  -H "Origin: https://buildcrm-pwa.vercel.app"
```

Expected body (with CORS headers in response):

```json
{
  "request_origin": "https://buildcrm-pwa.vercel.app",
  "allowed_origins": ["https://buildcrm-pwa.vercel.app"],
  "origin_allowed": true
}
```

If `origin_allowed` is `false`, the request Origin is not in `allowed_origins` — add it in Render env or fix the frontend origin.

---

## Vercel-side Network screenshot (successful OPTIONS + POST login)

1. Open **https://buildcrm-pwa.vercel.app** in Chrome/Edge.
2. Open **DevTools → Network**.
3. (Optional) Filter by **Fetch/XHR**.
4. Enter credentials and click **Войти** (Login).
5. In the list you should see:
   - **OPTIONS** `https://crm-api-5vso.onrender.com/api/auth/login` — Status **200** or **204**, response headers include `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`.
   - **POST** `https://crm-api-5vso.onrender.com/api/auth/login` — Status **200** (success) or **401** (wrong credentials), again with `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`.
6. If OPTIONS or POST is red (failed) or blocked by CORS, the status may be 0 or (failed); click the request and check **Headers** to see if `Access-Control-Allow-Origin` is missing or wrong.

Take a screenshot of the Network tab showing both OPTIONS and POST with status 200/204 and 200 (or 401), and the Response headers for one of them showing `Access-Control-Allow-Origin: https://buildcrm-pwa.vercel.app`.

---

## Deploy steps

1. Push backend changes, trigger **Render** deploy.
2. In Render logs, confirm: `[CORS] Final parsed allowed origins: ['https://buildcrm-pwa.vercel.app']`.
3. From Vercel, open the app and try login; in Render logs confirm: `[CORS] Request Origin: 'https://buildcrm-pwa.vercel.app'`.
4. Optional: call `GET /api/debug/cors` with `Origin: https://buildcrm-pwa.vercel.app` and confirm `origin_allowed: true`.
5. After CORS is fixed, remove or protect `/api/debug/cors` (e.g. only in dev or behind a secret header).
