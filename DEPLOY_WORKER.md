# Followup Worker Deployment Guide

## Overview

The followup worker is a standalone background process that sends automated followup messages to leads who haven't replied. It runs independently from the main web application.

## How It Works

- **Check interval**: 60 seconds
- **Database**: Uses same DATABASE_URL as main app
- **Health monitoring**: Updates health tick every 60s, accessible via `GET /api/worker/health`
- **Error handling**: Exponential backoff on database errors (max 5 consecutive errors before backoff)
- **Retry logic**: Survives temporary database/network issues

## Deployment on Render

### Step 1: Create Background Worker

1. Go to Render Dashboard → your service
2. Click "New" → "Background Worker"
3. Or add to existing `render.yaml`:

```yaml
services:
  # Main web service
  - type: web
    name: crmai-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    
  # Followup Worker
  - type: background
    name: crmai-followup-worker
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.workers.followup_worker
    envVars:
      - key: DATABASE_URL
        sync: false  # Auto-synced from main service
```

### Step 2: Manual Setup (Alternative)

If not using `render.yaml`:

1. **In Render Dashboard**:
   - Click "New" → "Background Worker"
   - Select same repository as your web service
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m app.workers.followup_worker`

2. **Environment Variables**:
   - DATABASE_URL (copy from web service)
   - Any other vars from main app (settings, etc.)

### Step 3: Verify Deployment

After deployment, check logs:

```
[FOLLOWUP_WORKER] Starting as standalone process
[FOLLOWUP_WORKER] Python: 3.11.x
[FOLLOWUP_WORKER] DATABASE_URL: SET
[FOLLOWUP_WORKER] Starting followup worker (checks every 60s)
```

### Step 4: Health Check

Call the health endpoint from your web service:

```bash
curl https://your-app.onrender.com/api/worker/health
```

Expected response:

```json
{
  "ok": true,
  "last_tick": "2026-02-09T01:35:00.000Z",
  "status": "running",
  "checked_at": "2026-02-09T01:35:30.000Z"
}
```

**Status meanings**:
- `running` - Worker checked for followups in last 5 minutes ✅
- `stale` - Last tick > 5 minutes ago ⚠️ (worker may be down)
- `unknown` - Worker never started ❌

## Local Development

```bash
# Set DATABASE_URL in .env or export
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/crm"

# Run worker
python -m app.workers.followup_worker
```

Logs will show:
```
INFO:app.workers.followup_worker:[FOLLOWUP_WORKER] Starting...
INFO:app.workers.followup_worker:[FOLLOWUP WORKER] No pending followups at this time
```

## Troubleshooting

### Worker not starting

**Check logs** for error:
- `DATABASE_URL: NOT SET` → Add environment variable
- `ImportError` → Run `pip install -r requirements.txt`
- `Connection refused` → Check DATABASE_URL format

### Worker shows "stale"

**Possible causes**:
1. Worker crashed - check Render logs
2. Database connection lost - check DB status
3. Worker restarting frequently - check error logs

**Fix**:
- Restart worker from Render dashboard
- Check database connection string
- Review error logs for exceptions

### Followups not sending

**Debug checklist**:
1. Check `lead_followups` table: `SELECT * FROM lead_followups WHERE status='pending';`
2. Verify `scheduled_at <= NOW()`
3. Check worker logs for processing messages
4. Ensure `tenant.followup_enabled = TRUE`
5. Verify ChatFlow credentials in `whatsapp_accounts`

## Monitoring

### Health Endpoint

Monitor worker status programmatically:

```python
import requests

resp = requests.get("https://your-app/api/worker/health")
data = resp.json()

if data["status"] != "running":
    alert("Followup worker is down!")
```

### Render Metrics

- Go to Render Dashboard → Background Worker
- View CPU/Memory usage
- Check restart count (should be low)

## Stopping the Worker

**Temporary**:
- Render Dashboard → Worker → Manual Deploy → Stop

**Permanent**:
- Delete background worker service
- Or set `startCommand: echo "disabled"` in render.yaml

## Production Checklist

- [ ] Worker deployed as Background Worker on Render
- [ ] DATABASE_URL environment variable set
- [ ] Health endpoint returns `"status": "running"`
- [ ] Test followup sends correctly (create test lead, wait 5 min)
- [ ] Monitor worker logs for 24 hours
- [ ] Set up alerting on health endpoint (optional)

## Further Improvements (Future)

- Redis-based health state (survives worker restarts)
- Distributed locking (multiple worker instances)
- Prometheus metrics export
- Dead letter queue for failed messages
