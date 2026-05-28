"""Browser cookie utilities for persistent session management."""

import json
from urllib.parse import quote, unquote

import streamlit as st
from streamlit.components.v1 import html

from . import jwt_utils


AUTH_COOKIE_NAME = "legal_ai_auth"


def _auth_cookie_max_age_seconds() -> int:
    return jwt_utils.get_refresh_token_expiry_days() * 24 * 60 * 60


def _serialize_auth_data(
    user_id: str,
    email: str,
    access_token: str,
    refresh_token: str,
    role: str,
    full_name: str | None,
    firm: str | None,
) -> str:
    return json.dumps(
        {
            "user_id": user_id,
            "email": email,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "role": role,
            "full_name": full_name,
            "firm": firm,
        },
        separators=(",", ":"),
    )


def _cookie_script(cookie_value: str, max_age_seconds: int) -> str:
    cookie_name = quote(AUTH_COOKIE_NAME, safe="")
    encoded_value = quote(cookie_value, safe="")
    # Write cookie, then broadcast change via localStorage and BroadcastChannel so other tabs update immediately
    return f"""
    <script>
        (function() {{
            try {{
                const cookieName = decodeURIComponent("{cookie_name}");
                const cookieValue = decodeURIComponent("{encoded_value}");
                document.cookie = cookieName + '=' + cookieValue + '; Path=/; Max-Age={max_age_seconds}; SameSite=Lax' + (window.location.protocol === 'https:' ? '; Secure' : '');

                // localStorage-based sync (triggers storage event in other tabs)
                try {{
                    const payload = JSON.stringify({{ type: 'set', value: cookieValue, ts: Date.now() }});
                    localStorage.setItem('legal_ai_auth_sync', payload);
                }} catch (e) {{ /* ignore localStorage errors */ }}

                // BroadcastChannel for modern browsers (optional, but more immediate)
                try {{
                    const bc = new BroadcastChannel('legal_ai_auth');
                    bc.postMessage({{ type: 'set', value: cookieValue, ts: Date.now() }});
                    bc.close();
                }} catch (e) {{ /* ignore BroadcastChannel errors */ }}
            }} catch (e) {{ console.error(e); }}
        }})();
    </script>
    """


def _clear_cookie_script() -> str:
    # Clear cookie and broadcast a clear event so other tabs can react
    return f"""
    <script>
        (function() {{
            try {{
                const cookieName = "{AUTH_COOKIE_NAME}";
                document.cookie = cookieName + '=; Path=/; Max-Age=0; SameSite=Lax' + (window.location.protocol === 'https:' ? '; Secure' : '');

                try {{
                    const payload = JSON.stringify({{ type: 'clear', ts: Date.now() }});
                    localStorage.setItem('legal_ai_auth_sync', payload);
                }} catch (e) {{ /* ignore localStorage errors */ }}

                try {{
                    const bc = new BroadcastChannel('legal_ai_auth');
                    bc.postMessage({{ type: 'clear', ts: Date.now() }});
                    bc.close();
                }} catch (e) {{ /* ignore BroadcastChannel errors */ }}
            }} catch (e) {{ console.error(e); }}
        }})();
    </script>
    """


def get_auth_from_browser() -> dict | None:
    """Read auth tokens from the browser cookie."""
    context = getattr(st, "context", None)
    if context is None:
        return None

    cookies = getattr(context, "cookies", None)
    if not cookies:
        return None

    raw_value = cookies.get(AUTH_COOKIE_NAME)
    if not raw_value:
        return None

    for candidate in (raw_value, unquote(raw_value)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            return data

    return None


def store_auth_in_browser(user_id: str, email: str, access_token: str,
                          refresh_token: str, role: str, full_name: str | None,
                          firm: str | None) -> None:
    """Store auth tokens in a persistent browser cookie."""
    auth_value = _serialize_auth_data(
        user_id=user_id,
        email=email,
        access_token=access_token,
        refresh_token=refresh_token,
        role=role,
        full_name=full_name,
        firm=firm,
    )
    html(_cookie_script(auth_value, _auth_cookie_max_age_seconds()), height=0)


def restore_auth_from_browser() -> dict | None:
    """Restore auth tokens from the browser cookie."""
    return get_auth_from_browser()


def clear_auth_from_browser() -> None:
    """Clear auth tokens from the browser cookie."""
    html(_clear_cookie_script(), height=0)


def get_auth_from_session_or_query() -> dict | None:
    """Get auth from browser cookie, session state, or query parameters."""
    auth_data = get_auth_from_browser()
    if auth_data:
        return auth_data

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

    return None


def restore_auth_in_session() -> bool:
    """Restore auth into Streamlit session state from browser state."""
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


def inject_auth_sync_listener() -> None:
    """Inject a small client-side listener that reloads the page when auth changes occur in other tabs.

    This listens for `storage` events (localStorage) and BroadcastChannel messages. When an
    auth change is observed it performs a `window.location.reload()` so Streamlit re-runs and
    `init_auth()` can restore the updated cookie state.
    """
    script = f"""
    <script>
    (function() {{
        try {{
            window.addEventListener('storage', function(e) {{
                if (!e.key) return;
                if (e.key === 'legal_ai_auth_sync') {{
                    try {{
                        const data = JSON.parse(e.newValue || e.oldValue || null);
                        if (data && (data.type === 'set' || data.type === 'clear')) {{
                            // Reload to let Streamlit re-run and pick up cookie/localStorage changes
                            window.location.reload();
                        }}
                    }} catch (err) {{ /* ignore parse errors */ }}
                }}
            }});

            try {{
                const bc = new BroadcastChannel('legal_ai_auth');
                bc.onmessage = function(ev) {{
                    try {{
                        const data = ev.data;
                        if (data && (data.type === 'set' || data.type === 'clear')) {{
                            window.location.reload();
                        }}
                    }} catch (err) {{ /* ignore */ }}
                }};
            }} catch (e) {{ /* BroadcastChannel not supported */ }}
        }} catch (e) {{ console.error(e); }}
    }})();
    </script>
    """

    try:
        html(script, height=0)
    except Exception:
        # If html injection fails for any reason, fail silently; feature is optional
        pass
