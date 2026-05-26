-- Migration 004: Refactor documents table for multi-jurisdiction support
-- Date: 2026-05-25
-- Description: Add jurisdiction, version, document type, and status tracking to documents table

BEGIN;

-- ============================================================================
-- Alter documents table to add new fields
-- ============================================================================
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS jurisdiction_id UUID REFERENCES jurisdictions(jurisdiction_id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS doc_type_id UUID REFERENCES document_types(doc_type_id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS language_id UUID REFERENCES languages(language_id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS version TEXT DEFAULT '1.0',
ADD COLUMN IF NOT EXISTS effective_date DATE,
ADD COLUMN IF NOT EXISTS expiration_date DATE,
ADD COLUMN IF NOT EXISTS source_url TEXT,
ADD COLUMN IF NOT EXISTS section_title TEXT,
ADD COLUMN IF NOT EXISTS is_latest BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'archived', 'deprecated')),
ADD COLUMN IF NOT EXISTS parent_document_id UUID REFERENCES documents(document_id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS total_characters INT,
ADD COLUMN IF NOT EXISTS last_updated_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS update_reason TEXT;

-- ============================================================================
-- Create document_versions table for version history
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    effective_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    change_summary TEXT,
    superseded_by_version_id UUID REFERENCES document_versions(version_id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================================================
-- Create chunk_metadata table for normalized chunk fields
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    jurisdiction_id UUID REFERENCES jurisdictions(jurisdiction_id) ON DELETE SET NULL,
    version TEXT,
    section_title TEXT,
    chunk_index INT,
    effective_date DATE,
    status TEXT,
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Add indexes for multi-jurisdiction queries
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction_id ON documents(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type_id ON documents(doc_type_id);
CREATE INDEX IF NOT EXISTS idx_documents_language_id ON documents(language_id);
CREATE INDEX IF NOT EXISTS idx_documents_version ON documents(version);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_is_latest ON documents(is_latest);
CREATE INDEX IF NOT EXISTS idx_documents_effective_date ON documents(effective_date);
CREATE INDEX IF NOT EXISTS idx_documents_parent_id ON documents(parent_document_id);

CREATE INDEX IF NOT EXISTS idx_document_versions_document_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_version ON document_versions(version);
CREATE INDEX IF NOT EXISTS idx_document_versions_created_at ON document_versions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chunk_metadata_document_id ON chunk_metadata(document_id);
CREATE INDEX IF NOT EXISTS idx_chunk_metadata_jurisdiction_id ON chunk_metadata(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_chunk_metadata_version ON chunk_metadata(version);
CREATE INDEX IF NOT EXISTS idx_chunk_metadata_status ON chunk_metadata(status);

-- ============================================================================
-- Add user profile fields for jurisdiction preferences
-- ============================================================================
ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_jurisdictions TEXT[] DEFAULT ARRAY[]::TEXT[],
ADD COLUMN IF NOT EXISTS preferred_doc_types TEXT[] DEFAULT ARRAY[]::TEXT[],
ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC',
ADD COLUMN IF NOT EXISTS language_preference TEXT DEFAULT 'en';

COMMIT;
