-- Owner-Managed Pipelines Database Migration (Refactored)
-- Component 1: Add tenant_stages table + extend leads/tenants for stage management
-- Date: 2026-02-09
-- IDEMPOTENT: Safe to run multiple times

-- ============================================================
-- PART 1: Create tenant_stages table (owner-managed Kanban columns)
-- ============================================================

CREATE TABLE IF NOT EXISTS tenant_stages (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stage_key VARCHAR(50) NOT NULL,
    title_ru VARCHAR(100) NOT NULL,
    title_kz VARCHAR(100) NOT NULL,
    color VARCHAR(7) NOT NULL DEFAULT '#94a3b8',
    order_index INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_tenant_stage_key UNIQUE (tenant_id, stage_key)
);

CREATE INDEX IF NOT EXISTS idx_tenant_stages_tenant_id ON tenant_stages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_stages_active ON tenant_stages(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_tenant_stages_order ON tenant_stages(tenant_id, order_index);

COMMENT ON TABLE tenant_stages IS 'Owner-managed pipeline stages (Kanban columns) per tenant';

-- ============================================================
-- PART 2: Extend leads table with stage tracking
-- ============================================================

ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_key VARCHAR(50);
-- Assuming stage_updated_at and stage_auto_moved were added in previous iteration or need to be added
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_updated_at TIMESTAMP; 
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_auto_moved BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_leads_stage_key ON leads(stage_key);

-- ============================================================
-- PART 3: Extend tenants table (Welcome sequence fields - kept from previous plan)
-- ============================================================

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS website_url VARCHAR(512);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_voice_ru_url VARCHAR(1024);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_voice_kz_url VARCHAR(1024);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_photo_urls JSONB;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS welcome_sequence_enabled BOOLEAN DEFAULT TRUE NOT NULL;

-- Set default for existing tenants
UPDATE tenants SET welcome_sequence_enabled = TRUE WHERE welcome_sequence_enabled IS NULL;

-- ============================================================
-- PART 4: Seed default stages for existing tenants
-- ============================================================

DO $$
DECLARE
    tenant_record RECORD;
BEGIN
    FOR tenant_record IN SELECT id, name FROM tenants WHERE is_active = TRUE
    LOOP
        -- Check if tenant already has stages
        IF NOT EXISTS (SELECT 1 FROM tenant_stages WHERE tenant_id = tenant_record.id) THEN
            INSERT INTO tenant_stages (tenant_id, stage_key, title_ru, title_kz, color, order_index, is_active)
            VALUES
                (tenant_record.id, 'unsorted', 'Неразобранное', 'Бөлінбеген', '#94a3b8', 0, TRUE),
                (tenant_record.id, 'in_progress', 'В работе', 'Жұмыста', '#3b82f6', 1, TRUE),
                (tenant_record.id, 'qualified', 'Квалифицированные', 'Біліктілік', '#8b5cf6', 2, TRUE),
                (tenant_record.id, 'won', 'Успешно', 'Сәтті', '#10b981', 3, TRUE),
                (tenant_record.id, 'lost', 'Отказ', 'Бас тарту', '#ef4444', 4, TRUE),
                (tenant_record.id, 'postponed', 'Отложено', 'Кейінге қалдырылды', '#6b7280', 5, TRUE)
            ON CONFLICT (tenant_id, stage_key) DO NOTHING;
            
            RAISE NOTICE 'Created default stages for tenant: % (ID: %)', tenant_record.name, tenant_record.id;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- PART 5: Migrate existing lead.category → lead.stage_key
-- ============================================================

UPDATE leads 
SET stage_key = CASE 
    WHEN category = 'no_reply' THEN 'unsorted'
    WHEN category = 'wants_call' THEN 'in_progress'
    WHEN category = 'partial_data' THEN 'in_progress'
    WHEN category = 'full_data' THEN 'qualified'
    WHEN category = 'measurement_assigned' THEN 'qualified'
    WHEN category = 'measurement_done' THEN 'qualified'
    WHEN category = 'rejected' THEN 'lost'
    WHEN category = 'non_target' THEN 'lost'
    WHEN category = 'postponed' THEN 'postponed'
    WHEN category = 'won' THEN 'won'
    ELSE 'unsorted'
END
WHERE stage_key IS NULL;

-- ============================================================
-- VERIFICATION
-- ============================================================
-- Check stages
SELECT tenant_id, stage_key, title_ru, order_index FROM tenant_stages ORDER BY tenant_id, order_index LIMIT 10;
