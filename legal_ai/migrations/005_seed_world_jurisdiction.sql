-- Migration 005: Seed root world jurisdiction and ensure data consistency
-- Date: 2026-05-25
-- Description: Initialize world jurisdiction as root hierarchy node

BEGIN;

-- ============================================================================
-- Insert root WORLD jurisdiction (all others reference this as parent eventually)
-- ============================================================================
INSERT INTO jurisdictions (code, name, parent_jurisdiction_id, level, region_code, flag_emoji, is_active, metadata)
VALUES ('WORLD', 'World', NULL, 'world', 'GLOBAL', '🌍', true, '{"description":"Root jurisdiction encompassing all regions"}'::jsonb)
ON CONFLICT (code) DO NOTHING;

-- ============================================================================
-- Ensure user_jurisdiction_preferences table exists for user preferences
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_jurisdiction_preferences (
    pref_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(jurisdiction_id) ON DELETE CASCADE,
    preference_order INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, jurisdiction_id)
);

CREATE INDEX IF NOT EXISTS idx_user_jurisdiction_preferences_user_id ON user_jurisdiction_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_user_jurisdiction_preferences_jurisdiction_id ON user_jurisdiction_preferences(jurisdiction_id);

-- ============================================================================
-- Ensure document metadata tracking for audit
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_metadata_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    changed_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_metadata_history_document_id ON document_metadata_history(document_id);
CREATE INDEX IF NOT EXISTS idx_document_metadata_history_created_at ON document_metadata_history(created_at DESC);

COMMIT;
