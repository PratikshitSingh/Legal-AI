"""User queries: profiles, roles, and login bookkeeping."""

import json

from sqlalchemy import text

from ._engine import USER_COLUMNS, get_engine, with_retry


@with_retry
def get_or_create_user(
    email: str, full_name: str | None = None, firm: str | None = None, role: str = "viewer"
) -> str:
    """Insert a user, or touch the existing row for this email (upsert).

    Args:
        email: User email (required, must be unique)
        full_name: User's full name (optional)
        firm: User's organization/firm (optional)
        role: Role for a newly created user (default: 'viewer'); an existing
              user's role is never changed here

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


@with_retry
def get_user_by_id(user_id: str) -> dict | None:
    """Fetch user by ID; returns full user profile."""
    engine = get_engine()
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    SELECT {USER_COLUMNS}
                    FROM users
                    WHERE user_id = CAST(:user_id AS UUID)
                    """
                ),
                {"user_id": user_id},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


@with_retry
def get_user_by_email(email: str) -> dict | None:
    """Fetch user by email; returns dict with all user fields."""
    engine = get_engine()
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    SELECT {USER_COLUMNS}
                    FROM users
                    WHERE email = :email
                    """
                ),
                {"email": email},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


@with_retry
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

    # The SET clause is built from hardcoded column snippets only; every
    # value goes through bound parameters.
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


@with_retry
def update_user_role(user_id: str, role: str, changed_by_user_id: str | None = None) -> bool:
    """Update user's role (admin-only operation).

    Args:
        user_id: User ID to update
        role: New role ('viewer', 'editor', 'admin')
        changed_by_user_id: User ID of admin performing change (for audit)

    Returns:
        True if updated, False if user not found or invalid role
    """
    valid_roles = {"viewer", "editor", "admin"}
    if role not in valid_roles:
        return False

    engine = get_engine()
    with engine.begin() as conn:
        # Get old role for audit
        old_role = conn.execute(
            text("SELECT role FROM users WHERE user_id = CAST(:user_id AS UUID)"),
            {"user_id": user_id},
        ).scalar()

        if not old_role:
            return False

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
                    "old_values": json.dumps({"role": old_role}),
                    "new_values": json.dumps({"role": role}),
                    "changed_by": changed_by_user_id,
                },
            )

    return bool(result)


@with_retry
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
        rows = (
            conn.execute(
                text(
                    f"""
                    SELECT {USER_COLUMNS}
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@with_retry
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
        rows = (
            conn.execute(
                text(
                    f"""
                    SELECT {USER_COLUMNS}
                    FROM users
                    WHERE role = :role
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"role": role, "limit": limit},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@with_retry
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
