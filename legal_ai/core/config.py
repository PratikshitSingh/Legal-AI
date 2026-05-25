"""Configuration management."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from .constants import CONFIG_FILE, ROOT


def load_config() -> dict:
    """Load configuration from config.yaml."""
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_app_base_url() -> str:
    """Get the app base URL from config.yaml or environment variable.
    
    Priority:
    1. APP_BASE_URL environment variable (for overrides)
    2. config.yaml app.base_url
    3. Fallback to localhost:8501
    """
    config = load_config()
    app_url = os.getenv("APP_BASE_URL") or config.get("app", {}).get("base_url")
    if not app_url:
        app_url = "http://localhost:8501"
    return app_url.rstrip("/")  # Remove trailing slash for consistency
