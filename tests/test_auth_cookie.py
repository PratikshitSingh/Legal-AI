import pytest

import app
from legal_ai.auth import auth, browser_storage


class FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class DummySpinner:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RerunCalled(RuntimeError):
    pass


class StopCalled(RuntimeError):
    pass


@pytest.fixture()
def fake_auth_state(monkeypatch):
    session_state = FakeSessionState()
    query_params = {}

    monkeypatch.setattr(auth.st, "session_state", session_state, raising=False)
    monkeypatch.setattr(auth.st, "query_params", query_params, raising=False)
    monkeypatch.setattr(browser_storage.st, "session_state", session_state, raising=False)
    monkeypatch.setattr(browser_storage.st, "query_params", query_params, raising=False)

    return session_state, query_params


def test_set_auth_tokens_does_not_write_query_params(fake_auth_state, monkeypatch):
    session_state, query_params = fake_auth_state
    stored = {}

    monkeypatch.setattr(
        auth.browser_storage,
        "store_auth_in_browser",
        lambda *args, **kwargs: stored.update({"called": True}),
    )

    auth.set_auth_tokens(
        user_id="user-123",
        email="user@example.com",
        access_token="access-token",
        refresh_token="refresh-token",
        role="viewer",
        full_name="User Name",
        firm="Firm",
    )

    assert stored.get("called") is True
    assert session_state["legal_ai_user_id"] == "user-123"
    assert session_state["legal_ai_access_token"] == "access-token"
    assert query_params == {}


def test_init_auth_restores_from_browser_cookie(fake_auth_state, monkeypatch):
    session_state, _query_params = fake_auth_state

    monkeypatch.setattr(
        browser_storage,
        "get_auth_from_browser",
        lambda: {
            "user_id": "user-456",
            "email": "cookie@example.com",
            "access_token": "cookie-access",
            "refresh_token": "cookie-refresh",
            "role": "viewer",
            "full_name": "Cookie User",
            "firm": "Cookie Firm",
        },
    )
    # Cookie payloads are untrusted: restore validates the token signature and
    # loads the role from the DB.
    monkeypatch.setattr(
        browser_storage.jwt_utils,
        "get_user_id_from_token_signature",
        lambda token: "user-456" if token == "cookie-access" else None,
    )
    from legal_ai import db as db_module

    monkeypatch.setattr(
        db_module,
        "get_user_by_id",
        lambda user_id: {
            "user_id": user_id,
            "email": "cookie@example.com",
            "role": "editor",
            "full_name": "Cookie User",
            "firm": "Cookie Firm",
        },
    )

    auth.init_auth()

    assert session_state["legal_ai_user_id"] == "user-456"
    assert session_state["legal_ai_user_email"] == "cookie@example.com"
    assert session_state["legal_ai_access_token"] == "cookie-access"
    assert session_state["legal_ai_user_role"] == "editor"


def test_init_auth_rejects_forged_cookie(fake_auth_state, monkeypatch):
    """A cookie with a tampered token or user_id must NOT sign the user in."""
    session_state, _query_params = fake_auth_state

    monkeypatch.setattr(
        browser_storage,
        "get_auth_from_browser",
        lambda: {
            "user_id": "victim-user",
            "email": "attacker@example.com",
            "access_token": "forged-token",
            "refresh_token": "whatever",
            "role": "admin",  # attacker-chosen role must be ignored
            "full_name": None,
            "firm": None,
        },
    )
    # Signature validation fails for the forged token
    monkeypatch.setattr(
        browser_storage.jwt_utils,
        "get_user_id_from_token_signature",
        lambda token: None,
    )
    cleared = {}
    monkeypatch.setattr(
        browser_storage, "clear_auth_from_browser", lambda: cleared.update({"called": True})
    )

    auth.init_auth()

    assert "legal_ai_user_id" not in session_state
    assert session_state.get("legal_ai_user_role") is None
    assert cleared.get("called") is True


def test_sign_out_clears_browser_cookie(fake_auth_state, monkeypatch):
    session_state, query_params = fake_auth_state
    session_state.update(
        {
            "legal_ai_user_id": "user-789",
            "legal_ai_user_email": "logout@example.com",
            "legal_ai_access_token": "logout-access",
            "legal_ai_refresh_token": "logout-refresh",
            "legal_ai_user_role": "viewer",
        }
    )
    query_params.update({"token": "abc", "email": "logout@example.com"})

    revoked = {}
    cleared = {}

    monkeypatch.setattr(auth.db, "ensure_db", lambda: None)
    monkeypatch.setattr(
        auth.db, "revoke_refresh_tokens", lambda user_id: revoked.update({"user_id": user_id})
    )
    monkeypatch.setattr(
        auth.browser_storage, "clear_auth_from_browser", lambda: cleared.update({"called": True})
    )

    auth.sign_out()

    assert revoked["user_id"] == "user-789"
    assert cleared.get("called") is True
    assert "legal_ai_user_id" not in session_state
    assert query_params == {}
    # The app uses this flag to re-run the browser-side clear on the next
    # stable render and to skip the auto-restore bootstrap for this tab.
    assert session_state.get("_legal_ai_signed_out") is True


def test_init_auth_restores_from_query_param_handoff(fake_auth_state, monkeypatch):
    """The one-time query-param handoff must restore the session server-side.

    This is the restore path that works on hosts whose proxies don't forward
    cookies to the server (Streamlit Community Cloud): tokens arrive as query
    params, the signature is verified, the profile is loaded from the DB, the
    browser payload is re-persisted, and the tokens are cleared from the URL.
    """
    session_state, query_params = fake_auth_state
    query_params.update(
        {
            "user_id": "user-321",
            "email": "handoff@example.com",
            "access_token": "handoff-access",
            "refresh_token": "handoff-refresh",
        }
    )

    # No cookie reaches the server (the Cloud failure mode).
    monkeypatch.setattr(browser_storage, "get_auth_from_browser", lambda: None)
    monkeypatch.setattr(
        browser_storage.jwt_utils,
        "get_user_id_from_token_signature",
        lambda token: "user-321" if token == "handoff-access" else None,
    )
    from legal_ai import db as db_module

    monkeypatch.setattr(
        db_module,
        "get_user_by_id",
        lambda user_id: {
            "user_id": user_id,
            "email": "handoff@example.com",
            "role": "editor",
            "full_name": None,
            "firm": None,
        },
    )
    stored = {}
    monkeypatch.setattr(
        auth.browser_storage,
        "store_auth_in_browser",
        lambda *args, **kwargs: stored.update({"called": True}),
    )

    auth.init_auth()

    assert session_state["legal_ai_user_id"] == "user-321"
    assert session_state["legal_ai_user_role"] == "editor"
    # The handoff re-persists the browser payload and strips the tokens
    # from the URL.
    assert stored.get("called") is True
    assert query_params == {}


def test_magic_link_success_clears_query_params(monkeypatch):
    session_state = FakeSessionState()
    query_params = {"token": "magic-token", "email": "magic@example.com"}

    monkeypatch.setattr(app.st, "session_state", session_state, raising=False)
    monkeypatch.setattr(app.st, "query_params", query_params, raising=False)
    monkeypatch.setattr(
        app,
        "verify_magic_link_token",
        lambda email, token: {
            "status": "success",
            "user_id": "user-999",
            "email": email,
            "access_token": "access-999",
            "refresh_token": "refresh-999",
            "role": "viewer",
            "full_name": None,
            "firm": None,
        },
    )
    monkeypatch.setattr(app, "set_auth_tokens", lambda **kwargs: None)
    monkeypatch.setattr(app, "start_new_chat", lambda user_id: None)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "balloons", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "components_html", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "divider", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "spinner", lambda *args, **kwargs: DummySpinner())
    monkeypatch.setattr(app.st, "stop", lambda: (_ for _ in ()).throw(StopCalled()))

    with pytest.raises(StopCalled):
        app.render_magic_link_verification("magic@example.com", "magic-token")

    assert query_params == {}


def test_magic_link_error_while_already_signed_in_reruns_without_error(monkeypatch):
    session_state = FakeSessionState()
    query_params = {"token": "stale-token", "email": "magic@example.com"}
    captured = {"error_called": False}

    monkeypatch.setattr(app.st, "session_state", session_state, raising=False)
    monkeypatch.setattr(app.st, "query_params", query_params, raising=False)
    monkeypatch.setattr(
        app,
        "verify_magic_link_token",
        lambda email, token: {
            "status": "error",
            "message": "Invalid or expired magic link",
        },
    )
    monkeypatch.setattr(app, "is_signed_in", lambda: True)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "divider", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "spinner", lambda *args, **kwargs: DummySpinner())
    monkeypatch.setattr(
        app.st, "error", lambda *args, **kwargs: captured.update({"error_called": True})
    )
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunCalled()))

    with pytest.raises(RerunCalled):
        app.render_magic_link_verification("magic@example.com", "stale-token")

    assert captured["error_called"] is False
    assert query_params == {}
