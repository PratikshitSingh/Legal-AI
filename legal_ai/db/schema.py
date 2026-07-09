"""Schema creation for the auth/session tables.

``init_db()`` creates the tables the auth flow needs and is safe to re-run
(everything is IF NOT EXISTS / ON CONFLICT). The documents/jurisdictions
tables are managed separately by the SQL files in ``legal_ai/migrations/``
(applied via ``scripts/run_migrations.py``) — both must have run for the full
app to work.
"""

from sqlalchemy import text

from ._engine import get_engine


def init_db() -> None:
    """Create users, refresh_tokens, magic_links, sessions, and audit_log tables if they do not exist."""
    engine = get_engine()
    with engine.begin() as conn:
        _create_auth_tables(conn)
        _create_session_tables(conn)
        _create_rbac_tables(conn)
        _seed_default_roles(conn)
        _create_indexes(conn)


def _create_auth_tables(conn) -> None:
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


def _create_session_tables(conn) -> None:
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


def _create_rbac_tables(conn) -> None:
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

    # User audit log for tracking profile changes
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


def _seed_default_roles(conn) -> None:
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


def _create_indexes(conn) -> None:
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);
            CREATE INDEX IF NOT EXISTS idx_magic_links_email ON magic_links(email);
            CREATE INDEX IF NOT EXISTS idx_magic_links_expires ON magic_links(expires_at);
            CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_roles_role_name ON roles(role_name);
            CREATE INDEX IF NOT EXISTS idx_user_audit_log_user_id ON user_audit_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_audit_log_created_at ON user_audit_log(created_at DESC);
            """
        )
    )
