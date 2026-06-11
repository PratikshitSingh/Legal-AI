import pytest

from legal_ai.auth import auth
from legal_ai.auth import browser_storage
import app


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

    monkeypatch.setattr(auth.browser_storage, "store_auth_in_browser", lambda *args, **kwargs: stored.update({"called": True}))

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
        auth.browser_storage,
        "get_auth_from_browser",
        lambda: {
            "user_id": "user-456",
            "email": "cookie@example.com",
            "access_token": "cookie-access",
            "refresh_token": "cookie-refresh",
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

    monkeypatch.setattr(auth, "ensure_db", lambda: None)
    monkeypatch.setattr(auth.db, "revoke_refresh_tokens", lambda user_id: revoked.update({"user_id": user_id}))
    monkeypatch.setattr(auth.browser_storage, "clear_auth_from_browser", lambda: cleared.update({"called": True}))

    auth.sign_out()

    assert revoked["user_id"] == "user-789"
    assert cleared.get("called") is True
    assert "legal_ai_user_id" not in session_state
    assert query_params == {}


def test_magic_link_success_clears_query_params(monkeypatch):
    session_state = FakeSessionState()
    query_params = {"token": "magic-token", "email": "magic@example.com"}

    monkeypatch.setattr(app.ST, "session_state", session_state, raising=False)
    monkeypatch.setattr(app.ST, "query_params", query_params, raising=False)
    monkeypatch.setattr(app, "verify_magic_link_token", lambda email, token: {
        "status": "success",
        "user_id": "user-999",
        "email": email,
        "access_token": "access-999",
        "refresh_token": "refresh-999",
        "role": "viewer",
        "full_name": None,
        "firm": None,
    })
    monkeypatch.setattr(app, "set_auth_tokens", lambda **kwargs: None)
    monkeypatch.setattr(app, "start_new_chat", lambda user_id: None)
    monkeypatch.setattr(app.ST, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "balloons", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "divider", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "spinner", lambda *args, **kwargs: DummySpinner())
    monkeypatch.setattr(app.ST, "stop", lambda: (_ for _ in ()).throw(StopCalled()))

    with pytest.raises(StopCalled):
        app.render_magic_link_verification("magic@example.com", "magic-token")

    assert query_params == {}


def test_magic_link_error_while_already_signed_in_reruns_without_error(monkeypatch):
    session_state = FakeSessionState()
    query_params = {"token": "stale-token", "email": "magic@example.com"}
    captured = {"error_called": False}

    monkeypatch.setattr(app.ST, "session_state", session_state, raising=False)
    monkeypatch.setattr(app.ST, "query_params", query_params, raising=False)
    monkeypatch.setattr(app, "verify_magic_link_token", lambda email, token: {
        "status": "error",
        "message": "Invalid or expired magic link",
    })
    monkeypatch.setattr(app, "is_signed_in", lambda: True)
    monkeypatch.setattr(app.ST, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "divider", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ST, "spinner", lambda *args, **kwargs: DummySpinner())
    monkeypatch.setattr(app.ST, "error", lambda *args, **kwargs: captured.update({"error_called": True}))
    monkeypatch.setattr(app.ST, "rerun", lambda: (_ for _ in ()).throw(RerunCalled()))

    with pytest.raises(RerunCalled):
        app.render_magic_link_verification("magic@example.com", "stale-token")

    assert captured["error_called"] is False
    assert query_params == {}
