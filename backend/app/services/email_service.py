"""
MODULE: Outbound Email (optional).

Sends account-related emails (approved access, password resets) when SMTP
credentials are configured via environment variables. If no SMTP host is
configured - the default in this training environment - every call is a
safe no-op that returns False, and the calling endpoint falls back to
showing the credential once to the approving Admin for manual relay.

This is intentionally NOT a hard dependency: nothing in the system breaks
or blocks if email is not configured.
"""
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings


def is_email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Returns True if the email was handed off to the SMTP server successfully."""
    if not is_email_configured():
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())
        return True
    except Exception:
        # Never let an email failure break the underlying approve/reject workflow.
        return False
