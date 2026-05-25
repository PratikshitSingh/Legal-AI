"""Role-Based Access Control (RBAC) utilities for Streamlit."""

import functools
from typing import Callable

import streamlit as st

from . import auth
from legal_ai.db import db


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

# Permissions matrix: role -> list of allowed actions
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


# ============================================================================
# Permission Checking Functions
# ============================================================================


def get_user_permissions(role: str | None = None) -> dict:
    """Get permissions for a role.
    
    Args:
        role: Role name. If None, uses current user's role.
    
    Returns:
        Dict of permissions for the role
    """
    if role is None:
        role = auth.get_current_user_role()
    
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[ROLE_VIEWER])


def can_perform_action(action: str, role: str | None = None) -> bool:
    """Check if a role can perform an action.
    
    Args:
        action: Action name (e.g., 'read', 'write', 'admin')
        role: Role to check. If None, uses current user's role.
    
    Returns:
        True if the role can perform the action
    """
    if role is None:
        role = auth.get_current_user_role()
    
    permissions = get_user_permissions(role)
    return permissions.get(action, False)


def require_permission(action: str) -> bool:
    """Require that current user has permission for an action.
    
    Shows an error message if not authorized.
    
    Args:
        action: Action name to check
    
    Returns:
        True if authorized, False otherwise
    """
    if not can_perform_action(action):
        current_role = auth.get_current_user_role()
        st.error(f"❌ You don't have permission to perform '{action}'. Your role is '{current_role}'.")
        return False
    return True


# ============================================================================
# Streamlit Decorators
# ============================================================================


def require_role(required_role: str) -> Callable:
    """Decorator to require a specific role to execute a function.
    
    Usage:
        @require_role('admin')
        def delete_user():
            st.write("Deleting user...")
    
    Args:
        required_role: Minimum required role ('viewer', 'editor', 'admin')
    
    Returns:
        Decorated function that checks role before executing
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not auth.is_signed_in():
                st.error("❌ You must be signed in to access this feature.")
                return None
            
            if not auth.has_role(required_role):
                st.error(
                    f"❌ Access denied. This feature requires '{required_role}' role. "
                    f"Your current role is '{auth.get_current_user_role()}'."
                )
                return None
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_permission_decorator(action: str) -> Callable:
    """Decorator to require permission for an action.
    
    Usage:
        @require_permission_decorator('admin')
        def manage_system():
            st.write("Managing system...")
    
    Args:
        action: Action name to check permission for
    
    Returns:
        Decorated function that checks permission before executing
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not auth.is_signed_in():
                st.error("❌ You must be signed in to access this feature.")
                return None
            
            if not require_permission(action):
                return None
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_login(func: Callable) -> Callable:
    """Decorator to require user to be signed in.
    
    Usage:
        @require_login
        def profile_page():
            st.write("Profile page")
    
    Args:
        func: Function to decorate
    
    Returns:
        Decorated function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not auth.is_signed_in():
            st.error("❌ You must be signed in to access this page.")
            return None
        return func(*args, **kwargs)
    
    return wrapper


# ============================================================================
# UI Components for RBAC
# ============================================================================


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


def display_user_info() -> None:
    """Display current user information in sidebar."""
    if not auth.is_signed_in():
        return
    
    profile = auth.get_current_user_profile()
    if not profile:
        return
    
    st.sidebar.divider()
    st.sidebar.subheader("👤 Profile")
    st.sidebar.write(f"**Email:** {profile['email']}")
    
    if profile.get('full_name'):
        st.sidebar.write(f"**Name:** {profile['full_name']}")
    
    if profile.get('firm'):
        st.sidebar.write(f"**Firm:** {profile['firm']}")
    
    role_badge = display_role_badge(profile['role'])
    st.sidebar.write(f"**Role:** {role_badge}")


def permission_required_component(action: str, component: Callable) -> None:
    """Conditionally render a component based on permission.
    
    Usage:
        permission_required_component('admin', lambda: st.write("Admin panel"))
    
    Args:
        action: Action to check permission for
        component: Callable that renders the component (usually a lambda)
    """
    if can_perform_action(action):
        component()
    else:
        st.info(f"ℹ️ This feature requires '{action}' permission (your role: {auth.get_current_user_role()})")


# ============================================================================
# Admin Utilities
# ============================================================================


def list_users_with_roles(limit: int = 100) -> list[dict]:
    """Get all users with their roles. Admin only.
    
    Args:
        limit: Maximum number of users to return
    
    Returns:
        List of user dicts with role info, or empty list if not admin
    """
    auth.ensure_db()
    
    if not auth.is_admin():
        return []
    
    return db.get_all_users(limit=limit)


def assign_role(user_id: str, new_role: str) -> dict:
    """Assign a new role to a user. Admin only.
    
    Args:
        user_id: User to update
        new_role: New role to assign
    
    Returns:
        {"status": "success|error", "message": "..."}
    """
    auth.ensure_db()
    
    if not auth.is_admin():
        return {"status": "error", "message": "Only admins can assign roles."}
    
    if new_role not in ROLE_HIERARCHY:
        return {"status": "error", "message": f"Invalid role: {new_role}"}
    
    try:
        success = db.update_user_role(user_id, new_role, changed_by_user_id=auth.get_current_user_id())
        
        if success:
            return {"status": "success", "message": f"User role updated to {new_role}"}
        else:
            return {"status": "error", "message": "User not found or update failed"}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}
