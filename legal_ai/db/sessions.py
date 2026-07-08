"""Chat session queries: sessions and their message audit log."""

from sqlalchemy import text

from ._engine import get_engine, with_retry


@with_retry
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


@with_retry
def get_user_sessions(user_id: str, limit: int = 50) -> list[dict]:
    """Get all chat sessions for a user, newest activity first.

    Each row carries the latest user message (falling back to the latest
    message of any role) so the sidebar can label past chats.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = (
            conn.execute(
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
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@with_retry
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


@with_retry
def get_session_messages(session_id: str) -> list[dict]:
    """Get all messages in a chat session.

    Args:
        session_id: Session ID to fetch messages for

    Returns:
        List of message dicts with id, role, content, created_at
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = (
            conn.execute(
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
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@with_retry
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
