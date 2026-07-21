"""Database access layer for Neon Postgres, split by domain.

Call through the package — ``from legal_ai import db; db.get_user_by_id(...)``
— rather than importing domain modules directly. Tests monkeypatch functions
on this namespace, and calling through the package keeps those patches
effective for every caller.
"""

from ._engine import get_engine
from .documents import (
    create_document_record,
    get_all_documents,
    get_document_by_name_hash,
    log_document_audit,
)
from .jurisdictions import (
    get_all_jurisdictions,
    get_jurisdiction_tree,
    get_user_jurisdictions,
    update_user_jurisdictions,
)
from .schema import init_db
from .sessions import (
    add_session_message,
    get_session_messages,
    get_session_user_id,
    get_user_sessions,
    upsert_session,
)
from .tokens import (
    create_magic_link,
    create_refresh_token,
    revoke_refresh_tokens,
    validate_magic_link,
    validate_refresh_token,
)
from .users import (
    get_all_users,
    get_or_create_user,
    get_user_by_email,
    get_user_by_id,
    get_users_by_role,
    update_user_last_login,
    update_user_profile,
    update_user_role,
)

_initialized = False


def ensure_db() -> None:
    """Run ``init_db()`` once per process (lazy schema creation)."""
    global _initialized
    if not _initialized:
        # Resolved through this module's globals on purpose: patching
        # ``db.init_db`` in tests must also neuter this call.
        init_db()
        _initialized = True


__all__ = [
    "get_engine",
    "init_db",
    "ensure_db",
    # users
    "get_or_create_user",
    "get_user_by_id",
    "get_user_by_email",
    "update_user_profile",
    "update_user_role",
    "get_all_users",
    "get_users_by_role",
    "update_user_last_login",
    # tokens
    "create_magic_link",
    "validate_magic_link",
    "create_refresh_token",
    "validate_refresh_token",
    "revoke_refresh_tokens",
    # sessions
    "upsert_session",
    "get_user_sessions",
    "get_session_user_id",
    "get_session_messages",
    "add_session_message",
    # documents
    "create_document_record",
    "get_document_by_name_hash",
    "get_all_documents",
    "log_document_audit",
    # jurisdictions
    "get_all_jurisdictions",
    "get_jurisdiction_tree",
    "get_user_jurisdictions",
    "update_user_jurisdictions",
]
