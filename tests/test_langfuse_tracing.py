import sys
import types

from legal_ai.core import settings, tracing


class FakeCallbackHandler:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.flushed = False
        FakeCallbackHandler.instances.append(self)

    def flush(self):
        self.flushed = True


def _install_fake_langfuse(monkeypatch):
    fake_langfuse = types.ModuleType("langfuse")
    fake_langfuse.CallbackHandler = FakeCallbackHandler

    fake_callback = types.ModuleType("langfuse.callback")
    fake_callback.CallbackHandler = FakeCallbackHandler

    fake_callback_handler = types.ModuleType("langfuse.callback_handler")
    fake_callback_handler.CallbackHandler = FakeCallbackHandler

    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setitem(sys.modules, "langfuse.callback", fake_callback)
    monkeypatch.setitem(sys.modules, "langfuse.callback_handler", fake_callback_handler)


def test_langfuse_tracing_initializes_and_returns_callbacks(monkeypatch):
    _install_fake_langfuse(monkeypatch)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://example.langfuse.local")
    monkeypatch.setattr(
        settings,
        "load_config",
        lambda: {"tracing": {"enabled": True, "project_name": "legal-ai"}},
    )

    tracing._reset_for_tests()
    FakeCallbackHandler.instances.clear()

    tracing.setup_langfuse_tracing()

    assert tracing._state.enabled is True
    assert tracing._state.callback is not None

    status = tracing.get_langfuse_tracing_status()
    assert status["enabled"] is True
    assert status["project_name"] == "legal-ai"
    assert "Langfuse tracing enabled" in status["message"]

    callbacks = tracing.get_langfuse_callback(
        trace_name="legal-rag-query",
        user_id="user-123",
        session_id="session-456",
        tags=["question-answering"],
    )

    assert len(callbacks) == 1
    handler = callbacks[0]
    assert handler.kwargs["trace_name"] == "legal-rag-query"
    assert handler.kwargs["user_id"] == "user-123"
    assert handler.kwargs["session_id"] == "session-456"
    assert handler.kwargs["tags"] == ["question-answering"]

    tracing.flush_langfuse_traces()
    assert tracing._state.callback.flushed is True
