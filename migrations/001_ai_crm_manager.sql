-- AI CRM Manager Database Migration
-- Phase A: Add fields for lead categorization, followup tracking, and AmoCRM sync
-- Date: 2026-02-08
-- WARNING: Run this script ONLY ONCE. Creates new columns and tables.

-- ============================================================
-- PART 1: Extend Lead table with AI CRM fields
-- ============================================================

-- Add AI CRM Manager fields to leads table
ALTER TABLE leads ADD COLUMN IF NOT EXISTS category VARCHAR(64);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_score VARCHAR(32);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_inbound_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_outbound_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS handoff_mode VARCHAR(16) DEFAULT 'ai' NOT NULL;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS extracted_fields JSONB;

COMMENT ON COLUMN leads.category IS 'Lead category: no_reply, wants_call, partial_data, full_data, measurement_assigned, measurement_done, rejected, won';
COMMENT ON COLUMN leads.lead_score IS 'Lead temperature: hot, warm, cold';
COMMENT ON COLUMN leads.last_inbound_at IS 'Timestamp of last message FROM client';
COMMENT ON COLUMN leads.last_outbound_at IS 'Timestamp of last message TO client (AI or human)';
COMMENT ON COLUMN leads.handoff_mode IS 'Control mode: ai (automatic) or human (manual takeover)';
COMMENT ON COLUMN leads.extracted_fields IS 'Structured data extracted from conversation: {name, city, phone, house_length, house_width, house_height, foundation_cover, doors_count, windows_count, wants_call, preferred_call_time, has_house_photo}';

-- ============================================================
-- PART 2: Extend Tenant table with followup settings
-- ============================================================

-- Add auto-followup configuration fields to tenants table
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS followup_enabled BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS followup_delays_minutes JSONB;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS followup_template_ru TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS followup_template_kz TEXT;

COMMENT ON COLUMN tenants.followup_enabled IS 'Enable/disable auto-followup system for this tenant';
COMMENT ON COLUMN tenants.followup_delays_minutes IS 'Array of delay values in minutes, e.g., [5, 30] for followup 1 at +5min, followup 2 at +35min';
COMMENT ON COLUMN tenants.followup_template_ru IS 'Russian followup message template with {name} placeholders';
COMMENT ON COLUMN tenants.followup_template_kz IS 'Kazakh followup message template';

-- Set default followup delays for existing tenants
UPDATE tenants 
SET followup_delays_minutes = '[5, 30]'::jsonb 
WHERE followup_delays_minutes IS NULL;

-- Set default RU template
UPDATE tenants 
SET followup_template_ru = E'Здравствуйте{name}! 👋\n\nМы компания по продаже алюминиевых сэндвич-панелей.\n\nМожем рассчитать стоимость для вашего проекта?\n\nОтветьте, если интересно, и наш менеджер свяжется с вами в ближайшее время.'
WHERE followup_template_ru IS NULL;

-- Set default KZ template (without special characters)
UPDATE tenants 
SET followup_template_kz = E'Salem{name}! 👋\n\nBiz alyuminievyy sendvich-panelderdi satamyz.\n\nSіzdің zhobaңyz usһіn qұnyn eseptep bere alamyz ba?\n\nQyzїqtї bolsa, zhauap beriңiz, bizdің menedzher zhaqїn arada habarlasynady.'
WHERE followup_template_kz IS NULL;

-- ============================================================
-- PART 3: Create LeadFollowup table
-- ============================================================

CREATE TABLE IF NOT EXISTS lead_followups (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    scheduled_at TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    followup_number INTEGER NOT NULL,
    template_used TEXT,
    status VARCHAR(32) DEFAULT 'pending' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_lead_followups_lead_id ON lead_followups(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_followups_tenant_id ON lead_followups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_lead_followups_scheduled_at ON lead_followups(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_lead_followups_status ON lead_followups(status);

-- Composite index for worker queries: WHERE status='pending' AND scheduled_at <= NOW()
CREATE INDEX IF NOT EXISTS idx_lead_followups_pending_scheduled 
ON lead_followups(status, scheduled_at) 
WHERE status = 'pending';

COMMENT ON TABLE lead_followups IS 'Scheduled auto-followup messages for leads that have not replied';
COMMENT ON COLUMN lead_followups.scheduled_at IS 'When to send this followup message';
COMMENT ON COLUMN lead_followups.sent_at IS 'When the message was actually sent (NULL if not sent yet)';
COMMENT ON COLUMN lead_followups.followup_number IS 'Sequence number: 1, 2, 3... for this lead';
COMMENT ON COLUMN lead_followups.status IS 'Status: pending (not sent), sent (delivered), cancelled (skipped due to reply or handoff)';

-- ============================================================
-- PART 4: Create TenantCategoryStageMapping table
-- ============================================================

CREATE TABLE IF NOT EXISTS tenant_category_stage_mappings (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL,
    stage_key VARCHAR(64) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_tenant_category_mapping UNIQUE(tenant_id, category)
);

-- Index for tenant lookups
CREATE INDEX IF NOT EXISTS idx_category_mappings_tenant_id ON tenant_category_stage_mappings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_category_mappings_category ON tenant_category_stage_mappings(category);

COMMENT ON TABLE tenant_category_stage_mappings IS 'Maps local lead categories to AmoCRM pipeline stage keys for automatic sync';
COMMENT ON COLUMN tenant_category_stage_mappings.category IS 'Local category: no_reply, wants_call, partial_data, full_data, etc.';
COMMENT ON COLUMN tenant_category_stage_mappings.stage_key IS 'Internal stage key from tenant_pipeline_mappings: NEW, IN_WORK, WON, etc.';

-- ============================================================
-- PART 5: Insert default category mappings (optional)
-- ============================================================

-- Example: Default mappings for first tenant (ID=1)
-- Uncomment and customize as needed:

/*
INSERT INTO tenant_category_stage_mappings (tenant_id, category, stage_key, is_active)
VALUES 
    (1, 'no_reply', 'UNREAD', TRUE),
    (1, 'wants_call', 'CALL_1', TRUE),
    (1, 'partial_data', 'IN_WORK', TRUE),
    (1, 'full_data', 'MEASUREMENT_ASSIGNED', TRUE),
    (1, 'measurement_done', 'AFTER_MEASUREMENT_REJECT', TRUE),
    (1, 'won', 'WON', TRUE),
    (1, 'rejected', 'LOST', TRUE)
ON CONFLICT (tenant_id, category) DO NOTHING;
*/

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Check Lead table columns
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'leads' 
AND column_name IN ('category', 'lead_score', 'last_inbound_at', 'last_outbound_at', 'handoff_mode', 'extracted_fields')
ORDER BY column_name;

-- Check Tenant table columns
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'tenants' 
AND column_name IN ('followup_enabled', 'followup_delays_minutes', 'followup_template_ru', 'followup_template_kz')
ORDER BY column_name;

-- Check LeadFollowup table exists
SELECT table_name FROM information_schema.tables WHERE table_name = 'lead_followups';

-- Check TenantCategoryStageMapping table exists
SELECT table_name FROM information_schema.tables WHERE table_name = 'tenant_category_stage_mappings';

-- Check indexes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename IN ('lead_followups', 'tenant_category_stage_mappings')
ORDER BY tablename, indexname;

-- ============================================================
-- ROLLBACK SCRIPT (DANGEROUS - USE WITH CAUTION)
-- ============================================================

/*
-- To rollback this migration (will DELETE all followup data!):

DROP TABLE IF EXISTS lead_followups CASCADE;
DROP TABLE IF NOT EXISTS tenant_category_stage_mappings CASCADE;

ALTER TABLE leads DROP COLUMN IF EXISTS category;
ALTER TABLE leads DROP COLUMN IF EXISTS lead_score;
ALTER TABLE leads DROP COLUMN IF EXISTS last_inbound_at;
ALTER TABLE leads DROP COLUMN IF EXISTS last_outbound_at;
ALTER TABLE leads DROP COLUMN IF EXISTS handoff_mode;
ALTER TABLE leads DROP COLUMN IF EXISTS extracted_fields;

ALTER TABLE tenants DROP COLUMN IF EXISTS followup_enabled;
ALTER TABLE tenants DROP COLUMN IF EXISTS followup_delays_minutes;
ALTER TABLE tenants DROP COLUMN IF EXISTS followup_template_ru;
ALTER TABLE tenants DROP COLUMN IF EXISTS followup_template_kz;
*/

-- ============================================================
-- MIGRATION COMPLETE
-- ============================================================
-- Next steps:
-- 1. Verify changes: Run verification queries above
-- 2. Update application code to use new fields
-- 3. Test followup scheduler with test data
-- 4. Configure category mappings in admin UI or SQL
