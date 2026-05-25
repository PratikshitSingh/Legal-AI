"""Email service for sending magic links."""

import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()


class EmailProvider(ABC):
    """Abstract base for email providers."""

    @abstractmethod
    def send(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send email; return True if successful."""
        pass


class SendGridEmailProvider(EmailProvider):
    """SendGrid email provider."""

    def __init__(self):
        self.api_key = os.environ.get("SENDGRID_API_KEY")
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY not set in environment")
        # Import here to avoid hard dependency
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            self.SendGridAPIClient = SendGridAPIClient
            self.Mail = Mail
        except ImportError:
            raise ImportError(
                "SendGrid SDK not installed. Install with: pip install sendgrid"
            )

    def send(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send email via SendGrid."""
        from_email = os.environ.get("EMAIL_FROM", "noreply@legal-ai.app")
        
        try:
            message = self.Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_body,
            )
            sg = self.SendGridAPIClient(self.api_key)
            response = sg.send(message)
            return 200 <= response.status_code < 300
        except Exception as e:
            print(f"SendGrid error: {e}")
            return False


class LocalEmailProvider(EmailProvider):
    """Local/development provider (prints to console)."""

    def send(self, to_email: str, subject: str, html_body: str) -> bool:
        """Print email to console (for development/testing)."""
        print(f"\n{'='*60}")
        print(f"EMAIL TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"{'-'*60}")
        print(html_body)
        print(f"{'='*60}\n")
        return True


def get_email_provider() -> EmailProvider:
    """Get configured email provider."""
    provider_name = os.environ.get("EMAIL_PROVIDER", "sendgrid").lower()

    if provider_name == "local":
        return LocalEmailProvider()
    elif provider_name == "sendgrid":
        return SendGridEmailProvider()
    else:
        raise ValueError(f"Unknown email provider: {provider_name}")


def send_magic_link_email(email: str, magic_link_url: str) -> bool:
    """
    Send magic link email to user.
    
    Args:
        email: User's email address
        magic_link_url: Full URL with magic token (e.g., https://app.com/auth/verify?token=xxx)
    
    Returns:
        True if sent successfully
    """
    subject = "Sign in to Legal AI"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Sign in to Legal AI</h2>
            <p>Click the link below to sign in:</p>
            <p>
                <a href="{magic_link_url}" 
                   style="display: inline-block; padding: 10px 20px; background-color: #007bff; 
                          color: white; text-decoration: none; border-radius: 5px;">
                    Sign In
                </a>
            </p>
            <p style="color: #666; font-size: 12px;">
                Or copy this link: <a href="{magic_link_url}">{magic_link_url}</a>
            </p>
            <p style="color: #999; font-size: 11px; margin-top: 30px;">
                This link expires in 15 minutes.
            </p>
        </body>
    </html>
    """

    provider = get_email_provider()
    return provider.send(email, subject, html_body)
