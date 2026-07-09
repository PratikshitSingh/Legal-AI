"""Auth token queries: magic links and refresh tokens (stored hashed)."""

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from ._engine import get_engine, hash_token, with_retry


@with_retry
def create_magic_link(email: str, token: str, expires_in_minutes: int = 15) -> None:
    """Store magic link token (hashed) for passwordless auth."""
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_in_minutes)
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
                "token_hash": hash_token(token),
                "expires_at": expires_at,
            },
        )


@with_retry
def validate_magic_link(email: str, token: str) -> bool:
    """Validate magic link token; marks as used if valid."""
    token_hash = hash_token(token)
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


@with_retry
def create_refresh_token(user_id: str, token: str, expires_in_days: int | None = None) -> None:
    """Store refresh token (hashed) in DB for this user.

    Args:
        user_id: User ID (UUID)
        token: Refresh token to store (will be hashed)
        expires_in_days: Token expiry in days. If None, uses JWT_REFRESH_EXPIRY_DAYS env var (default 7)
    """
    if expires_in_days is None:
        expires_in_days = int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", 7))

    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
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
                "token_hash": hash_token(token),
                "expires_at": expires_at,
            },
        )


@with_retry
def validate_refresh_token(user_id: str, token: str) -> bool:
    """Validate refresh token for a user."""
    token_hash = hash_token(token)
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


@with_retry
def revoke_refresh_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (on sign-out)."""
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
