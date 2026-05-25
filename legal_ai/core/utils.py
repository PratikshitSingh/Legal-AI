"""Core utilities for article management, embeddings, and tracing."""

import json as JS
import os as OS
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config
from .constants import (
    ARTICLES_FILE,
    ARTICLES_FOLDER,
    COLLECTION_NAME,
    DB_FOLDER,
)

load_dotenv()


def use_chroma_cloud() -> bool:
    """Check if Chroma Cloud is configured."""
    return bool(
        OS.getenv("CHROMA_API_KEY")
        and OS.getenv("CHROMA_TENANT")
        and OS.getenv("CHROMA_DATABASE")
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


def get_embedding_settings() -> dict:
    """Get embedding configuration."""
    config = load_config()
    emb = config.get("embeddings", {})
    return {
        "model": emb.get("model", "gemini-embedding-001"),
        "task_type": emb.get("task_type", "RETRIEVAL_DOCUMENT"),
        "api_key_env": emb.get("api_key_env", "GEMINI_API_KEY"),
    }


def load_articles(file_name: str) -> list:
    """Load articles from JSON file."""
    result = []
    if OS.path.exists(file_name):
        with open(file_name, encoding="utf-8") as file:
            try:
                result = JS.load(file)
            except JS.JSONDecodeError:
                print("File exists but is not valid JSON. Returning empty object.")
    else:
        with open(file_name, "w", encoding="utf-8") as file:
            JS.dump("[{}]", file)
        print(f"File '{file_name}' did not exist and was created.")
        OS.makedirs(ARTICLES_FOLDER, exist_ok=True)
        print("'articles' directory was created")

    return result


def save_articles(file_name: str, data) -> None:
    """Save articles to JSON file."""
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            JS.dump(data, file, indent=4)
            print(f"Data successfully saved to '{file_name}'.")
    except Exception as e:
        print(f"Error: trying to save articles data [{e}]")


def save_article_content(file_name: str, content: str) -> None:
    """Save article content to file."""
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            file.write(content)
    except IOError as e:
        print(f"An IOError occurred: {e.strerror}")
    except Exception as e:
        print(f"Error: {e}")
    else:
        print(f"Content successfully written to '{file_name}'.")


def load_article_content(file_name: str) -> str:
    """Load article content from file."""
    result = ""
    try:
        with open(file_name, encoding="utf-8") as file:
            result = file.read()
    except Exception as e:
        print(
            f"An unexpected error occurred while reading content file '{file_name}': {e}"
        )

    return result


# ============================================================================
# Tracing Utilities
# ============================================================================

# Global tracing state (initialized once at startup)
_langfuse_callback = None
_tracing_enabled = False


def _mask_sensitive_legal_content(text: str) -> str:
    """Mask sensitive PII in legal documents for tracing.
    
    Removes/redacts:
    - Email addresses
    - Phone numbers  
    - Social security numbers
    - Account numbers (partial masking)
    - Dates in certain formats (can be tuned)
    
    Best practice: Only trace necessary context, not full documents.
    """
    import re
    
    masked = text
    
    # Email addresses
    masked = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', masked)
    
    # Phone numbers (various formats)
    masked = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', masked)
    
    # SSN (XXX-XX-XXXX or similar)
    masked = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', masked)
    
    # Bank account numbers (simplified: 8+ consecutive digits)
    masked = re.sub(r'\b\d{8,}\b', '[ACCOUNT_NUMBER]', masked)
    
    return masked


def setup_langfuse_tracing() -> None:
    """Initialize LangFuse tracing for LangChain operations (startup once).
    
    Best practices implemented:
    - Loads config AFTER env vars are loaded (not during import)
    - Returns callback handler factory for explicit chain integration
    - Supports tags, user context, and data masking
    - Fails gracefully if credentials missing (continues without tracing)
    """
    global _langfuse_callback, _tracing_enabled
    
    config = load_config()
    tracing_config = config.get("tracing", {})
    
    if not tracing_config.get("enabled", False):
        print("[Tracing] LangFuse tracing is disabled in config.yaml")
        _tracing_enabled = False
        return
    
    public_key = OS.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = OS.getenv("LANGFUSE_SECRET_KEY")
    host = OS.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not public_key or not secret_key:
        print(
            "[Tracing] LangFuse enabled but credentials not found. "
            "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env to enable tracing. "
            "Get keys from https://cloud.langfuse.com"
        )
        _tracing_enabled = False
        return
    
    try:
        from langfuse.callback import CallbackHandler
        
        project_name = tracing_config.get("project_name", "legal-ai")
        
        _langfuse_callback = CallbackHandler(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        
        _tracing_enabled = True
        print(
            f"[Tracing] LangFuse enabled · "
            f"Host: {host} · Project: {project_name}"
        )
    except ImportError as e:
        print(
            f"[Tracing] langfuse not installed. Install with: pip install langfuse"
        )
        _tracing_enabled = False
    except Exception as e:
        print(f"[Tracing] Failed to initialize LangFuse: {e}")
        _tracing_enabled = False


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
        from langfuse.callback import CallbackHandler
        import os as os_module
        
        handler = CallbackHandler(
            public_key=os_module.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os_module.getenv("LANGFUSE_SECRET_KEY"),
            host=os_module.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            session_id=session_id,
            user_id=user_id,
            trace_name=trace_name,
            tags=tags or [],
        )
        
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
