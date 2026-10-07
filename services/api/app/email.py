"""Outgoing email: console (development), SMTP or Postmark."""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

# Tests can inspect what would have been sent.
outbox: list["Email"] = []


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str


def send(email: Email) -> None:
    settings = get_settings()
    if settings.environment == "test" or settings.email_backend == "console":
        outbox.append(email)
        log.info("Email to %s: %s\n%s", email.to, email.subject, email.text)
        return
    if settings.email_backend == "postmark":
        res = httpx.post(
            "https://api.postmarkapp.com/email",
            headers={
                "X-Postmark-Server-Token": settings.postmark_server_token,
                "Accept": "application/json",
            },
            json={
                "From": settings.email_from,
                "To": email.to,
                "Subject": email.subject,
                "TextBody": email.text,
                "HtmlBody": email.html,
                "MessageStream": "outbound",
            },
            timeout=20,
        )
        res.raise_for_status()
        return
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = email.to
    msg["Subject"] = email.subject
    msg.set_content(email.text)
    msg.add_alternative(email.html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)
