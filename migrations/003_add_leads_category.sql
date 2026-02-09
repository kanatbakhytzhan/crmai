-- Add missing legacy column used by ORM selects
-- Safe to run multiple times
ALTER TABLE leads ADD COLUMN IF NOT EXISTS category VARCHAR(64);

-- Optional: quick verify
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'category';
