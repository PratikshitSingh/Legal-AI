-- Migration 001: Add user profile fields and RBAC support
-- Date: 2026-05-24
-- Description: Add full_name, firm, and role columns to users table; create roles table

BEGIN;

-- ============================================================================
-- Add profile and role columns to users table
-- ============================================================================
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS full_name TEXT,
ADD COLUMN IF NOT EXISTS firm TEXT,
ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'viewer' NOT NULL;

-- Update timestamp for existing records
UPDATE users SET updated_at = NOW() WHERE role IS NULL;

-- ============================================================================
-- Create roles table for future extensibility
-- ============================================================================
CREATE TABLE IF NOT EXISTS roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name TEXT NOT NULL UNIQUE,
    description TEXT,
    permissions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default roles
INSERT INTO roles (role_name, description, permissions) VALUES
    ('viewer', 'Read-only access to documents and cases', '{"read": true, "write": false, "admin": false}'::jsonb),
    ('editor', 'Can read and edit documents and cases', '{"read": true, "write": true, "admin": false}'::jsonb),
    ('admin', 'Full access including user management', '{"read": true, "write": true, "admin": true}'::jsonb)
ON CONFLICT (role_name) DO NOTHING;

-- ============================================================================
-- Add indexes for performance
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_firm ON users(firm);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_roles_role_name ON roles(role_name);

-- ============================================================================
-- Add audit table for tracking role changes (optional, for compliance)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_audit_log_user_id ON user_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_user_audit_log_created_at ON user_audit_log(created_at DESC);

COMMIT;
