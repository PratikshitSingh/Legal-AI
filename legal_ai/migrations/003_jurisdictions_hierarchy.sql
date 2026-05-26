-- Migration 003: Create jurisdictions hierarchy tables
-- Date: 2026-05-25
-- Description: Establish hierarchical jurisdiction structure for multi-country support

BEGIN;

-- ============================================================================
-- Create jurisdictions table (hierarchical)
-- ============================================================================
CREATE TABLE IF NOT EXISTS jurisdictions (
    jurisdiction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_jurisdiction_id UUID REFERENCES jurisdictions(jurisdiction_id) ON DELETE CASCADE,
    level TEXT NOT NULL CHECK (level IN ('world', 'region', 'country', 'state', 'city')),
    region_code TEXT,
    flag_emoji TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================================================
-- Create document types table
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_types (
    doc_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Create languages table
-- ============================================================================
CREATE TABLE IF NOT EXISTS languages (
    language_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    native_name TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Create indexes for performance
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_jurisdictions_code ON jurisdictions(code);
CREATE INDEX IF NOT EXISTS idx_jurisdictions_parent_id ON jurisdictions(parent_jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_jurisdictions_level ON jurisdictions(level);
CREATE INDEX IF NOT EXISTS idx_jurisdictions_region_code ON jurisdictions(region_code);
CREATE INDEX IF NOT EXISTS idx_jurisdictions_is_active ON jurisdictions(is_active);

CREATE INDEX IF NOT EXISTS idx_document_types_name ON document_types(name);
CREATE INDEX IF NOT EXISTS idx_document_types_is_active ON document_types(is_active);

CREATE INDEX IF NOT EXISTS idx_languages_code ON languages(code);
CREATE INDEX IF NOT EXISTS idx_languages_is_active ON languages(is_active);

-- ============================================================================
-- Insert default document types
-- ============================================================================
INSERT INTO document_types (name, description, category) VALUES
    ('regulation', 'Legal regulation or statute', 'legislation'),
    ('directive', 'EU directive or similar', 'legislation'),
    ('guidance', 'Guidance, guidance notes, or FAQs', 'guidance'),
    ('case_law', 'Court decisions and case law', 'case_law'),
    ('statute', 'Statute or legislative act', 'legislation'),
    ('ordinance', 'Municipal or local ordinance', 'legislation'),
    ('policy', 'Government policy document', 'policy'),
    ('bill', 'Proposed legislation', 'legislation')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- Insert default languages
-- ============================================================================
INSERT INTO languages (code, name, native_name) VALUES
    ('en', 'English', 'English'),
    ('es', 'Spanish', 'Español'),
    ('fr', 'French', 'Français'),
    ('de', 'German', 'Deutsch'),
    ('it', 'Italian', 'Italiano'),
    ('pt', 'Portuguese', 'Português'),
    ('nl', 'Dutch', 'Nederlands'),
    ('pl', 'Polish', 'Polski'),
    ('sv', 'Swedish', 'Svenska'),
    ('da', 'Danish', 'Dansk'),
    ('fi', 'Finnish', 'Suomi'),
    ('el', 'Greek', 'Ελληνικά'),
    ('hu', 'Hungarian', 'Magyar'),
    ('cs', 'Czech', 'Čeština'),
    ('ro', 'Romanian', 'Română'),
    ('bg', 'Bulgarian', 'Български'),
    ('hr', 'Croatian', 'Hrvatski'),
    ('et', 'Estonian', 'Eesti'),
    ('lv', 'Latvian', 'Latvian'),
    ('lt', 'Lithuanian', 'Lietuvių')
ON CONFLICT (code) DO NOTHING;

COMMIT;
