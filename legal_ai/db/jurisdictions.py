"""Jurisdiction queries: the hierarchy tree and per-user filter preferences."""

import logging

from sqlalchemy import text

from ._engine import get_engine, with_retry

logger = logging.getLogger(__name__)


@with_retry
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
                {"code": parent_code},
            ).scalar()
        else:
            parent_id = None

        # The WHERE clause switches between two fixed snippets; values are
        # bound parameters.
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


@with_retry
def get_user_jurisdictions(user_id: str) -> list[dict]:
    """Get list of jurisdictions selected by user for default filtering.

    Args:
        user_id: User ID

    Returns:
        List of jurisdiction dicts with preference_order
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = (
            conn.execute(
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
                {"user_id": user_id},
            )
            .mappings()
            .all()
        )

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
                text("DELETE FROM user_jurisdiction_preferences WHERE user_id = CAST(:user_id AS UUID)"),
                {"user_id": user_id},
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
                    {"user_id": user_id, "jurisdiction_id": jid, "order": order},
                )

        return True
    except Exception:
        logger.exception("Error updating user jurisdictions")
        return False
