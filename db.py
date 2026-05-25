"""Neon Postgres schema and helpers."""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


@lru_cache
def get_engine():
    """Neon Postgres engine (lazy; requires psycopg2-binary)."""
    url = os.environ.get("NEON_DB_DATABASE_URL")
    if not url:
        raise ValueError("Set NEON_DB_DATABASE_URL in .env")
    return create_engine(url)


def init_db() -> None:
    """Create users, refresh_tokens, magic_links, sessions, and audit_log tables if they do not exist."""
    engine = get_engine()
    with engine.begin() as conn:
        # Create new tables for JWT auth
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email TEXT NOT NULL UNIQUE,
                    full_name TEXT,
                    firm TEXT,
                    role TEXT DEFAULT 'viewer' NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_login_at TIMESTAMPTZ
                );
                """
            )
        )
        
        # Add columns if they don't exist (for existing databases)
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS users
                ADD COLUMN IF NOT EXISTS full_name TEXT,
                ADD COLUMN IF NOT EXISTS firm TEXT,
                ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'viewer' NOT NULL;
                """
            )
        )
        
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    revoked_at TIMESTAMPTZ
                );
                """
            )
        )
        
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS magic_links (
                    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    used_at TIMESTAMPTZ
                );
                """
            )
        )
        
        # Migrate old sessions table: add user_id column if not present
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS sessions ADD COLUMN IF NOT EXISTS user_id UUID 
                REFERENCES users(user_id) ON DELETE CASCADE;
                """
            )
        )
        
        # If sessions table doesn't exist, create it
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
                    display_user TEXT DEFAULT 'demo-user',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        
        # Migrate old audit_log table: ensure foreign key is correct
        # First check if audit_log exists
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGSERIAL PRIMARY KEY,
                    session_id UUID NOT NULL REFERENCES sessions(session_id) ON 
DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        
        # Create roles table for RBAC
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS roles (
                    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    role_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    permissions JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        
        # Insert default roles if they don't exist
        conn.execute(
            text(
                """
                INSERT INTO roles (role_name, description, permissions) VALUES
                    ('viewer', 'Read-only access to documents and cases', '{"read": true, "write": false, "admin": false}'::jsonb),
                    ('editor', 'Can read and edit documents and cases', '{"read": true, "write": true, "admin": false}'::jsonb),
                    ('admin', 'Full access including user management', '{"read": true, "write": true, "admin": true}'::jsonb)
                ON CONFLICT (role_name) DO NOTHING;
                """
            )
        )
        
        # Create user audit log table for tracking profile changes
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_audit_log (
                    audit_id BIGSERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    action TEXT NOT NULL,
                    old_values JSONB,
                    new_values JSONB,
                    changed_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        
        # Create indexes
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);
                CREATE INDEX IF NOT EXISTS idx_magic_links_email ON magic_links(email);
                CREATE INDEX IF NOT EXISTS idx_magic_links_expires ON magic_links(expires_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_users_firm ON users(firm);
                CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_roles_role_name ON roles(role_name);
                CREATE INDEX IF NOT EXISTS idx_user_audit_log_user_id ON user_audit_log(user_id);
                CREATE INDEX IF NOT EXISTS idx_user_audit_log_created_at ON user_audit_log(created_at DESC);
                """
            )
        )


def _hash_token(token: str) -> str:
    """Hash token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ============================================================================
# User Management
# ============================================================================


def create_user(email: str, full_name: str | None = None, firm: str | None = None, role: str = "viewer") -> str:
    """Create a new user; returns user_id (UUID as string).
    
    Args:
        email: User email (required, must be unique)
        full_name: User's full name (optional)
        firm: User's organization/firm (optional)
        role: User's role (default: 'viewer')
    
    Returns:
        user_id as UUID string
    """
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO users (email, full_name, firm, role)
                VALUES (:email, :full_name, :firm, :role)
                ON CONFLICT (email) DO UPDATE SET updated_at = NOW()
                RETURNING user_id::text
                """
            ),
            {"email": email, "full_name": full_name, "firm": firm, "role": role},
        )
        return result.scalar()


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch user by ID; returns full user profile."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT 
                    user_id::text, email, full_name, firm, role,
                    created_at, updated_at, last_login_at
                FROM users
                WHERE user_id = CAST(:user_id AS UUID)
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    """Fetch user by email; returns dict with all user fields."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT 
                    user_id::text, email, full_name, firm, role,
                    created_at, updated_at, last_login_at
                FROM users
                WHERE email = :email
                """
            ),
            {"email": email},
        ).mappings().first()
    return dict(row) if row else None


def update_user_profile(user_id: str, full_name: str | None = None, firm: str | None = None) -> bool:
    """Update user's own profile (full_name, firm).
    
    Args:
        user_id: User ID to update
        full_name: New full name (optional, if provided updates)
        firm: New firm/organization (optional, if provided updates)
    
    Returns:
        True if updated, False if user not found
    """
    engine = get_engine()
    
    # Only update provided fields
    updates = []
    params = {"user_id": user_id}
    
    if full_name is not None:
        updates.append("full_name = :full_name")
        params["full_name"] = full_name
    
    if firm is not None:
        updates.append("firm = :firm")
        params["firm"] = firm
    
    if not updates:
        return True  # Nothing to update
    
    updates.append("updated_at = NOW()")
    update_clause = ", ".join(updates)
    
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE users
                SET {update_clause}
                WHERE user_id = CAST(:user_id AS UUID)
                RETURNING user_id::text
                """
            ),
            params,
        ).scalar()
    
    return bool(result)


def update_user_role(user_id: str, role: str, changed_by_user_id: str | None = None) -> bool:
    """Update user's role (admin-only operation).
    
    Args:
        user_id: User ID to update
        role: New role ('viewer', 'editor', 'admin')
        changed_by_user_id: User ID of admin performing change (for audit)
    
    Returns:
        True if updated, False if user not found or invalid role
    """
    # Validate role
    valid_roles = {"viewer", "editor", "admin"}
    if role not in valid_roles:
        return False
    
    engine = get_engine()
    with engine.begin() as conn:
        # Get old role for audit
        old_user = conn.execute(
            text(
                """
                SELECT role FROM users WHERE user_id = CAST(:user_id AS UUID)
                """
            ),
            {"user_id": user_id},
        ).scalar()
        
        if not old_user:
            return False
        
        # Update role
        result = conn.execute(
            text(
                """
                UPDATE users
                SET role = :role, updated_at = NOW()
                WHERE user_id = CAST(:user_id AS UUID)
                RETURNING user_id::text
                """
            ),
            {"user_id": user_id, "role": role},
        ).scalar()
        
        # Log audit entry
        if result and changed_by_user_id:
            conn.execute(
                text(
                    """
                    INSERT INTO user_audit_log (user_id, action, old_values, new_values, changed_by)
                    VALUES (CAST(:user_id AS UUID), :action, :old_values, :new_values, CAST(:changed_by AS UUID))
                    """
                ),
                {
                    "user_id": user_id,
                    "action": "role_update",
                    "old_values": f'{{"role": "{old_user}"}}'.replace("'", '"'),
                    "new_values": f'{{"role": "{role}"}}'.replace("'", '"'),
                    "changed_by": changed_by_user_id,
                },
            )
    
    return bool(result)


def get_all_users(limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch all users with pagination. Admin-only operation.
    
    Args:
        limit: Maximum number of users to return
        offset: Number of users to skip
    
    Returns:
        List of user dicts
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    user_id::text, email, full_name, firm, role,
                    created_at, updated_at, last_login_at
                FROM users
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        ).mappings().all()
    return [dict(row) for row in rows]


def get_users_by_role(role: str, limit: int = 100) -> list[dict]:
    """Fetch all users with a specific role.
    
    Args:
        role: Role to filter by ('viewer', 'editor', 'admin')
        limit: Maximum number of users to return
    
    Returns:
        List of user dicts with matching role
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    user_id::text, email, full_name, firm, role,
                    created_at, updated_at, last_login_at
                FROM users
                WHERE role = :role
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"role": role, "limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def update_user_last_login(user_id: str) -> None:
    """Update user's last_login_at timestamp."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE users
                SET last_login_at = NOW()
                WHERE user_id = CAST(:user_id AS UUID)
                """
            ),
            {"user_id": user_id},
        )


# ============================================================================
# Magic Links
# ============================================================================


def create_magic_link(email: str, token: str, expires_in_minutes: int = 15) -> None:
    """Store magic link token (hashed) for passwordless auth."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO magic_links (email, token_hash, expires_at)
                VALUES (:email, :token_hash, :expires_at)
                """
            ),
            {
                "email": email,
                "token_hash": _hash_token(token),
                "expires_at": expires_at,
            },
        )


def validate_magic_link(email: str, token: str) -> bool:
    """Validate magic link token; marks as used if valid."""
    token_hash = _hash_token(token)
    engine = get_engine()
    with engine.begin() as conn:
        # Check if token exists, not expired, and not already used
        result = conn.execute(
            text(
                """
                SELECT link_id FROM magic_links
                WHERE email = :email
                  AND token_hash = :token_hash
                  AND expires_at > NOW()
                  AND used_at IS NULL
                """
            ),
            {"email": email, "token_hash": token_hash},
        ).scalar()

        if not result:
            return False

        # Mark as used
        conn.execute(
            text(
                """
                UPDATE magic_links
                SET used_at = NOW()
                WHERE email = :email AND token_hash = :token_hash
                """
            ),
            {"email": email, "token_hash": token_hash},
        )
        return True


# ============================================================================
# Refresh Tokens
# ============================================================================


def create_refresh_token(user_id: str, token: str, expires_in_days: int = 7) -> None:
    """Store refresh token (hashed) in database."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
                VALUES (CAST(:user_id AS UUID), :token_hash, :expires_at)
                """
            ),
            {
                "user_id": user_id,
                "token_hash": _hash_token(token),
                "expires_at": expires_at,
            },
        )


def validate_refresh_token(user_id: str, token: str) -> bool:
    """Check if refresh token is valid and not revoked."""
    token_hash = _hash_token(token)
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT token_id FROM refresh_tokens
                WHERE user_id = CAST(:user_id AS UUID)
                  AND token_hash = :token_hash
                  AND expires_at > NOW()
                  AND revoked_at IS NULL
                """
            ),
            {"user_id": user_id, "token_hash": token_hash},
        ).scalar()
    return bool(result)


def revoke_refresh_tokens(user_id: str) -> None:
    """Revoke all active refresh tokens for a user (on sign-out)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE refresh_tokens
                SET revoked_at = NOW()
                WHERE user_id = CAST(:user_id AS UUID)
                  AND revoked_at IS NULL
                """
            ),
            {"user_id": user_id},
        )


# ============================================================================
# Sessions (updated for user_id)
# ============================================================================


def upsert_session(session_id: str, display_user: str = "demo-user", user_id: str | None = None) -> None:
    """Create or update session. Can use display_user (legacy) or user_id (new)."""
    now = datetime.now(timezone.utc)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (session_id, user_id, display_user, created_at, last_seen_at)
                VALUES (CAST(:session_id AS UUID), CAST(:user_id AS UUID), :display_user, :now, :now)
                ON CONFLICT (session_id) DO UPDATE SET
                    user_id = COALESCE(EXCLUDED.user_id, sessions.user_id),
                    display_user = EXCLUDED.display_user,
                    last_seen_at = EXCLUDED.last_seen_at
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "display_user": display_user,
                "now": now,
            },
        )


def log_message(session_id: str, role: str, content: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_log (session_id, role, content)
                VALUES (CAST(:session_id AS UUID), :role, :content)
                """
            ),
            {"session_id": session_id, "role": role, "content": content},
        )


def get_user_sessions(user_id_or_display_user: str, limit: int = 30) -> list[dict]:
    """Fetch past chat sessions for a user (by user_id UUID or display_user name)."""
    engine = get_engine()
    with engine.connect() as conn:
        # Try user_id first (UUID), fallback to display_user (text)
        rows = conn.execute(
            text(
                """
                SELECT s.session_id::text, s.created_at, s.last_seen_at,
                       (
                           SELECT a.content
                           FROM audit_log a
                           WHERE a.session_id = s.session_id
                           ORDER BY a.created_at DESC
                           LIMIT 1
                       ) AS last_message
                FROM sessions s
                WHERE (
                    s.user_id = CAST(:user_id AS UUID)
                    OR s.display_user = :display_user
                )
                ORDER BY s.last_seen_at DESC
                LIMIT :limit
                """
            ),
            {
                "user_id": user_id_or_display_user,
                "display_user": user_id_or_display_user,
                "limit": limit,
            },
        ).mappings().all()
    return [dict(r) for r in rows]


def get_session_messages(session_id: str) -> list[dict]:
    """Ordered conversation turns for a session."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role, content, created_at
                FROM audit_log
                WHERE session_id = CAST(:session_id AS UUID)
                ORDER BY created_at ASC
                """
            ),
            {"session_id": session_id},
        ).mappings().all()
    return [dict(r) for r in rows]


def get_session_user_id(session_id: str) -> str | None:
    """Fetch the user_id associated with a session."""
    engine = get_engine()
    with engine.connect() as conn:
        user_id = conn.execute(
            text(
                """
                SELECT user_id::text FROM sessions
                WHERE session_id = CAST(:session_id AS UUID)
                """
            ),
            {"session_id": session_id},
        ).scalar()
    return user_id
