"""Role-Based Access Control: the single source of truth for the role model.

Pure module — no Streamlit, no DB. ``auth`` layers the current-user context
on top of these checks.
"""

# ============================================================================
# Role Constants
# ============================================================================

ROLE_VIEWER = "viewer"
ROLE_EDITOR = "editor"
ROLE_ADMIN = "admin"

ROLE_HIERARCHY = {
    ROLE_VIEWER: 0,
    ROLE_EDITOR: 1,
    ROLE_ADMIN: 2,
}

# Permissions matrix: role -> allowed actions
ROLE_PERMISSIONS = {
    ROLE_VIEWER: {
        "read": True,
        "write": False,
        "admin": False,
        "manage_users": False,
    },
    ROLE_EDITOR: {
        "read": True,
        "write": True,
        "admin": False,
        "manage_users": False,
    },
    ROLE_ADMIN: {
        "read": True,
        "write": True,
        "admin": True,
        "manage_users": True,
    },
}

_ROLE_BADGES = {
    ROLE_VIEWER: "👁️ Viewer",
    ROLE_EDITOR: "✏️ Editor",
    ROLE_ADMIN: "👑 Admin",
}


def role_at_least(user_role: str, required_role: str) -> bool:
    """Check whether ``user_role`` meets or exceeds ``required_role``.

    Fails closed: an unknown required role never grants access, and an
    unknown user role never satisfies any requirement.
    """
    if required_role not in ROLE_HIERARCHY:
        return False
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY[required_role]


def display_role_badge(role: str) -> str:
    """Render a role as an emoji badge string."""
    return _ROLE_BADGES.get(role, "❓ Unknown")
