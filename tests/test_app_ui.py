"""UI-level integration tests using Streamlit's AppTest harness.

These run the real app.py script server-side (same code path as
`streamlit run app.py`) and assert on the rendered elements.
DB and vector-store calls are stubbed so the tests run without network access.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_FILE = str(PROJECT_ROOT / "app.py")


def _make_apptest() -> AppTest:
    return AppTest.from_file(APP_FILE, default_timeout=30)


def test_signed_out_shows_sign_in_form(monkeypatch):
    """A fresh visitor (no cookie, no session) must see the sign-in form."""
    from legal_ai.core import tracing

    monkeypatch.setattr(tracing, "setup_langfuse_tracing", lambda: None)
    monkeypatch.setattr(
        tracing,
        "get_langfuse_tracing_status",
        lambda: {"enabled": False, "message": ""},
    )

    at = _make_apptest()
    at.run()

    assert not at.exception, f"App raised: {at.exception}"
    headers = [s.value for s in at.subheader]
    assert "Sign in to Legal AI" in headers
    assert len(at.text_input) >= 1  # email field
    # No chat input rendered while signed out
    assert len(at.chat_input) == 0


def test_signed_in_renders_chat(monkeypatch):
    """With a valid session, the sidebar and chat input must render."""
    from legal_ai.auth import auth, jwt_utils
    from legal_ai.core import tracing
    from legal_ai.db import db
    from legal_ai.services import gateway, vector_store

    user_id = "11111111-1111-1111-1111-111111111111"
    token = jwt_utils.create_access_token(user_id)

    # Stub everything that needs the network
    monkeypatch.setattr(tracing, "setup_langfuse_tracing", lambda: None)
    monkeypatch.setattr(
        tracing,
        "get_langfuse_tracing_status",
        lambda: {"enabled": False, "message": ""},
    )
    monkeypatch.setattr(vector_store, "collection_has_documents", lambda: True)
    monkeypatch.setattr(vector_store, "use_chroma_cloud", lambda: False)
    monkeypatch.setattr(auth, "ensure_db", lambda: None)
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "upsert_session", lambda *a, **k: None)
    monkeypatch.setattr(db, "get_session_messages", lambda sid: [])
    monkeypatch.setattr(db, "get_user_sessions", lambda uid, limit=50: [])
    monkeypatch.setattr(db, "get_jurisdiction_tree", lambda parent_code=None: [])
    monkeypatch.setattr(db, "get_user_jurisdictions", lambda uid: [])
    monkeypatch.setattr(
        db,
        "get_user_by_id",
        lambda uid: {
            "user_id": uid,
            "email": "tester@example.com",
            "role": "viewer",
            "full_name": "Tester",
            "firm": None,
        },
    )
    monkeypatch.setattr(gateway, "route_query", lambda **kw: "stubbed answer")

    at = _make_apptest()
    at.session_state["legal_ai_user_id"] = user_id
    at.session_state["legal_ai_user_email"] = "tester@example.com"
    at.session_state["legal_ai_access_token"] = token
    at.session_state["legal_ai_refresh_token"] = "refresh-token"
    at.session_state["legal_ai_user_role"] = "viewer"
    at.run()

    assert not at.exception, f"App raised: {at.exception}"
    # Sidebar shows account + chat input rendered
    assert len(at.chat_input) == 1
    sidebar_text = " ".join(t.value for t in at.sidebar.text)
    assert "tester@example.com" in sidebar_text


def test_expired_session_signs_out(monkeypatch):
    """If token refresh fails, the app must warn and sign the user out."""
    from legal_ai.auth import auth
    from legal_ai.core import tracing
    from legal_ai.db import db

    monkeypatch.setattr(tracing, "setup_langfuse_tracing", lambda: None)
    monkeypatch.setattr(
        tracing,
        "get_langfuse_tracing_status",
        lambda: {"enabled": False, "message": ""},
    )
    monkeypatch.setattr(auth, "ensure_db", lambda: None)
    monkeypatch.setattr(db, "revoke_refresh_tokens", lambda uid: None)
    # Any junk token fails validation -> refresh path -> DB says invalid
    monkeypatch.setattr(db, "validate_refresh_token", lambda uid, tok: False)

    at = _make_apptest()
    at.session_state["legal_ai_user_id"] = "22222222-2222-2222-2222-222222222222"
    at.session_state["legal_ai_user_email"] = "expired@example.com"
    at.session_state["legal_ai_access_token"] = "not-a-valid-jwt"
    at.session_state["legal_ai_refresh_token"] = "stale"
    at.session_state["legal_ai_user_role"] = "viewer"
    at.run()

    assert not at.exception, f"App raised: {at.exception}"
    # The failed refresh signs the user out and reruns, landing on sign-in.
    assert "legal_ai_user_id" not in at.session_state
    headers = [s.value for s in at.subheader]
    assert "Sign in to Legal AI" in headers
    assert len(at.chat_input) == 0


def test_magic_link_invalid_token_shows_error(monkeypatch):
    """Visiting with a bad magic link shows an error, not a crash."""
    from legal_ai.auth import auth
    from legal_ai.core import tracing

    monkeypatch.setattr(tracing, "setup_langfuse_tracing", lambda: None)
    monkeypatch.setattr(
        tracing,
        "get_langfuse_tracing_status",
        lambda: {"enabled": False, "message": ""},
    )
    monkeypatch.setattr(auth, "ensure_db", lambda: None)
    monkeypatch.setattr(auth.db, "validate_magic_link", lambda email, token: False)

    at = _make_apptest()
    at.query_params["token"] = "bogus-token"
    at.query_params["email"] = "someone@example.com"
    at.run()

    assert not at.exception, f"App raised: {at.exception}"
    errors = [e.value for e in at.error]
    assert any("Invalid or expired" in e for e in errors)
