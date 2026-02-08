-- Owner-Managed Pipelines Database Migration
-- Component 1: Add tenant_stages table + extend leads/tenants for stage management
-- Date: 2026-02-09
-- IDEMPOTENT: Safe to run multiple times

-- ============================================================
-- PART 1: Create tenant_stages table (owner-managed Kanban columns)
-- ============================================================

CREATE TABLE IF NOT EXISTS tenant_stages (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key VARCHAR(64) NOT NULL,
    title_ru VARCHAR(255) NOT NULL,
    title_kz VARCHAR(255) NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    color VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, key)
);

CREATE INDEX IF NOT EXISTS idx_tenant_stages_tenant ON tenant_stages(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_tenant_stages_order ON tenant_stages(tenant_id, order_index) WHERE is_active = TRUE;

COMMENT ON TABLE tenant_stages IS 'Owner-managed pipeline stages (Kanban columns) per tenant';
COMMENT ON COLUMN tenant_stages.key IS 'Stage identifier: no_reply, in_work, wants_call, partial_data, full_data, measurement_scheduled, success, lost';
COMMENT ON COLUMN tenant_stages.title_ru IS 'Russian display name for UI';
COMMENT ON COLUMN tenant_stages.title_kz IS 'Kazakh display name for UI (supports Cyrillic without special chars)';
COMMENT ON COLUMN tenant_stages.order_index IS 'Display order in Kanban board (lower = left)';

-- ============================================================
-- PART 2: Extend leads table with stage tracking
-- ============================================================

ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_key VARCHAR(64);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_updated_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_auto_moved BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_leads_stage_key ON leads(tenant_id, stage_key) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_stage_updated ON leads(stage_updated_at DESC) WHERE stage_updated_at IS NOT NULL;

COMMENT ON COLUMN leads.stage_key IS 'Current pipeline stage (references tenant_stages.key conceptually)';
COMMENT ON COLUMN leads.stage_updated_at IS 'Last time stage was changed';
COMMENT ON COLUMN leads.stage_auto_moved IS 'TRUE if AI moved stage automatically, FALSE if manual owner change';

-- ============================================================
-- PART 3: Extend tenants table with welcome sequence settings
-- ============================================================

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS website_url VARCHAR(512);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_voice_ru_url VARCHAR(1024);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_voice_kz_url VARCHAR(1024);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_photo_urls JSONB;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_sequence_enabled BOOLEAN DEFAULT TRUE NOT NULL;

COMMENT ON COLUMN tenants.website_url IS 'Company website URL sent in welcome sequence';
COMMENT ON COLUMN tenants.welcome_voice_ru_url IS 'URL to Russian voice message audio file';
COMMENT ON COLUMN tenants.welcome_voice_kz_url IS 'URL to Kazakh voice message audio file';
COMMENT ON COLUMN tenants.welcome_photo_urls IS 'Array of image URLs to send in welcome sequence, e.g. ["https://...", "https://..."]';
COMMENT ON COLUMN tenants.welcome_sequence_enabled IS 'Enable/disable automatic welcome sequence on first message';

-- Set default for existing tenants
UPDATE tenants SET welcome_sequence_enabled = TRUE WHERE welcome_sequence_enabled IS NULL;

-- ============================================================
-- PART 4: Seed default stages for existing tenants
-- ============================================================

-- Insert default stages for each tenant that doesn't have any stages yet
-- Using ON CONFLICT DO NOTHING for idempotency

DO $$
DECLARE
    tenant_record RECORD;
BEGIN
    FOR tenant_record IN SELECT id, name FROM tenants WHERE is_active = TRUE
    LOOP
        -- Check if tenant already has stages
        IF NOT EXISTS (SELECT 1 FROM tenant_stages WHERE tenant_id = tenant_record.id) THEN
            INSERT INTO tenant_stages (tenant_id, key, title_ru, title_kz, order_index, color)
            VALUES
                (tenant_record.id, 'no_reply', 'Нет ответа', 'Zhauap zhok', 0, '#9E9E9E'),
                (tenant_record.id, 'in_work', 'В работе', 'Zhumysta', 1, '#2196F3'),
                (tenant_record.id, 'wants_call', 'Хочет звонок', 'Qongyraw kalaidy', 2, '#FF9800'),
                (tenant_record.id, 'partial_data', 'Частичные данные', 'Zhartylai derekter', 3, '#FFC107'),
                (tenant_record.id, 'full_data', 'Полные данные', 'Tolyk derekter', 4, '#4CAF50'),
                (tenant_record.id, 'measurement_scheduled', 'Замер назначен', 'Olsheu tagindalgan', 5, '#9C27B0'),
                (tenant_record.id, 'success', 'Успех', 'Satti', 6, '#00C853'),
                (tenant_record.id, 'lost', 'Потерян', 'Zhogalgan', 7, '#F44336')
            ON CONFLICT (tenant_id, key) DO NOTHING;
            
            RAISE NOTICE 'Created default stages for tenant: % (ID: %)', tenant_record.name, tenant_record.id;
        ELSE
            RAISE NOTICE 'Tenant % (ID: %) already has stages, skipping', tenant_record.name, tenant_record.id;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- PART 5: Migrate existing lead.category → lead.stage_key
-- ============================================================

-- Map existing AI category values to stage_key
-- Only update leads that don't already have a stage_key set

UPDATE leads
SET 
    stage_key = CASE 
        WHEN category = 'no_reply' THEN 'no_reply'
        WHEN category = 'wants_call' THEN 'wants_call'
        WHEN category = 'partial_data' THEN 'partial_data'
        WHEN category = 'full_data' THEN 'full_data'
        WHEN category = 'measurement_assigned' THEN 'measurement_scheduled'
        WHEN category = 'measurement_done' THEN 'measurement_scheduled'
        WHEN category = 'rejected' THEN 'lost'
        WHEN category = 'won' THEN 'success'
        ELSE 'in_work'  -- fallback for unknown categories
    END,
    stage_updated_at = updated_at,
    stage_auto_moved = TRUE  -- mark as auto-assigned during migration
WHERE stage_key IS NULL AND category IS NOT NULL;

-- For leads with no category, default to first stage (no_reply)
UPDATE leads
SET 
    stage_key = 'no_reply',
    stage_updated_at = created_at,
    stage_auto_moved = FALSE
WHERE stage_key IS NULL;

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Check tenant_stages table
DO $$
DECLARE
    stage_count INTEGER;
    tenant_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO stage_count FROM tenant_stages;
    SELECT COUNT(*) INTO tenant_count FROM tenants WHERE is_active = TRUE;
    
    RAISE NOTICE '=== MIGRATION VERIFICATION ===';
    RAISE NOTICE 'Total stages created: %', stage_count;
    RAISE NOTICE 'Active tenants: %', tenant_count;
    RAISE NOTICE 'Expected stages: % (8 per tenant)', tenant_count * 8;
    
    IF stage_count >= tenant_count * 8 THEN
        RAISE NOTICE '✅ Stage seeding successful!';
    ELSE
        RAISE WARNING '⚠️  Some stages may be missing';
    END IF;
END $$;

-- Show sample stages
SELECT ts.tenant_id, t.name as tenant_name, ts.key, ts.title_ru, ts.order_index, ts.is_active
FROM tenant_stages ts
JOIN tenants t ON ts.tenant_id = t.id
WHERE t.is_active = TRUE
ORDER BY ts.tenant_id, ts.order_index
LIMIT 16;  -- Show first 2 tenants

-- Check leads migration
DO $$
DECLARE
    leads_with_stage INTEGER;
    leads_total INTEGER;
    leads_auto_moved INTEGER;
BEGIN
    SELECT COUNT(*) INTO leads_with_stage FROM leads WHERE stage_key IS NOT NULL;
    SELECT COUNT(*) INTO leads_total FROM leads;
    SELECT COUNT(*) INTO leads_auto_moved FROM leads WHERE stage_auto_moved = TRUE;
    
    RAISE NOTICE '';
    RAISE NOTICE '=== LEADS MIGRATION ===';
    RAISE NOTICE 'Total leads: %', leads_total;
    RAISE NOTICE 'Leads with stage_key: %', leads_with_stage;
    RAISE NOTICE 'Auto-assigned stages: %', leads_auto_moved;
    
    IF leads_with_stage = leads_total THEN
        RAISE NOTICE '✅ All leads have stage_key assigned!';
    ELSE
        RAISE WARNING '⚠️  Some leads missing stage_key';
    END IF;
END $$;

-- Stage distribution
SELECT stage_key, COUNT(*) as lead_count
FROM leads
WHERE stage_key IS NOT NULL
GROUP BY stage_key
ORDER BY lead_count DESC;

-- ============================================================
-- ROLLBACK SCRIPT (commented out - uncomment if needed)
-- ============================================================

-- WARNING: This will DELETE all stage data!
-- USE ONLY IN DEVELOPMENT OR EMERGENCY ROLLBACK

/*
-- Rollback in reverse order
ALTER TABLE leads DROP COLUMN IF EXISTS stage_auto_moved;
ALTER TABLE leads DROP COLUMN IF EXISTS stage_updated_at;
ALTER TABLE leads DROP COLUMN IF EXISTS stage_key;

ALTER TABLE tenants DROP COLUMN IF EXISTS welcome_sequence_enabled;
ALTER TABLE tenants DROP COLUMN IF EXISTS welcome_photo_urls;
ALTER TABLE tenants DROP COLUMN IF EXISTS welcome_voice_kz_url;
ALTER TABLE tenants DROP COLUMN IF EXISTS welcome_voice_ru_url;
ALTER TABLE tenants DROP COLUMN IF EXISTS website_url;

DROP TABLE IF EXISTS tenant_stages CASCADE;

RAISE NOTICE '⚠️  ROLLBACK COMPLETE - All stage data deleted';
*/
