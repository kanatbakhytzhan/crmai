# AI CRM Manager - Migration Guide

## Database Migration: 001_ai_crm_manager.sql

### What This Migration Does

Adds AI CRM Manager features to the database:
- **Lead table**: 6 new columns (category, lead_score, handoff_mode, extracted_fields, last_inbound_at, last_outbound_at)
- **Tenant table**: 4 new columns (followup settings)
- **New tables**: `lead_followups` (auto-followup tracking), `tenant_category_stage_mappings` (AmoCRM sync)

### How to Apply on Render Postgres

**Option 1: Via Render Dashboard (Recommended)**

1. Go to your Render Dashboard → Database
2. Click "Connect" → Copy connection string
3. Use psql locally:
   ```bash
   psql "<connection_string>" -f migrations/001_ai_crm_manager.sql
   ```

**Option 2: Via Render Shell**

1. Go to your Web Service → Shell tab
2. Run:
   ```bash
   cd /opt/render/project/src
   psql $DATABASE_URL -f migrations/001_ai_crm_manager.sql
   ```

**Option 3: Using pgAdmin or DBeaver**

1. Connect to Render Postgres using external connection URL
2. Open SQL editor
3. Paste contents of `001_ai_crm_manager.sql`
4. Execute

### Idempotency & Safety

✅ **Safe to run multiple times** - uses `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`
✅ **No data loss** - only adds columns/tables, doesn't drop anything
✅ **Default values** - sets default followup templates for existing tenants

### Verification After Migration

Run these queries to confirm success:

```sql
-- Check Lead columns
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'leads' 
AND column_name IN ('category', 'lead_score', 'handoff_mode', 'extracted_fields');

-- Check new tables
SELECT table_name FROM information_schema.tables 
WHERE table_name IN ('lead_followups', 'tenant_category_stage_mappings');

-- Check indexes
SELECT indexname FROM pg_indexes 
WHERE tablename = 'lead_followups';
```

Expected output: 4 columns for leads, 2 new tables, 5+ indexes.

### Rollback (If Needed)

**⚠️ WARNING: This will DELETE all followup data!**

Uncomment and run the rollback script at the end of `001_ai_crm_manager.sql` (lines 165-182).

### Post-Migration Steps

1. **Restart web service** (Render auto-restarts on deploy)
2. **Start followup worker**:
   ```bash
   pm2 start "python -m app.workers.followup_worker" --name followup-worker
   ```
3. **Configure category mappings** (optional):
   ```sql
   INSERT INTO tenant_category_stage_mappings (tenant_id, category, stage_key)
   VALUES (1, 'wants_call', 'CALL_1'), (1, 'full_data', 'IN_WORK');
   ```

### Troubleshooting

**Error: "relation does not exist"**
- Check that you're connected to the correct database
- Verify `leads` and `tenants` tables exist

**Error: "permission denied"**
- Use database owner credentials (from Render dashboard)

**Error: "column already exists"**
- Safe to ignore - migration is idempotent

### Need Help?

Check verification queries in the migration file (lines 132-159) or contact support.
