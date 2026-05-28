"""Neon Postgres schema and helpers."""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

load_dotenv()


@lru_cache
def get_engine():
    """Neon Postgres engine (lazy; requires psycopg2-binary)."""
    url = os.environ.get("NEON_DB_DATABASE_URL")
    if not url:
        raise ValueError("Set NEON_DB_DATABASE_URL in .env")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE_SECONDS", 300)),
        connect_args={
            "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT_SECONDS", 10)),
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )


def _retry_after_operational_error(fn, *, retries: int = 1):
    """Retry once after disposing pooled connections on transient DB disconnects."""
    try:
        return fn()
    except OperationalError:
        if retries <= 0:
            raise
        get_engine().dispose()
        return _retry_after_operational_error(fn, retries=retries - 1)


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
            # Debug: Check why it failed
            debug_result = conn.execute(
                text(
                    """
                    SELECT link_id, expires_at, used_at, email, token_hash 
                    FROM magic_links
                    WHERE email = :email OR token_hash = :token_hash
                    ORDER BY created_at DESC LIMIT 3
                    """
                ),
                {"email": email, "token_hash": token_hash},
            ).fetchall()
            
            if debug_result:
                print(f"DEBUG: Found magic links for investigation:")
                for row in debug_result:
                    print(f"  - Email match: {row[3] == email}, Token match: {row[4] == token_hash}, Used: {row[2] is not None}, Expires: {row[1]}")
            else:
                print(f"DEBUG: No magic links found for email={email} or token_hash={token_hash[:20]}...")
            
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
# Refresh Tokens (in DB)
# ============================================================================


def create_refresh_token(user_id: str, token: str, expires_in_days: int | None = None) -> None:
    """Store refresh token (hashed) in DB for this user.
    
    Args:
        user_id: User ID (UUID)
        token: Refresh token to store (will be hashed)
        expires_in_days: Token expiry in days. If None, uses JWT_REFRESH_EXPIRY_DAYS env var (default 7)
    """
    if expires_in_days is None:
        expires_in_days = int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", 7))
    
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
    """Validate refresh token for a user."""
    token_hash = _hash_token(token)
    def _run_query():
        engine = get_engine()
        with engine.connect() as conn:
            return conn.execute(
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

    result = _retry_after_operational_error(_run_query)
    
    return bool(result)


def revoke_refresh_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (on sign-out)."""
    def _run_update():
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE refresh_tokens
                    SET revoked_at = NOW()
                    WHERE user_id = CAST(:user_id AS UUID) AND revoked_at IS NULL
                    """
                ),
                {"user_id": user_id},
            )

    _retry_after_operational_error(_run_update)


# ============================================================================
# Sessions (Chat Sessions)
# ============================================================================


def upsert_session(session_id: str, user_id: str | None = None, display_user: str = "demo-user") -> None:
    """Create or update a chat session."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (session_id, user_id, display_user, created_at, last_seen_at)
                VALUES (CAST(:session_id AS UUID), CAST(:user_id AS UUID), :display_user, NOW(), NOW())
                ON CONFLICT (session_id) DO UPDATE
                SET user_id = CAST(EXCLUDED.user_id AS UUID),
                    display_user = EXCLUDED.display_user,
                    last_seen_at = NOW()
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "display_user": display_user,
            },
        )


def get_user_sessions(user_id: str, limit: int = 50) -> list[dict]:
    """Get all chat sessions for a user."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    s.session_id::text,
                    s.user_id::text,
                    s.display_user,
                    s.created_at,
                    s.last_seen_at,
                    COALESCE(user_last.content, any_last.content) AS last_message,
                    COALESCE(user_last.created_at, any_last.created_at) AS last_message_at
                FROM sessions s
                LEFT JOIN LATERAL (
                    SELECT content, created_at
                    FROM audit_log
                    WHERE session_id = s.session_id
                      AND role = 'user'
                    ORDER BY created_at DESC
                    LIMIT 1
                ) AS user_last ON TRUE
                LEFT JOIN LATERAL (
                    SELECT content, created_at
                    FROM audit_log
                    WHERE session_id = s.session_id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) AS any_last ON TRUE
                WHERE s.user_id = CAST(:user_id AS UUID)
                  AND any_last.created_at IS NOT NULL
                ORDER BY COALESCE(user_last.created_at, any_last.created_at) DESC, s.last_seen_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def get_session_user_id(session_id: str) -> str | None:
    """Get the user ID associated with a session.
    
    Args:
        session_id: Session ID (UUID)
    
    Returns:
        user_id as string if session exists, None otherwise
    """
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


# ============================================================================
# Chat Messages (Audit Log)
# ============================================================================



def get_session_messages(session_id: str) -> list[dict]:
    """Get all messages in a chat session.
    
    Args:
        session_id: Session ID to fetch messages for
    
    Returns:
        List of message dicts with id, role, content, created_at
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    id,
                    role,
                    content,
                    created_at
                FROM audit_log
                WHERE session_id = CAST(:session_id AS UUID)
                ORDER BY created_at ASC
                """
            ),
            {"session_id": session_id},
        ).mappings().all()
    return [dict(row) for row in rows]


def add_session_message(session_id: str, role: str, content: str) -> None:
    """Add a message to a chat session's audit log.
    
    Args:
        session_id: Session ID
        role: Message role ('user', 'assistant', etc.)
        content: Message content
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_log (session_id, role, content)
                VALUES (CAST(:session_id AS UUID), :role, :content)
                """
            ),
            {"session_id": session_id, "role": role, "content": content},
        )


def log_message(session_id: str, role: str, content: str) -> None:
    """Convenience alias for add_session_message.
    
    Add a message to a chat session's audit log.
    
    Args:
        session_id: Session ID
        role: Message role ('user', 'assistant', etc.)
        content: Message content
    """
    add_session_message(session_id, role, content)


# ============================================================================
# Document Management (Admin Uploads)
# ============================================================================


def create_document_record(
    name: str,
    description: str,
    content_hash: str,
    uploaded_by_user_id: str,
    file_type: str = "pdf",
    chunk_count: int = 0,
    metadata: dict | None = None,
) -> dict | None:
    """Create a record for an uploaded document in the documents table.
    
    Args:
        name: Document name
        description: Document description
        content_hash: MD5 hash of document content (for duplicate detection)
        uploaded_by_user_id: UUID of admin uploading document
        file_type: File type ('pdf' or 'txt')
        chunk_count: Number of chunks created in Chroma
        metadata: Additional metadata (file size, text length, etc.)
    
    Returns:
        Document record dict with document_id, or None if error
    """
    if metadata is None:
        metadata = {}
    
    engine = get_engine()
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO documents (name, description, content_hash, uploaded_by, file_type, chunk_count, metadata)
                    VALUES (:name, :description, :content_hash, CAST(:uploaded_by_user_id AS UUID), :file_type, :chunk_count, :metadata::jsonb)
                    RETURNING document_id::text, name, description, created_at
                    """
                ),
                {
                    "name": name,
                    "description": description,
                    "content_hash": content_hash,
                    "uploaded_by_user_id": uploaded_by_user_id,
                    "file_type": file_type,
                    "chunk_count": chunk_count,
                    "metadata": str(metadata).replace("'", '"'),
                },
            ).mappings().first()
        
        return dict(result) if result else None
    except Exception as e:
        print(f"Error creating document record: {e}")
        return None


def get_document_by_name_hash(name: str, content_hash: str) -> dict | None:
    """Fetch document by name and content hash (exact match for duplicate detection).
    
    Args:
        name: Document name
        content_hash: MD5 hash of document content
    
    Returns:
        Document dict, or None if not found
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT 
                    document_id::text, name, description, content_hash,
                    uploaded_by::text, file_type, chunk_count, 
                    created_at, updated_at, metadata
                FROM documents
                WHERE name = :name AND content_hash = :content_hash
                LIMIT 1
                """
            ),
            {"name": name, "content_hash": content_hash},
        ).mappings().first()
    
    return dict(row) if row else None


def get_documents_by_name(name: str, limit: int = 10) -> list[dict]:
    """Fetch all documents with a given name (for duplicate detection across versions).
    
    Args:
        name: Document name
        limit: Maximum documents to return
    
    Returns:
        List of document dicts
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    document_id::text, name, description, content_hash,
                    uploaded_by::text, file_type, chunk_count,
                    created_at, updated_at, metadata
                FROM documents
                WHERE name = :name
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"name": name, "limit": limit},
        ).mappings().all()
    
    return [dict(row) for row in rows]


def get_all_documents(limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch all uploaded documents with pagination.
    
    Args:
        limit: Maximum documents to return
        offset: Number of documents to skip
    
    Returns:
        List of document dicts
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    d.document_id::text, d.name, d.description, d.content_hash,
                    d.uploaded_by::text, u.email as uploaded_by_email,
                    d.file_type, d.chunk_count,
                    d.created_at, d.updated_at, d.metadata
                FROM documents d
                LEFT JOIN users u ON d.uploaded_by = u.user_id
                ORDER BY d.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        ).mappings().all()
    
    return [dict(row) for row in rows]


def get_documents_by_uploader(uploaded_by_user_id: str, limit: int = 50) -> list[dict]:
    """Fetch all documents uploaded by a specific user.
    
    Args:
        uploaded_by_user_id: UUID of uploader
        limit: Maximum documents to return
    
    Returns:
        List of document dicts
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    document_id::text, name, description, content_hash,
                    uploaded_by::text, file_type, chunk_count,
                    created_at, updated_at, metadata
                FROM documents
                WHERE uploaded_by = CAST(:uploaded_by_user_id AS UUID)
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"uploaded_by_user_id": uploaded_by_user_id, "limit": limit},
        ).mappings().all()
    
    return [dict(row) for row in rows]


def log_document_audit(document_id: str, user_id: str, action: str, details: dict | None = None) -> None:
    """Log document action to audit trail.
    
    Args:
        document_id: Document ID
        user_id: User ID performing action
        action: Action type ('upload', 'delete', 'view', etc.)
        details: Additional details (JSON)
    """
    if details is None:
        details = {}
    
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO document_audit_log (document_id, user_id, action, details)
                    VALUES (CAST(:document_id AS UUID), CAST(:user_id AS UUID), :action, :details::jsonb)
                    """
                ),
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "action": action,
                    "details": str(details).replace("'", '"'),
                },
            )
    except Exception as e:
        print(f"Error logging document audit: {e}")


# ============================================================================
# Jurisdiction Management (Multi-Jurisdiction Support)
# ============================================================================


def get_jurisdiction_tree(parent_code: str | None = None) -> list[dict]:
    """Get hierarchical jurisdiction structure for UI.
    
    Args:
        parent_code: If provided, only return children of this jurisdiction code
                     If None, returns root (WORLD)
    
    Returns:
        List of jurisdiction dicts with nested children
    """
    engine = get_engine()
    with engine.connect() as conn:
        if parent_code:
            parent_id = conn.execute(
                text("SELECT jurisdiction_id::text FROM jurisdictions WHERE code = :code"),
                {"code": parent_code}
            ).scalar()
        else:
            parent_id = None
        
        # Get jurisdictions at this level
        query = """
            SELECT 
                jurisdiction_id::text,
                code,
                name,
                level,
                flag_emoji,
                region_code
            FROM jurisdictions
            """
        
        params = {}
        if parent_id:
            query += "WHERE parent_jurisdiction_id = CAST(:parent_id AS UUID)"
            params["parent_id"] = parent_id
        else:
            query += "WHERE code = 'WORLD'"
        
        query += " ORDER BY name"
        
        rows = conn.execute(text(query), params).mappings().all()
    
    return [dict(row) for row in rows]


def get_user_jurisdictions(user_id: str) -> list[dict]:
    """Get list of jurisdictions selected by user for default filtering.
    
    Args:
        user_id: User ID
    
    Returns:
        List of jurisdiction dicts with preference_order
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    ujp.jurisdiction_id::text,
                    j.code,
                    j.name,
                    j.level,
                    ujp.preference_order
                FROM user_jurisdiction_preferences ujp
                JOIN jurisdictions j ON ujp.jurisdiction_id = j.jurisdiction_id
                WHERE ujp.user_id = CAST(:user_id AS UUID)
                ORDER BY ujp.preference_order ASC
                """
            ),
            {"user_id": user_id}
        ).mappings().all()
    
    return [dict(row) for row in rows]


def update_user_jurisdictions(user_id: str, jurisdiction_ids: list[str]) -> bool:
    """Save user's preferred jurisdictions for filtering.
    
    Args:
        user_id: User ID
        jurisdiction_ids: List of jurisdiction IDs (UUIDs as strings) in preferred order
    
    Returns:
        True if updated successfully
    """
    engine = get_engine()
    try:
        with engine.begin() as conn:
            # Delete existing preferences
            conn.execute(
                text(
                    "DELETE FROM user_jurisdiction_preferences WHERE user_id = CAST(:user_id AS UUID)"
                ),
                {"user_id": user_id}
            )
            
            # Insert new preferences
            for order, jid in enumerate(jurisdiction_ids, start=1):
                conn.execute(
                    text(
                        """
                        INSERT INTO user_jurisdiction_preferences (user_id, jurisdiction_id, preference_order)
                        VALUES (CAST(:user_id AS UUID), CAST(:jurisdiction_id AS UUID), :order)
                        """
                    ),
                    {"user_id": user_id, "jurisdiction_id": jid, "order": order}
                )
        
        return True
    except Exception as e:
        print(f"Error updating user jurisdictions: {e}")
        return False


def get_document_versions(document_id: str) -> list[dict]:
    """Get all versions of a document with change summary.
    
    Args:
        document_id: Document ID
    
    Returns:
        List of version dicts ordered by effective_date DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    version_id::text,
                    document_id::text,
                    version,
                    effective_date,
                    created_by::text,
                    change_summary,
                    superseded_by_version_id::text,
                    created_at
                FROM document_versions
                WHERE document_id = CAST(:document_id AS UUID)
                ORDER BY effective_date DESC
                """
            ),
            {"document_id": document_id}
        ).mappings().all()
    
    return [dict(row) for row in rows]


def create_document_version(
    document_id: str,
    version: str,
    effective_date: str,
    change_summary: str,
    created_by_user_id: str | None = None
) -> dict | None:
    """Create a new version record for a document.
    
    Args:
        document_id: Document ID
        version: Version string (e.g., "1.1", "2.0")
        effective_date: Date version becomes effective (ISO format)
        change_summary: Summary of changes in this version
        created_by_user_id: User ID creating the version (optional)
    
    Returns:
        Version record dict, or None if error
    """
    engine = get_engine()
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO document_versions (
                        document_id, version, effective_date, change_summary, created_by
                    )
                    VALUES (
                        CAST(:document_id AS UUID),
                        :version,
                        CAST(:effective_date AS DATE),
                        :change_summary,
                        CAST(:created_by AS UUID)
                    )
                    RETURNING version_id::text, document_id::text, version, effective_date, created_at
                    """
                ),
                {
                    "document_id": document_id,
                    "version": version,
                    "effective_date": effective_date,
                    "change_summary": change_summary,
                    "created_by": created_by_user_id
                }
            ).mappings().first()
        
        return dict(result) if result else None
    except Exception as e:
        print(f"Error creating document version: {e}")
        return None


def get_documents_by_jurisdiction(jurisdiction_id: str, limit: int = 50) -> list[dict]:
    """Get all documents for a specific jurisdiction.
    
    Args:
        jurisdiction_id: Jurisdiction ID (UUID as string)
        limit: Maximum documents to return
    
    Returns:
        List of document dicts
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT 
                    d.document_id::text,
                    d.name,
                    d.description,
                    d.jurisdiction_id::text,
                    j.code as jurisdiction_code,
                    j.name as jurisdiction_name,
                    d.version,
                    d.status,
                    d.effective_date,
                    d.doc_type_id::text,
                    dt.name as doc_type,
                    d.created_at
                FROM documents d
                JOIN jurisdictions j ON d.jurisdiction_id = j.jurisdiction_id
                LEFT JOIN document_types dt ON d.doc_type_id = dt.doc_type_id
                WHERE d.jurisdiction_id = CAST(:jurisdiction_id AS UUID)
                AND d.is_latest = true
                ORDER BY d.effective_date DESC
                LIMIT :limit
                """
            ),
            {"jurisdiction_id": jurisdiction_id, "limit": limit}
        ).mappings().all()
    
    return [dict(row) for row in rows]
