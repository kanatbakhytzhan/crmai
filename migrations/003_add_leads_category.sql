-- Add missing legacy columns used by ORM selects
-- Safe to run multiple times
ALTER TABLE leads ADD COLUMN IF NOT EXISTS category VARCHAR(64);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_score VARCHAR(32);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_inbound_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_outbound_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS handoff_mode VARCHAR(16);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS extracted_fields JSON;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_key VARCHAR(64);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_updated_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_auto_moved BOOLEAN;

-- Optional: quick verify
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'leads' AND column_name IN ('category','lead_score','last_inbound_at','last_outbound_at','handoff_mode','extracted_fields','stage_key','stage_updated_at','stage_auto_moved');
