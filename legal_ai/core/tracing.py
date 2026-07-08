"""Langfuse tracing: one-time setup, status, and per-trace callback plumbing."""

import importlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from . import settings

logger = logging.getLogger(__name__)


@dataclass
class _TracingState:
    """Process-wide tracing state, initialized once at startup."""

    callback: Any = None
    enabled: bool = False
    host: str | None = None
    project_name: str | None = None
    status_message: str = field(default="Langfuse tracing is not initialized.")


_state = _TracingState()


def _reset_for_tests() -> None:
    """Reset tracing to its uninitialized state (test isolation hook)."""
    global _state
    _state = _TracingState()


def _import_langfuse_callback_handler():
    """Import Langfuse's CallbackHandler from whichever module path is available.

    Langfuse moved this class across releases:
    - Older versions (< 2.0): langfuse.callback.CallbackHandler
    - 2.0-4.x: langfuse.callback_handler.CallbackHandler or langfuse.CallbackHandler
    - Newer (4.7+): langfuse.langchain.CallbackHandler

    The dependency is pinned now, but the fallback chain stays as cheap
    insurance for future bumps.
    """
    paths_to_try = [
        ("langfuse.langchain", "CallbackHandler"),  # 4.7+ LangChain integration
        ("langfuse.callback", "CallbackHandler"),  # Older versions
        ("langfuse.callback_handler", "CallbackHandler"),  # Mid versions
        ("langfuse", "CallbackHandler"),  # Some versions expose it at top level
    ]

    for module_name, class_name in paths_to_try:
        try:
            module = importlib.import_module(module_name)
            handler = getattr(module, class_name, None)
            if handler is not None:
                logger.debug("Imported CallbackHandler from %s.%s", module_name, class_name)
                return handler
        except ImportError:
            continue
        except Exception as e:
            logger.warning("Error checking %s for CallbackHandler: %s", module_name, e)
            continue

    raise ImportError(
        "langfuse is installed but CallbackHandler could not be imported. "
        "Tried paths: langfuse.langchain, langfuse.callback, langfuse.callback_handler, langfuse"
    )


def setup_langfuse_tracing() -> None:
    """Initialize Langfuse tracing for LangChain operations (startup, once).

    Fails gracefully: missing config or credentials disable tracing and the
    app continues without it.
    """
    config = settings.load_config()
    tracing_config = config.get("tracing", {})
    project_name = tracing_config.get("project_name", "legal-ai")

    if not tracing_config.get("enabled", False):
        _state.host = None
        _state.project_name = project_name
        _state.status_message = "Langfuse tracing is disabled in config.yaml."
        _state.enabled = False
        logger.info("Langfuse tracing is disabled in config.yaml")
        return

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    _state.host = host
    _state.project_name = project_name

    if not public_key or not secret_key:
        _state.status_message = "Langfuse tracing is enabled in config, but credentials are missing."
        _state.enabled = False
        logger.warning(
            "Langfuse enabled but credentials not found. Set LANGFUSE_PUBLIC_KEY and "
            "LANGFUSE_SECRET_KEY in .env to enable tracing (keys: https://cloud.langfuse.com)"
        )
        return

    try:
        CallbackHandler = _import_langfuse_callback_handler()

        # Try the new API (langfuse 4.7+): public_key only; fall back to the
        # old signature (public_key, secret_key, host) on TypeError.
        try:
            _state.callback = CallbackHandler(public_key=public_key)
            logger.debug("Using langfuse 4.7+ API (public_key only)")
        except TypeError:
            _state.callback = CallbackHandler(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            logger.debug("Using legacy langfuse API (public_key, secret_key, host)")

        _state.enabled = True
        _state.status_message = f"Langfuse tracing enabled · Host: {host} · Project: {project_name}"
        logger.info(_state.status_message)
    except ImportError as e:
        _state.status_message = f"Langfuse import failed: {e}"
        _state.enabled = False
        logger.error("Langfuse import failed: %s", e)
    except Exception as e:
        _state.status_message = f"Langfuse tracing failed to initialize: {e}"
        _state.enabled = False
        logger.exception("Error initializing Langfuse")


def get_langfuse_tracing_status() -> dict:
    """Return the current Langfuse tracing state for UI and diagnostics."""
    return {
        "enabled": _state.enabled and _state.callback is not None,
        "configured": _state.callback is not None,
        "host": _state.host,
        "project_name": _state.project_name,
        "message": _state.status_message,
    }


def get_langfuse_callback(
    trace_name: str = "legal-query",
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> list:
    """Get Langfuse callback handler(s) to pass to a LangChain chain.

    Args:
        trace_name: Descriptive name for this trace (e.g., 'contract-analysis')
        user_id: User identifier for audit trails
        session_id: Session identifier for grouping interactions
        tags: List of tags (e.g., ['eu-ai-act', 'question-answering'])

    Returns:
        List of callbacks (empty if tracing is disabled or not initialized)
    """
    if not _state.enabled or _state.callback is None:
        return []

    try:
        CallbackHandler = _import_langfuse_callback_handler()

        try:
            # Legacy API (langfuse < 3): handler takes credentials + trace context
            handler = CallbackHandler(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                session_id=session_id,
                user_id=user_id,
                trace_name=trace_name,
                tags=tags or [],
            )
        except TypeError:
            # New API (langfuse 3/4.x): handler takes no trace-context kwargs.
            # Credentials come from env vars; session/user/tags are passed via
            # the chain's config metadata (langfuse_session_id etc.) — see
            # LegalChat.ask, which adds them to config["metadata"].
            try:
                handler = CallbackHandler(public_key=os.getenv("LANGFUSE_PUBLIC_KEY"))
            except TypeError:
                handler = CallbackHandler()

        return [handler]
    except Exception as e:
        logger.warning("Failed to create Langfuse callback handler: %s", e)
        return []


def flush_langfuse_traces() -> None:
    """Flush pending traces to the Langfuse backend.

    Call before exit in batch processes (ingest scripts) — they have no
    server lifecycle to flush for them.
    """
    if not _state.enabled or _state.callback is None:
        return

    try:
        _state.callback.flush()
        logger.debug("Traces flushed to Langfuse")
    except Exception as e:
        logger.warning("Failed to flush Langfuse traces: %s", e)
