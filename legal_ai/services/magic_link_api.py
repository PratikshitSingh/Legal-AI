"""FastAPI service that verifies magic links, sets the auth cookie, and redirects back to Streamlit."""

import json
import os
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from legal_ai.auth.auth import verify_magic_link_token
from legal_ai.core.config import get_app_base_url

app = FastAPI()


def _get_verify_base_url() -> str:
    """Base URL used in generated magic links."""
    return (os.getenv("MAGIC_VERIFY_BASE_URL") or "http://localhost:8502").rstrip("/")


@app.get("/verify")
def verify(token: str = "", email: str = ""):
    """Validate a magic link token, set a cookie, and redirect to the app."""
    app_base_url = get_app_base_url()

    if not token or not email:
        return RedirectResponse(f"{app_base_url}?verify_error=missing_params")

    result = verify_magic_link_token(email, token)
    if result.get("status") != "success":
        message = urlencode({"msg": result.get("message", "Invalid or expired magic link")})
        return RedirectResponse(f"{app_base_url}?verify_error=1&{message}")

    auth_payload = {
        "user_id": result["user_id"],
        "email": result["email"],
        "access_token": result.get("access_token", ""),
        "refresh_token": result.get("refresh_token", ""),
        "role": result.get("role", "viewer"),
        "full_name": result.get("full_name"),
        "firm": result.get("firm"),
    }

    redirect_params = urlencode(
        {
            "user_id": auth_payload["user_id"],
            "email": auth_payload["email"],
            "access_token": auth_payload["access_token"],
            "refresh_token": auth_payload["refresh_token"],
            "role": auth_payload["role"],
        }
    )

    response = RedirectResponse(f"{app_base_url}?{redirect_params}")
    response.set_cookie(
        key="legal_ai_auth",
        value=json.dumps(auth_payload),
        max_age=30 * 24 * 60 * 60,
        path="/",
        samesite="lax",
    )
    return response


@app.get("/")
def root():
    return HTMLResponse(
        "<html><body><h3>Legal-AI magic link verify service</h3><p>Use /verify?token=...&email=...</p></body></html>"
    )
