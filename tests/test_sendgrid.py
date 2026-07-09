#!/usr/bin/env python3
"""Test SendGrid API configuration.

Runnable two ways:
- `python tests/test_sendgrid.py` — interactive script that actually sends a
  test email (requires SENDGRID_API_KEY).
- `pytest` — collected as a normal test; skips when SENDGRID_API_KEY is not
  configured instead of killing the whole test run with sys.exit().
"""

import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

# Live-service test: sends a real email when opted in via env vars below.
pytestmark = pytest.mark.integration


def _send_test_email(verbose: bool = True) -> tuple[bool, str]:
    """Send a test email through SendGrid; returns (success, message)."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    email_from = os.environ.get("EMAIL_FROM") or "noreply@legal-ai.app"

    if not api_key:
        return False, "SENDGRID_API_KEY not found in environment/.env"

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=email_from,
            to_emails="test@example.com",
            subject="Test Email from Legal AI",
            html_content="<strong>This is a test email from SendGrid!</strong>",
        )

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        if response.status_code in (200, 201, 202):
            return True, f"Email sent successfully (status {response.status_code})"
        return False, f"Unexpected status code: {response.status_code}"
    except Exception as e:
        error_msg = str(e)
        hint = ""
        if "Unauthorized" in error_msg or "401" in error_msg:
            hint = " — API key might be invalid or expired"
        elif "Permission" in error_msg or "403" in error_msg:
            hint = " — API key lacks 'Mail Send' permission"
        elif "not verified" in error_msg or "from_email" in error_msg:
            hint = f" — sender '{email_from}' not verified in SendGrid"
        return False, f"Error: {error_msg}{hint}"


def test_sendgrid_send():
    """Pytest entry point: opt-in live test (sends a real email).

    Run with SENDGRID_LIVE_TEST=1 to enable, e.g.:
        SENDGRID_LIVE_TEST=1 pytest tests/test_sendgrid.py
    """
    if os.environ.get("SENDGRID_LIVE_TEST") != "1":
        pytest.skip("Set SENDGRID_LIVE_TEST=1 to run the live SendGrid send test")
    if not os.environ.get("SENDGRID_API_KEY"):
        pytest.skip("SENDGRID_API_KEY not configured; skipping live SendGrid test")

    success, message = _send_test_email()
    assert success, message


if __name__ == "__main__":
    print("=" * 70)
    print("Testing SendGrid Configuration")
    print("=" * 70)

    api_key = os.environ.get("SENDGRID_API_KEY")
    if api_key:
        masked = api_key[:10] + "..." + api_key[-5:]
        print(f"  ✓ SENDGRID_API_KEY found: {masked}")
    else:
        print("  ✗ SENDGRID_API_KEY not found in .env")
        sys.exit(1)

    email_from = os.environ.get("EMAIL_FROM")
    print(f"  EMAIL_FROM: {email_from or 'not set (using default noreply@legal-ai.app)'}")

    success, message = _send_test_email()
    print(("  ✓ " if success else "  ✗ ") + message)
    sys.exit(0 if success else 1)
