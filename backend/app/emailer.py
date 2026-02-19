# backend/app/emailer.py
"""Email sending utilities.

Production-style behavior:
- Default: send via SMTP (EMAIL_MODE=smtp)
- Dev/Test: allow "console" mode to avoid hard failures when SMTP isn't configured.

This makes local development and automated tests reliable without changing business logic.
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage


EMAIL_MODE = (os.getenv("EMAIL_MODE", "smtp") or "smtp").lower().strip()

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")


def _smtp_send(msg: EmailMessage) -> None:
    """Send an email.

    EMAIL_MODE behavior:
    - smtp (default): requires SMTP_* env vars.
    - console: prints the email to stdout and does not raise.
    """

    if EMAIL_MODE == "console":
        print("\n--- EMAIL (console mode) ---", file=sys.stdout)
        print(f"To: {msg.get('To')}", file=sys.stdout)
        print(f"Subject: {msg.get('Subject')}", file=sys.stdout)
        print("\n" + (msg.get_content() or ""), file=sys.stdout)
        print("--- END EMAIL ---\n", file=sys.stdout)
        return

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        raise RuntimeError(
            "SMTP env vars not configured (SMTP_HOST/SMTP_USER/SMTP_PASS). "
            "For local dev/tests you can set EMAIL_MODE=console."
        )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


def send_verification_email(to_email: str, token: str) -> None:
    verify_url = f"{PUBLIC_BASE_URL}/api/auth/verify/{token}"

    msg = EmailMessage()
    msg["Subject"] = "Verify your email"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        "Please verify your email by clicking this link:\n\n"
        f"{verify_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    _smtp_send(msg)


def send_newsletter_email(to_email: str, newsletter_text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Your demo finance newsletter"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(newsletter_text)
    _smtp_send(msg)
