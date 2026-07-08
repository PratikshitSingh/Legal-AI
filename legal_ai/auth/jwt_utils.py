"""JWT token generation, validation, and refresh logic."""

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt


def get_jwt_secret() -> str:
    """Load JWT secret from environment; raise if not set."""
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise ValueError("JWT_SECRET not set in environment or .env")
    return secret


def get_access_token_expiry_seconds() -> int:
    """Access token expiry in seconds (default: 15 minutes)."""
    return int(os.environ.get("JWT_ACCESS_EXPIRY_SECONDS", 900))


def get_refresh_token_expiry_days() -> int:
    """Refresh token expiry in days (default: 7)."""
    return int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", 7))


def create_access_token(user_id: str, expires_in_seconds: int | None = None) -> str:
    """
    Create a short-lived JWT access token.

    Args:
        user_id: UUID of the user
        expires_in_seconds: Token expiry duration (default: 15 min from config)

    Returns:
        JWT token string
    """
    if expires_in_seconds is None:
        expires_in_seconds = get_access_token_expiry_seconds()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in_seconds)

    payload = {
        "user_id": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access",
    }

    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def create_refresh_token_string() -> str:
    """Generate a random refresh token (not JWT, just a random string)."""
    return secrets.token_urlsafe(32)


def validate_access_token(token: str) -> str:
    """
    Validate JWT access token and extract user_id.

    Args:
        token: JWT token string

    Returns:
        user_id (UUID as string)

    Raises:
        jwt.InvalidTokenError: If token is invalid, expired, or malformed
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])

        # Ensure token type is 'access'
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Invalid token type")

        user_id = payload.get("user_id")
        if not user_id:
            raise jwt.InvalidTokenError("Missing user_id in token")

        return user_id
    except jwt.ExpiredSignatureError:
        raise jwt.InvalidTokenError("Token expired")
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f"Invalid token: {e}")


def get_user_id_from_token_signature(token: str) -> str | None:
    """Extract user_id from a token with a VALID SIGNATURE, ignoring expiry.

    Used when restoring sessions from browser cookies: the access token may
    have expired (it is short-lived), but a valid signature still proves the
    user_id was issued by us. Expiry is then handled by the refresh flow,
    which validates the refresh token against the database.

    Returns:
        user_id if the signature is valid, None otherwise.
    """
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        if payload.get("type") != "access":
            return None
        return payload.get("user_id") or None
    except jwt.InvalidTokenError:
        return None


def is_access_token_expired(token: str) -> bool:
    """Check if access token is expired without raising exception."""
    try:
        jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        return False
    except jwt.ExpiredSignatureError:
        return True
    except jwt.InvalidTokenError:
        return True


def generate_auth_tokens(user_id: str) -> dict[str, str]:
    """
    Generate both access and refresh tokens for a user.

    Returns:
        {
            "access_token": "<JWT>",
            "refresh_token": "<random string>",
            "access_token_expires_in": <seconds>,
            "refresh_token_expires_in": <days>
        }
    """
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token_string()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_token_expires_in": get_access_token_expiry_seconds(),
        "refresh_token_expires_in": get_refresh_token_expiry_days(),
    }
