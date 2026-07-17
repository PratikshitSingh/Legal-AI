"""Browser-side session persistence: cookie + localStorage, and their restore.

The auth payload is persisted in two places by the same injected script:
a cookie (readable server-side via ``st.context.cookies`` on hosts that
forward it) and localStorage. localStorage is the restore path for hosts
whose proxies strip cookies from requests to the server (Streamlit
Community Cloud) — it is read back through a tiny bidirectional custom
component, since sandboxed component iframes cannot navigate the page and
cookie headers never arrive.
"""

import json
import logging
from pathlib import Path
from urllib.parse import quote, unquote

import streamlit as st
import streamlit.components.v1 as components
from streamlit.components.v1 import html

from legal_ai.core.constants import SessionKeys

from . import jwt_utils

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = "legal_ai_auth"

# Bidirectional component that returns the localStorage auth payload to
# Python. Declared once at import; rendering it (in restore) costs nothing
# visible (height 0).
_read_browser_auth = components.declare_component(
    "legal_ai_browser_auth",
    path=str(Path(__file__).parent / "_browser_auth_component"),
)


def _inject_html(script: str) -> None:
    """Inject HTML/JS into the page.

    IMPORTANT: `st.html` sanitizes content with DOMPurify and STRIPS <script>
    tags, so scripts injected through it never execute. `components.html`
    renders inside a same-origin iframe where scripts do run; the scripts
    below reach the main page via `window.parent`.
    """
    try:
        html(script, height=0)
    except Exception:
        # components.html is deprecated (slated for removal after 2026-06);
        # fall back to st.iframe on Streamlit versions that removed it.
        st.iframe(script, height=0)


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
                // Component scripts run inside an iframe; write to the parent
                // (main) page so the cookie/localStorage belong to the app page.
                const root = (function() {{
                    try {{ void window.parent.document; return window.parent; }} catch (e) {{ return window; }}
                }})();
                const cookieName = decodeURIComponent("{cookie_name}");
                const cookieValue = decodeURIComponent("{encoded_value}");
                root.document.cookie = cookieName + '=' + encodeURIComponent(cookieValue) + '; Path=/; Max-Age={max_age_seconds}; SameSite=Lax' + (root.location.protocol === 'https:' ? '; Secure' : '');

                // Also persist in localStorage: hosts whose proxies do not
                // forward cookies to the server (Streamlit Community Cloud)
                // restore sessions from it via the reader component.
                try {{
                    root.localStorage.setItem(cookieName, cookieValue);
                }} catch (e) {{ /* ignore localStorage errors */ }}

                // Strip one-time params (?token=&email=) from the URL BEFORE
                // broadcasting: the sync listener reloads the page on the
                // storage event, and a reload that still carries the consumed
                // magic-link token would re-verify it and show a false
                // "Invalid or expired" error. replaceState is not a
                // navigation, so the component sandbox allows it.
                try {{
                    if (root.location.search) {{
                        root.history.replaceState(null, '', root.location.pathname);
                    }}
                }} catch (e) {{ /* ignore history errors */ }}

                // localStorage-based sync (triggers storage event in other tabs)
                try {{
                    const payload = JSON.stringify({{ type: 'set', ts: Date.now() }});
                    root.localStorage.setItem('legal_ai_auth_sync', payload);
                }} catch (e) {{ /* ignore localStorage errors */ }}

                // BroadcastChannel for modern browsers (optional, but more immediate)
                try {{
                    const bc = new BroadcastChannel('legal_ai_auth');
                    bc.postMessage({{ type: 'set', ts: Date.now() }});
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
                const root = (function() {{
                    try {{ void window.parent.document; return window.parent; }} catch (e) {{ return window; }}
                }})();
                const cookieName = "{AUTH_COOKIE_NAME}";
                root.document.cookie = cookieName + '=; Path=/; Max-Age=0; SameSite=Lax' + (root.location.protocol === 'https:' ? '; Secure' : '');

                try {{
                    root.localStorage.removeItem(cookieName);
                }} catch (e) {{ /* ignore localStorage errors */ }}

                try {{
                    const payload = JSON.stringify({{ type: 'clear', ts: Date.now() }});
                    root.localStorage.setItem('legal_ai_auth_sync', payload);
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


def get_auth_from_local_storage() -> dict | None:
    """Read the auth payload from localStorage via the component channel.

    Renders the (invisible) reader component. On the component's first
    appearance in a session this returns None and the value arrives on the
    rerun Streamlit triggers automatically — callers simply see the restore
    succeed one run later.
    """
    try:
        raw = _read_browser_auth(default=None, key="_legal_ai_browser_auth_reader")
    except Exception:
        # No script run context (unit tests) or component machinery
        # unavailable — behave as "nothing stored".
        return None

    if not raw:
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    return data if isinstance(data, dict) else None


def store_auth_in_browser(
    user_id: str,
    email: str,
    access_token: str,
    refresh_token: str,
    role: str,
    full_name: str | None,
    firm: str | None,
) -> None:
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
    _inject_html(_cookie_script(auth_value, _auth_cookie_max_age_seconds()))


def clear_auth_from_browser() -> None:
    """Clear auth tokens from the browser cookie."""
    _inject_html(_clear_cookie_script())


def get_auth_from_session_or_query() -> dict | None:
    """Get auth from cookie, session state, query params, or localStorage."""
    auth_data = get_auth_from_browser()
    if auth_data:
        return auth_data

    if st.session_state.get(SessionKeys.USER_ID):
        return {
            "user_id": st.session_state.get(SessionKeys.USER_ID),
            "email": st.session_state.get(SessionKeys.USER_EMAIL),
            "access_token": st.session_state.get(SessionKeys.ACCESS_TOKEN),
            "refresh_token": st.session_state.get(SessionKeys.REFRESH_TOKEN),
            "role": st.session_state.get(SessionKeys.USER_ROLE, "viewer"),
            "full_name": st.session_state.get(SessionKeys.USER_FULL_NAME),
            "firm": st.session_state.get(SessionKeys.USER_FIRM),
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

    # Last resort: the localStorage payload, delivered via the component
    # channel — the only restore path that works when the host's proxy
    # strips cookies (Streamlit Community Cloud).
    return get_auth_from_local_storage()


def restore_auth_in_session() -> bool:
    """Restore auth into Streamlit session state from browser state.

    SECURITY: cookies and query params are client-controlled, so nothing in
    them can be trusted directly. The access token's signature is verified to
    prove the user_id, and role/profile are loaded from the database — never
    from the client-supplied payload (otherwise anyone could edit their cookie
    or URL to gain the 'admin' role).
    """
    auth_data = get_auth_from_session_or_query()
    if not auth_data:
        return False

    access_token = auth_data.get("access_token") or ""
    token_user_id = jwt_utils.get_user_id_from_token_signature(access_token)
    if not token_user_id or token_user_id != auth_data.get("user_id"):
        # Forged/tampered payload — ignore it and clear the bad cookie.
        clear_auth_from_browser()
        return False

    # Load trusted profile fields (role, name, firm, email) from the DB.
    role = "viewer"
    full_name = auth_data.get("full_name")
    firm = auth_data.get("firm")
    email = auth_data.get("email")
    try:
        from legal_ai import db

        user = db.get_user_by_id(token_user_id)
        if user:
            role = user.get("role", "viewer")
            full_name = user.get("full_name")
            firm = user.get("firm")
            email = user.get("email")
    except Exception as exc:
        # DB unavailable: fall back to least privilege.
        logger.warning("Could not load user profile during restore: %s", exc)

    st.session_state[SessionKeys.USER_ID] = token_user_id
    st.session_state[SessionKeys.USER_EMAIL] = email
    st.session_state[SessionKeys.ACCESS_TOKEN] = access_token
    st.session_state[SessionKeys.REFRESH_TOKEN] = auth_data.get("refresh_token")
    st.session_state[SessionKeys.USER_ROLE] = role
    st.session_state[SessionKeys.USER_FULL_NAME] = full_name
    st.session_state[SessionKeys.USER_FIRM] = firm
    return True


def inject_auth_sync_listener() -> None:
    """Inject a small client-side listener that reloads the page when auth changes occur in other tabs.

    This listens for `storage` events (localStorage) and BroadcastChannel messages. When an
    auth change is observed it performs a `window.location.reload()` so Streamlit re-runs and
    `init_auth()` can restore the updated cookie state.
    """
    script = """
    <script>
    (function() {
        try {
            // Runs inside a component iframe: listen on the parent page's
            // storage and reload the parent so Streamlit re-runs init_auth().
            const root = (function() {
                try { void window.parent.document; return window.parent; } catch (e) { return window; }
            })();

            root.addEventListener('storage', function(e) {
                if (!e.key) return;
                if (e.key === 'legal_ai_auth_sync') {
                    try {
                        const data = JSON.parse(e.newValue || e.oldValue || null);
                        if (data && (data.type === 'set' || data.type === 'clear')) {
                            // Reload to let Streamlit re-run and pick up cookie changes
                            root.location.reload();
                        }
                    } catch (err) { /* ignore parse errors */ }
                }
            });

            try {
                const bc = new BroadcastChannel('legal_ai_auth');
                bc.onmessage = function(ev) {
                    try {
                        const data = ev.data;
                        if (data && (data.type === 'set' || data.type === 'clear')) {
                            root.location.reload();
                        }
                    } catch (err) { /* ignore */ }
                };
            } catch (e) { /* BroadcastChannel not supported */ }
        } catch (e) { console.error(e); }
    })();
    </script>
    """

    try:
        _inject_html(script)
    except Exception:
        # If html injection fails for any reason, fail silently; feature is optional
        pass
