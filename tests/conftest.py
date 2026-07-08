"""Shared pytest configuration.

Puts the repo root on ``sys.path`` so ``legal_ai`` and ``app`` import without
an editable install (the app deploys uninstalled, run from the repo root),
and provides the JWT secret the auth stack requires.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Real deployments set JWT_SECRET in the environment; tests fall back to a
# throwaway value (32+ bytes so PyJWT does not warn about weak HMAC keys).
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-0123456789abcdef")
