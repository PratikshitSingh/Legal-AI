"""Neon Postgres schema and helpers."""

import os
from datetime import datetime, timezone
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
    """Create sessions and audit_log tables if they do not exist."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id UUID PRIMARY KEY,
                    display_user TEXT NOT NULL DEFAULT 'demo-user',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGSERIAL PRIMARY KEY,
                    session_id UUID NOT NULL REFERENCES sessions(session_id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )


def upsert_session(session_id: str, display_user: str = "demo-user") -> None:
    now = datetime.now(timezone.utc)
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (session_id, display_user, created_at, last_seen_at)
                VALUES (CAST(:session_id AS UUID), :display_user, :now, :now)
                ON CONFLICT (session_id) DO UPDATE SET
                    display_user = EXCLUDED.display_user,
                    last_seen_at = EXCLUDED.last_seen_at
                """
            ),
            {"session_id": session_id, "display_user": display_user, "now": now},
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


def get_user_sessions(display_user: str, limit: int = 30) -> list[dict]:
    """Past chat sessions for a signed-in user, newest first."""
    with get_engine().connect() as conn:
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
                WHERE s.display_user = :display_user
                ORDER BY s.last_seen_at DESC
                LIMIT :limit
                """
            ),
            {"display_user": display_user, "limit": limit},
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
