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


# A just-used magic link stays valid for this long. Browsers and hosting
# proxies (Streamlit Cloud reconnects, email-client prefetchers) routinely
# run the verification URL more than once; without a grace window the
# duplicate run consumes the token's result and the real user sees a false
# "Invalid or expired" error. The token still expires and still cannot be
# replayed outside this short window.
MAGIC_LINK_REUSE_GRACE_SECONDS = 60


@with_retry
def validate_magic_link(email: str, token: str) -> bool:
    """Validate magic link token; marks as used on first validation.

    Idempotent within MAGIC_LINK_REUSE_GRACE_SECONDS of first use so
    duplicate verification runs (proxy reconnects, prefetchers, double
    loads) succeed instead of erroring after the first run consumed it.
    """
    token_hash = hash_token(token)
    engine = get_engine()
    with engine.begin() as conn:
        # Token must exist, be unexpired, and be unused or only just used.
        result = conn.execute(
            text(
                """
                SELECT link_id FROM magic_links
                WHERE email = :email
                  AND token_hash = :token_hash
                  AND expires_at > NOW()
                  AND (
                    used_at IS NULL
                    OR used_at > NOW() - make_interval(secs => :grace_seconds)
                  )
                """
            ),
            {
                "email": email,
                "token_hash": token_hash,
                "grace_seconds": MAGIC_LINK_REUSE_GRACE_SECONDS,
            },
        ).scalar()

        if not result:
            return False

        # Mark as used on first validation only — re-validation within the
        # grace window must not extend the window.
        conn.execute(
            text(
                """
                UPDATE magic_links
                SET used_at = NOW()
                WHERE email = :email AND token_hash = :token_hash AND used_at IS NULL
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
