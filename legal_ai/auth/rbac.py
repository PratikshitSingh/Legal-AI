"""Role-Based Access Control (RBAC): the role model and role display helpers."""

from . import auth

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


def display_role_badge(role: str | None = None) -> str:
    """Display role as a colored badge emoji.

    Args:
        role: Role to display. If None, shows current user's role.

    Returns:
        Emoji badge string
    """
    if role is None:
        role = auth.get_current_user_role()

    badges = {
        ROLE_VIEWER: "👁️ Viewer",
        ROLE_EDITOR: "✏️ Editor",
        ROLE_ADMIN: "👑 Admin",
    }
    return badges.get(role, "❓ Unknown")
