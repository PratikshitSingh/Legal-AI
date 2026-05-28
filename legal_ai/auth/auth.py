"""Auth layer: JWT + magic links + Neon Postgres session persistence."""

import os
import secrets
import uuid
from urllib.parse import quote

import streamlit as st

from legal_ai.db import db
from legal_ai.services.email_service import send_magic_link_email
from legal_ai.core import config, utils
from . import jwt_utils
from . import browser_storage

_db_initialized = False


def ensure_db() -> None:
    global _db_initialized
    if not _db_initialized:
        db.init_db()
        _db_initialized = True


# ============================================================================
# Session State Helpers
# ============================================================================


def init_auth() -> None:
    """
    Initialize auth on page load.
    Restores auth from query parameters (from magic link) or browser storage.
    Should be called once at the start of each page.
    """
    # Allow re-checking browser state when session has no auth.
    # If we've already initialized and a signed-in user exists, skip work.
    if st.session_state.get("_legal_ai_auth_initialized") and st.session_state.get("legal_ai_user_id"):
        return

    st.session_state._legal_ai_auth_initialized = True

    # If session has no user, attempt to restore from browser storage so
    # new tabs will pick up an existing sign-in immediately.
    if not st.session_state.get("legal_ai_user_id"):
        if browser_storage.restore_auth_in_session():
            return

    # Legacy fallback for one-time handoff parameters.
    query_params = st.query_params
    if all(k in query_params for k in ["user_id", "access_token", "email"]):
        st.session_state.legal_ai_user_id = query_params.get("user_id")
        st.session_state.legal_ai_user_email = query_params.get("email")
        st.session_state.legal_ai_access_token = query_params.get("access_token")
        st.session_state.legal_ai_refresh_token = query_params.get("refresh_token", "")
        st.session_state.legal_ai_user_role = query_params.get("role", "viewer")
        st.session_state.legal_ai_user_full_name = query_params.get("full_name")
        st.session_state.legal_ai_user_firm = query_params.get("firm")

        browser_storage.store_auth_in_browser(
            st.session_state.legal_ai_user_id,
            st.session_state.legal_ai_user_email,
            st.session_state.legal_ai_access_token,
            st.session_state.legal_ai_refresh_token,
            st.session_state.legal_ai_user_role,
            st.session_state.legal_ai_user_full_name,
            st.session_state.legal_ai_user_firm,
        )

        st.query_params.clear()


def is_signed_in() -> bool:
    """Check if user is signed in (has valid access token in session)."""
    return bool(st.session_state.get("legal_ai_user_id"))


def get_current_user_id() -> str | None:
    """Get current user's UUID from session state."""
    return st.session_state.get("legal_ai_user_id")


def get_current_user() -> str | None:
    """Get current user's email (for backward compatibility with existing code)."""
    return st.session_state.get("legal_ai_user_email")


def get_current_user_role() -> str:
    """Get current user's role from session state. Returns 'viewer' if not signed in."""
    return st.session_state.get("legal_ai_user_role", "viewer")


def get_current_user_profile() -> dict | None:
    """Get current user's full profile from session state."""
    if not is_signed_in():
        return None
    
    return {
        "user_id": get_current_user_id(),
        "email": get_current_user(),
        "full_name": st.session_state.get("legal_ai_user_full_name"),
        "firm": st.session_state.get("legal_ai_user_firm"),
        "role": get_current_user_role(),
    }


def get_current_access_token() -> str | None:
    """Get current access token from session state."""
    return st.session_state.get("legal_ai_access_token")


def get_current_refresh_token() -> str | None:
    """Get current refresh token from session state."""
    return st.session_state.get("legal_ai_refresh_token")


def set_auth_tokens(user_id: str, email: str, access_token: str, refresh_token: str, 
                   role: str = "viewer", full_name: str | None = None, firm: str | None = None) -> None:
    """Store auth tokens and user profile in session state and browser cookie."""
    st.session_state.legal_ai_user_id = user_id
    st.session_state.legal_ai_user_email = email
    st.session_state.legal_ai_access_token = access_token
    st.session_state.legal_ai_refresh_token = refresh_token
    st.session_state.legal_ai_user_role = role
    st.session_state.legal_ai_user_full_name = full_name
    st.session_state.legal_ai_user_firm = firm
    
    # Also store in browser localStorage for persistence across page reloads
    browser_storage.store_auth_in_browser(
        user_id, email, access_token, refresh_token, role, full_name, firm
    )


# ============================================================================
# Magic Link Flow
# ============================================================================


def request_magic_link(email: str, app_url: str = None) -> dict[str, str]:
    """
    Request a magic link for passwordless sign-in.
    
    Args:
        email: User's email address
        app_url: Base URL for the app (e.g., https://legal-ai.streamlit.app)
                If None, uses get_app_base_url() from config or environment
    
    Returns:
        {"status": "success|error", "message": "<message>"}
    """
    email = (email or "").strip().lower()
    if not email:
        return {"status": "error", "message": "Email cannot be empty"}

    try:
        ensure_db()
        
        # Generate magic link token
        magic_token = secrets.token_urlsafe(32)
        
        # Store magic link in DB (hashed)
        db.create_magic_link(email, magic_token, expires_in_minutes=15)
        
        # Determine app URL: use provided value or get from config
        if app_url is None:
            app_url = config.get_app_base_url()
        
        # Include both token and email in the magic link (URL-encode the email)
        encoded_email = quote(email, safe='')
        magic_link_url = f"{app_url}?token={magic_token}&email={encoded_email}"
        
        # Send email with magic link
        success = send_magic_link_email(email, magic_link_url)
        if not success:
            return {"status": "error", "message": "Failed to send email. Please try again."}
        
        return {
            "status": "success",
            "message": f"Check your email ({email}) for the magic link!",
        }
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}


def verify_magic_link(token: str) -> dict[str, str]:
    """
    Verify magic link token and sign in user.
    
    Returns:
        {"status": "success|error", "message": "<message>", "user_id": "<uuid>", "email": "<email>"}
    """
    try:
        ensure_db()
        
        # For now, we need to store the email in session state before calling this
        # In a real app, we'd look up the email from the token
        # For Streamlit, we'll handle this in app.py with query params
        
        # This is a placeholder; actual implementation will be in app.py
        return {"status": "error", "message": "Invalid or expired magic link"}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}


def verify_magic_link_token(email: str, token: str) -> dict:
    """
    Verify magic link token for a specific email.
    
    Returns:
        {
            "status": "success|error",
            "user_id": "<uuid>" (if success),
            "email": "<email>" (if success),
            "role": "<role>" (if success),
            "full_name": "<name>" (if success),
            "firm": "<firm>" (if success),
            "access_token": "<jwt>" (if success),
            "refresh_token": "<token>" (if success),
            "message": "<error message>" (if error)
        }
    """
    try:
        ensure_db()
        
        # Normalize email
        email = (email or "").strip().lower()
        
        # Validate magic link token
        is_valid = db.validate_magic_link(email, token)
        if not is_valid:
            print(f"DEBUG: Magic link validation failed for email={email}, token_length={len(token)}")
            return {"status": "error", "message": "Invalid or expired magic link"}
        
        # Create or get user (defaults to 'viewer' role for new users)
        user_id = db.create_user(email)
        db.update_user_last_login(user_id)
        
        # Fetch full user profile (includes role, full_name, firm)
        user = db.get_user_by_id(user_id)
        
        # Generate JWT tokens
        tokens = jwt_utils.generate_auth_tokens(user_id)
        
        # Store refresh token in DB
        db.create_refresh_token(user_id, tokens["refresh_token"])
        
        print(f"DEBUG: Magic link verified successfully for user={user_id}, email={email}")
        
        return {
            "status": "success",
            "user_id": user_id,
            "email": email,
            "role": user.get("role", "viewer"),
            "full_name": user.get("full_name"),
            "firm": user.get("firm"),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        }
    except Exception as e:
        print(f"DEBUG: Exception in verify_magic_link_token: {str(e)}")
        return {"status": "error", "message": f"Error: {str(e)}"}


# ============================================================================
# Token Refresh
# ============================================================================


def refresh_access_token_if_needed() -> bool:
    """
    Check if access token is expired and refresh if needed using refresh token.
    
    Returns:
        True if token is still valid (or was refreshed), False if refresh failed
    """
    access_token = get_current_access_token()
    refresh_token = get_current_refresh_token()
    user_id = get_current_user_id()

    if not access_token or not refresh_token or not user_id:
        return False

    # Check if access token is expired
    if not jwt_utils.is_access_token_expired(access_token):
        return True  # Still valid

    # Try to refresh using refresh token
    try:
        if db.validate_refresh_token(user_id, refresh_token):
            new_access_token = jwt_utils.create_access_token(user_id)
            st.session_state.legal_ai_access_token = new_access_token
            return True
    except Exception as exc:
        print(f"Error validating refresh token: {exc}")

    # Refresh token invalid/expired or DB unavailable
    return False


# ============================================================================
# Sign Out
# ============================================================================


def sign_out() -> None:
    """Sign out user and revoke refresh tokens."""
    user_id = get_current_user_id()
    if user_id:
        try:
            ensure_db()
            db.revoke_refresh_tokens(user_id)
        except Exception as e:
            print(f"Error revoking tokens: {e}")

    # Clear session state
    for key in (
        "legal_ai_user_id",
        "legal_ai_user_email",
        "legal_ai_access_token",
        "legal_ai_refresh_token",
        "legal_ai_user_role",
        "legal_ai_user_full_name",
        "legal_ai_user_firm",
        "legal_ai_session_id",
        "messages",
        "selected_session_id",
    ):
        st.session_state.pop(key, None)
    
    # Clear from browser storage
    browser_storage.clear_auth_from_browser()
    
    # Clear query params
    st.query_params.clear()


# ============================================================================
# Session Management (chat sessions)
# ============================================================================


def get_or_create_session_id(user_id: str | None = None) -> str:
    """Create or get a chat session tied to the user."""
    ensure_db()
    
    # Use provided user_id or current session state
    if user_id is None:
        user_id = get_current_user_id()

    if "legal_ai_session_id" not in st.session_state:
        st.session_state.legal_ai_session_id = str(uuid.uuid4())

    session_id = st.session_state.legal_ai_session_id
    
    # Upsert session with user_id
    db.upsert_session(
        session_id,
        user_id=user_id,
        display_user=get_current_user() or "anonymous",
    )
    
    return session_id


def start_new_chat(user_id: str | None = None) -> str:
    """New session for the current user; clears in-memory UI messages."""
    ensure_db()
    
    if user_id is None:
        user_id = get_current_user_id()

    session_id = str(uuid.uuid4())
    st.session_state.legal_ai_session_id = session_id
    st.session_state.messages = []
    st.session_state.selected_session_id = session_id

    # Upsert session with user_id
    db.upsert_session(
        session_id,
        user_id=user_id,
        display_user=get_current_user() or "anonymous",
    )

    return session_id


def switch_to_session(session_id: str) -> None:
    """Switch to an existing chat session."""
    ensure_db()
    user_id = get_current_user_id()
    
    st.session_state.legal_ai_session_id = session_id
    st.session_state.selected_session_id = session_id
    
    # Update session's user_id
    if user_id:
        db.upsert_session(session_id, user_id=user_id, display_user=get_current_user() or "anonymous")


def list_past_chats(user_id: str | None = None) -> list[dict]:
    """List past chat sessions for the current user."""
    ensure_db()
    
    if user_id is None:
        user_id = get_current_user_id()

    if not user_id:
        return []

    return db.get_user_sessions(user_id)


# ============================================================================
# RBAC (Role-Based Access Control)
# ============================================================================


def is_admin() -> bool:
    """Check if current user is an admin."""
    return get_current_user_role() == "admin"


def is_editor() -> bool:
    """Check if current user is an editor or admin."""
    role = get_current_user_role()
    return role in ("editor", "admin")


def has_role(required_role: str) -> bool:
    """Check if current user has at least the required role.
    
    Role hierarchy: viewer < editor < admin
    
    Args:
        required_role: 'viewer', 'editor', or 'admin'
    
    Returns:
        True if user has the required role or higher
    """
    role_hierarchy = {"viewer": 0, "editor": 1, "admin": 2}
    current = role_hierarchy.get(get_current_user_role(), -1)
    required = role_hierarchy.get(required_role, -1)
    return current >= required


def require_role(required_role: str) -> bool:
    """Require specific role; return False and show error if not authorized.
    
    Args:
        required_role: 'viewer', 'editor', or 'admin'
    
    Returns:
        True if authorized, False otherwise (error already displayed)
    """
    if not has_role(required_role):
        st.error(f"❌ Access denied. This feature requires '{required_role}' role or higher.")
        return False
    return True


def check_permission(user_id: str, required_role: str) -> bool:
    """Check if a specific user has required role.
    
    Args:
        user_id: User UUID to check
        required_role: Required role level
    
    Returns:
        True if user has the required role or higher
    """
    ensure_db()
    user = db.get_user_by_id(user_id)
    if not user:
        return False
    
    role_hierarchy = {"viewer": 0, "editor": 1, "admin": 2}
    user_level = role_hierarchy.get(user.get("role", "viewer"), -1)
    required_level = role_hierarchy.get(required_role, -1)
    return user_level >= required_level
