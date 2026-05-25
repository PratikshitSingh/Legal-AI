#!/usr/bin/env python3
"""Test SendGrid API configuration."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 70)
print("Testing SendGrid Configuration")
print("=" * 70)

# Check environment variables
print("\n✓ Checking environment variables...")
api_key = os.environ.get("SENDGRID_API_KEY")
email_from = os.environ.get("EMAIL_FROM")

if not api_key:
    print("  ✗ SENDGRID_API_KEY not found in .env")
    sys.exit(1)
else:
    # Show masked key
    masked = api_key[:10] + "..." + api_key[-5:]
    print(f"  ✓ SENDGRID_API_KEY found: {masked}")

if not email_from:
    print("  ⚠ EMAIL_FROM not found in .env, using default")
    email_from = "noreply@legal-ai.app"
else:
    print(f"  ✓ EMAIL_FROM: {email_from}")

# Test SendGrid connection
print("\n✓ Testing SendGrid API connection...")

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    
    # Create test email
    message = Mail(
        from_email=email_from,
        to_emails="test@example.com",
        subject="Test Email from Legal AI",
        html_content="<strong>This is a test email from SendGrid!</strong>"
    )
    
    # Send via SendGrid
    sg = SendGridAPIClient(api_key)
    response = sg.send(message)
    
    if response.status_code in [202, 201]:
        print(f"  ✓ Email sent successfully! Status: {response.status_code}")
        print(f"  ✓ To: test@example.com")
        print(f"  ✓ From: {email_from}")
        print("\n✅ SendGrid API is working correctly!")
        sys.exit(0)
    else:
        print(f"  ✗ Unexpected status code: {response.status_code}")
        print(f"  Response: {response.body}")
        sys.exit(1)

except Exception as e:
    error_msg = str(e)
    print(f"  ✗ Error: {error_msg}")
    
    if "Unauthorized" in error_msg or "401" in error_msg:
        print("\n  💡 Fix: Your SENDGRID_API_KEY might be invalid or expired")
        print("     Get a new key from: https://app.sendgrid.com/settings/api_keys")
    elif "Permission" in error_msg or "403" in error_msg:
        print("\n  💡 Fix: Your API key doesn't have 'Mail Send' permission")
        print("     Create a new key with restricted access to 'Mail Send'")
    elif "Email address not verified" in error_msg or "from_email" in error_msg:
        print(f"\n  💡 Fix: The email '{email_from}' is not verified in SendGrid")
        print("     Verify it at: https://app.sendgrid.com/settings/sender_auth/senders")
    
    sys.exit(1)
