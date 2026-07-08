"""Engine management and shared query infrastructure for the db package."""

import hashlib
import os
from functools import lru_cache, wraps

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

# Shared column projections — the single source for SELECT lists that several
# queries share, so adding a column cannot drift between them.
USER_COLUMNS = """
    user_id::text, email, full_name, firm, role,
    created_at, updated_at, last_login_at
"""

DOCUMENT_COLUMNS = """
    document_id::text, name, description, content_hash,
    uploaded_by::text, file_type, chunk_count,
    created_at, updated_at, metadata
"""


@lru_cache
def get_engine():
    """Neon Postgres engine (lazy; requires psycopg2-binary).

    Pool settings are tuned for Neon serverless: pre-ping and recycle survive
    scale-to-zero, keepalives hold the TCP path open through proxies.
    """
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


def with_retry(fn):
    """Retry a DB operation once after a transient disconnect.

    Neon scale-to-zero closes idle server connections. ``pool_pre_ping``
    catches most stale connections; this decorator covers the rest by
    disposing the pool and re-running the operation. Safe because the
    disconnect surfaces on the first statement, before any commit.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except OperationalError:
            get_engine().dispose()
            return fn(*args, **kwargs)

    return wrapper


def hash_token(token: str) -> str:
    """Hash a token (SHA-256) for secure at-rest storage."""
    return hashlib.sha256(token.encode()).hexdigest()
