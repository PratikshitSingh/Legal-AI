"""Application configuration: environment loading and config.yaml access.

This module owns the single ``load_dotenv()`` call for the package — it is
imported from ``legal_ai/__init__.py``, so importing anything under
``legal_ai`` guarantees ``.env`` values are in the environment.

Secrets (JWT_SECRET, database URL, API keys) stay env-only and are read where
they are consumed, at call time; this module owns the non-secret settings
surface backed by ``config.yaml``.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

import yaml
from dotenv import load_dotenv

from .constants import CONFIG_FILE

load_dotenv()


def load_config() -> dict:
    """Load raw configuration from config.yaml."""
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class Settings:
    """Typed view of config.yaml.

    Every field has a default so constructing settings never raises in
    environments without full configuration (e.g. CI).
    """

    llm_model: str = "gemini-2.5-flash"
    retrieval_top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    """Load, validate, and cache the typed settings."""
    config = load_config()
    llm = config.get("llm") or {}
    retrieval = config.get("retrieval") or {}
    return Settings(
        llm_model=llm.get("model", Settings.llm_model),
        retrieval_top_k=int(retrieval.get("top_k", Settings.retrieval_top_k)),
    )


def get_app_base_url() -> str:
    """Get the app base URL used in magic-link emails.

    Priority:
    1. APP_BASE_URL environment variable (for overrides)
    2. config.yaml app.base_url
    3. Fallback to localhost:8501
    """
    app_url = os.getenv("APP_BASE_URL") or load_config().get("app", {}).get("base_url")
    if not app_url:
        app_url = "http://localhost:8501"
    return app_url.rstrip("/")  # Remove trailing slash for consistency


def get_gemini_api_key() -> str:
    """Get the Google AI Studio API key from the environment.

    Mirrors the key into GOOGLE_API_KEY, which the LangChain Google
    integrations read implicitly.
    """
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Set GEMINI_API_KEY in .env (Google AI Studio API key). "
            "Get one at https://aistudio.google.com/apikey"
        )
    os.environ.setdefault("GOOGLE_API_KEY", key)
    return key
