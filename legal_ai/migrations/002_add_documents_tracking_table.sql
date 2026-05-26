-- Migration 002: Add documents tracking table for admin uploads
-- Date: 2026-05-25
-- Description: Create documents table to track uploaded documents with metadata, content hash, and uploader info

BEGIN;

-- ============================================================================
-- Create documents table for tracking admin uploads
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    content_hash TEXT NOT NULL,
    uploaded_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    file_type TEXT DEFAULT 'pdf' NOT NULL,
    chunk_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================================================
-- Create indexes for duplicate detection and lookups
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_documents_name_hash ON documents(name, content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

-- ============================================================================
-- Create audit table for document uploads (for compliance)
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_audit_log_document_id ON document_audit_log(document_id);
CREATE INDEX IF NOT EXISTS idx_document_audit_log_user_id ON document_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_document_audit_log_created_at ON document_audit_log(created_at DESC);

COMMIT;
