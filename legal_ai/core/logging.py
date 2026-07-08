"""Logging configuration for entry points (Streamlit app and CLI scripts)."""

import logging
import os

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure process-wide logging once, at the entry point.

    The level comes from the LOG_LEVEL environment variable unless given
    explicitly. Safe to call repeatedly — ``basicConfig`` is a no-op once
    handlers exist. Also quiets noisy third-party libraries; call this
    before importing modules that pull in transformers.
    """
    resolved = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(level=resolved, format=_LOG_FORMAT)

    # transformers / sentence-transformers log copiously at import and model
    # load; keep them at ERROR so application logs stay readable.
    logging.getLogger("transformers").setLevel(logging.ERROR)
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
