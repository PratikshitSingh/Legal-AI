"""Legal AI - Serverless legal document analysis with EU AI Act compliance."""

__version__ = "0.1.0"
__author__ = "pratikshitsinghpanwar@gmail.com"

# Importing settings here guarantees .env is loaded before any module in the
# package reads the environment, regardless of which entry point imported us.
from legal_ai.core import settings as _settings  # noqa: F401
