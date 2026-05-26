"""Browser storage utilities for persistent session management using localStorage."""

import json
import streamlit as st
from streamlit.components.v1 import html


def store_auth_in_browser(user_id: str, email: str, access_token: str, 
                          refresh_token: str, role: str, full_name: str | None, 
                          firm: str | None) -> None:
    """Store auth tokens in browser localStorage."""
    auth_data = {
        "user_id": user_id,
        "email": email,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": role,
        "full_name": full_name,
        "firm": firm,
    }
    
    # JavaScript to store in localStorage
    js_code = f"""
    <script>
        localStorage.setItem('legal_ai_auth', JSON.stringify({json.dumps(auth_data)}));
    </script>
    """
    html(js_code)


def restore_auth_from_browser() -> dict | None:
    """
    Restore auth tokens from browser localStorage.
    
    Returns:
        Dict with auth data if found, None otherwise
    """
    # JavaScript to retrieve from localStorage
    js_code = """
    <script>
        const auth = localStorage.getItem('legal_ai_auth');
        if (auth) {
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: JSON.parse(auth)}, '*');
        } else {
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: null}, '*');
        }
    </script>
    """
    
    # Try to get from sessionStorage as fallback
    return _get_from_local_storage()


def _get_from_local_storage() -> dict | None:
    """Helper to extract localStorage data via JavaScript injection."""
    # Create a custom HTML component to read localStorage
    html_code = """
    <script>
    const authData = localStorage.getItem('legal_ai_auth');
    if (authData) {
        parent.document.body.innerText = authData;
    }
    </script>
    """
    # Note: This is a simplified approach. For production, use proper streamlit-js-eval
    # or a custom Streamlit component
    return None


def clear_auth_from_browser() -> None:
    """Clear auth tokens from browser localStorage."""
    js_code = """
    <script>
        localStorage.removeItem('legal_ai_auth');
    </script>
    """
    html(js_code)


def get_auth_from_session_or_query() -> dict | None:
    """
    Get auth from session state or query parameters.
    This is a fallback for when localStorage is not accessible.
    
    Returns:
        Dict with auth data if found in query params or session state
    """
    # Check query parameters first (set after magic link verification)
    query_params = st.query_params
    
    if all(k in query_params for k in ["user_id", "access_token"]):
        return {
            "user_id": query_params.get("user_id"),
            "email": query_params.get("email", ""),
            "access_token": query_params.get("access_token"),
            "refresh_token": query_params.get("refresh_token"),
            "role": query_params.get("role", "viewer"),
            "full_name": query_params.get("full_name"),
            "firm": query_params.get("firm"),
        }
    
    # Check session state
    if st.session_state.get("legal_ai_user_id"):
        return {
            "user_id": st.session_state.get("legal_ai_user_id"),
            "email": st.session_state.get("legal_ai_user_email"),
            "access_token": st.session_state.get("legal_ai_access_token"),
            "refresh_token": st.session_state.get("legal_ai_refresh_token"),
            "role": st.session_state.get("legal_ai_user_role", "viewer"),
            "full_name": st.session_state.get("legal_ai_user_full_name"),
            "firm": st.session_state.get("legal_ai_user_firm"),
        }
    
    return None


def restore_auth_in_session() -> bool:
    """
    Try to restore auth from query parameters (fallback for localStorage).
    Returns True if successfully restored, False otherwise.
    """
    auth_data = get_auth_from_session_or_query()
    
    if auth_data:
        st.session_state.legal_ai_user_id = auth_data["user_id"]
        st.session_state.legal_ai_user_email = auth_data["email"]
        st.session_state.legal_ai_access_token = auth_data["access_token"]
        st.session_state.legal_ai_refresh_token = auth_data["refresh_token"]
        st.session_state.legal_ai_user_role = auth_data["role"]
        st.session_state.legal_ai_user_full_name = auth_data["full_name"]
        st.session_state.legal_ai_user_firm = auth_data["firm"]
        return True
    
    return False
