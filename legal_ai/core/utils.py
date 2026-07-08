"""Core utilities for article management, embeddings, and tracing."""

import os as OS

from dotenv import load_dotenv

from .config import load_config
from .constants import COLLECTION_NAME, DB_FOLDER

load_dotenv()


def use_chroma_cloud() -> bool:
    """Check if Chroma Cloud is configured."""
    return bool(
        OS.getenv("CHROMA_API_KEY") and OS.getenv("CHROMA_TENANT") and OS.getenv("CHROMA_DATABASE")
    )


def get_chroma_cloud_settings() -> dict[str, str]:
    """Get Chroma Cloud settings from environment."""
    api_key = OS.getenv("CHROMA_API_KEY")
    tenant = OS.getenv("CHROMA_TENANT")
    database = OS.getenv("CHROMA_DATABASE")
    if not api_key or not tenant or not database:
        raise ValueError(
            "Chroma Cloud requires CHROMA_API_KEY, CHROMA_TENANT, and CHROMA_DATABASE in .env"
        )
    return {"api_key": api_key, "tenant": tenant, "database": database}


def get_chroma_client():
    """Return a Chroma Cloud or local persistent client."""
    import chromadb

    if use_chroma_cloud():
        cfg = get_chroma_cloud_settings()
        return chromadb.CloudClient(
            api_key=cfg["api_key"],
            tenant=cfg["tenant"],
            database=cfg["database"],
        )
    return chromadb.PersistentClient(path=DB_FOLDER)


def chroma_collection_has_documents() -> bool:
    """Check if Chroma collection has documents."""
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        return collection.count() > 0
    except Exception:
        return False


def get_gemini_api_key() -> str:
    """Get Gemini API key from environment."""
    config = load_config()
    env_name = config.get("embeddings", {}).get("api_key_env", "GEMINI_API_KEY")
    key = OS.getenv(env_name) or OS.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            f"Set {env_name} in .env (Google AI Studio API key). "
            "Get one at https://aistudio.google.com/apikey"
        )
    OS.environ.setdefault("GEMINI_API_KEY", key)
    OS.environ.setdefault("GOOGLE_API_KEY", key)
    return key


# ============================================================================
# Tracing Utilities
# ============================================================================

# Global tracing state (initialized once at startup)
_langfuse_callback = None
_tracing_enabled = False
_langfuse_host = None
_langfuse_project_name = None
_langfuse_status_message = "Langfuse tracing is not initialized."


def _import_langfuse_callback_handler():
    """Import Langfuse's CallbackHandler from whichever module path is available.

    Langfuse versions have different structures:
    - Older versions (< 2.0): langfuse.callback.CallbackHandler
    - 2.0-4.x: langfuse.callback_handler.CallbackHandler or langfuse.CallbackHandler
    - Newer (4.7+): langfuse.langchain.CallbackHandler
    """
    import importlib

    # Try different import paths for different langfuse versions
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
                print(f"[Tracing] Imported CallbackHandler from {module_name}.{class_name}")
                return handler
        except ImportError:
            continue
        except Exception as e:
            print(f"[Tracing] Error checking {module_name}: {e}")
            continue

    raise ImportError(
        "langfuse is installed but CallbackHandler could not be imported. "
        "Tried paths: langfuse.langchain, langfuse.callback, langfuse.callback_handler, langfuse"
    )


def setup_langfuse_tracing() -> None:
    """Initialize LangFuse tracing for LangChain operations (startup once).

    Best practices implemented:
    - Loads config AFTER env vars are loaded (not during import)
    - Returns callback handler factory for explicit chain integration
    - Supports tags, user context, and data masking
    - Fails gracefully if credentials missing (continues without tracing)
    """
    global \
        _langfuse_callback, \
        _tracing_enabled, \
        _langfuse_host, \
        _langfuse_project_name, \
        _langfuse_status_message

    config = load_config()
    tracing_config = config.get("tracing", {})

    if not tracing_config.get("enabled", False):
        _langfuse_host = None
        _langfuse_project_name = tracing_config.get("project_name", "legal-ai")
        _langfuse_status_message = "Langfuse tracing is disabled in config.yaml."
        print("[Tracing] LangFuse tracing is disabled in config.yaml")
        _tracing_enabled = False
        return

    public_key = OS.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = OS.getenv("LANGFUSE_SECRET_KEY")
    host = OS.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        _langfuse_host = host
        _langfuse_project_name = tracing_config.get("project_name", "legal-ai")
        _langfuse_status_message = (
            "Langfuse tracing is enabled in config, but credentials are missing."
        )
        print(
            "[Tracing] LangFuse enabled but credentials not found. "
            "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env to enable tracing. "
            "Get keys from https://cloud.langfuse.com"
        )
        _tracing_enabled = False
        return

    try:
        CallbackHandler = _import_langfuse_callback_handler()

        project_name = tracing_config.get("project_name", "legal-ai")
        _langfuse_host = host
        _langfuse_project_name = project_name

        # Try new API (langfuse 4.7+): only public_key
        # Fall back to old API if that fails: public_key, secret_key, host
        try:
            _langfuse_callback = CallbackHandler(public_key=public_key)
            print("[Tracing] Using langfuse 4.7+ API (public_key only)")
        except TypeError:
            # Fall back to older API
            _langfuse_callback = CallbackHandler(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            print("[Tracing] Using legacy langfuse API (public_key, secret_key, host)")

        _tracing_enabled = True
        _langfuse_status_message = (
            f"Langfuse tracing enabled · Host: {host} · Project: {project_name}"
        )
        print(f"[Tracing] {_langfuse_status_message}")
    except ImportError as e:
        _langfuse_host = host
        _langfuse_project_name = tracing_config.get("project_name", "legal-ai")
        error_msg = str(e)

        _langfuse_status_message = f"Langfuse import failed: {error_msg}"
        print(f"[Tracing] ERROR: {error_msg}")
        _tracing_enabled = False
    except Exception as e:
        _langfuse_host = host
        _langfuse_project_name = tracing_config.get("project_name", "legal-ai")
        _langfuse_status_message = f"Langfuse tracing failed to initialize: {e}"
        print(f"[Tracing] ERROR initializing LangFuse: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        _tracing_enabled = False


def get_langfuse_tracing_status() -> dict:
    """Return the current Langfuse tracing state for UI and diagnostics."""
    return {
        "enabled": _tracing_enabled and _langfuse_callback is not None,
        "configured": _langfuse_callback is not None,
        "host": _langfuse_host,
        "project_name": _langfuse_project_name,
        "message": _langfuse_status_message,
    }


def get_langfuse_callback(
    trace_name: str = "legal-query",
    user_id: str = None,
    session_id: str = None,
    tags: list[str] = None,
) -> list:
    """Get LangFuse callback handler(s) for passing to LangChain chains.

    Best practice: Pass callbacks explicitly to chains instead of using globals.
    Supports adding user context, session tracking, and tags for filtering.

    Args:
        trace_name: Descriptive name for this trace (e.g., 'contract-analysis')
        user_id: User identifier for audit trails
        session_id: Session identifier for grouping interactions
        tags: List of tags (e.g., ['eu-ai-act', 'question-answering'])

    Returns:
        List of callbacks (empty if tracing disabled or not initialized)

    Example:
        callbacks = get_langfuse_callback(
            trace_name='rag-retrieval',
            user_id=user.id,
            session_id=session_id,
            tags=['document-processing', 'retrieval']
        )
        result = chain.invoke(input, config={'callbacks': callbacks})
    """
    if not _tracing_enabled or _langfuse_callback is None:
        return []

    try:
        # Create a new handler with context for this specific trace
        import os as os_module

        CallbackHandler = _import_langfuse_callback_handler()

        try:
            # Legacy API (langfuse < 3): handler takes credentials + trace context
            handler = CallbackHandler(
                public_key=os_module.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os_module.getenv("LANGFUSE_SECRET_KEY"),
                host=os_module.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
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
                handler = CallbackHandler(public_key=os_module.getenv("LANGFUSE_PUBLIC_KEY"))
            except TypeError:
                handler = CallbackHandler()

        return [handler]
    except Exception as e:
        print(f"[Tracing] Failed to create callback handler: {e}")
        return []


def flush_langfuse_traces() -> None:
    """Flush pending traces to LangFuse backend.

    Best practice: Call this before script exit to ensure all traces are sent.
    Important for batch processing, embed.py, and other non-server processes.
    """
    if not _tracing_enabled or _langfuse_callback is None:
        return

    try:
        _langfuse_callback.flush()
        print("[Tracing] Traces flushed to LangFuse")
    except Exception as e:
        print(f"[Tracing] Failed to flush traces: {e}")
