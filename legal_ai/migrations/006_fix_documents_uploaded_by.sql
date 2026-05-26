-- Fix Migration: Make uploaded_by nullable in documents table
-- Date: 2026-05-25
-- Description: Allow NULL values for uploaded_by to support system-generated documents

BEGIN;

-- Make uploaded_by nullable
ALTER TABLE documents
ALTER COLUMN uploaded_by DROP NOT NULL;

COMMIT;
