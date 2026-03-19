# SMTP credentials are set in docker-compose.yml environment section
# Uses Gmail SMTP with App Password authentication

import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str) -> None:
    """
    Send an email via SMTP. Reads credentials from environment variables.

    Environment variables required:
        SMTP_HOST     - SMTP server hostname (e.g. smtp.gmail.com)
        SMTP_PORT     - SMTP server port (e.g. 587 for STARTTLS)
        SMTP_USER     - SMTP login username
        SMTP_PASSWORD - SMTP login password (App Password for Gmail)
        SMTP_FROM     - Sender address shown in the From header

    If SMTP_HOST is not set or sending fails, logs a warning and returns
    without raising — the application continues normally.
    """
    smtp_host = os.environ.get("SMTP_HOST")
    if not smtp_host:
        logger.warning("SMTP_HOST not set — skipping email to %s (subject: %s)", to, subject)
        return

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    # Build the MIME message
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = to
    message.attach(MIMEText(body, "plain"))

    try:
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            start_tls=True,  # STARTTLS on port 587
        )
        logger.info("Email sent to %s (subject: %s)", to, subject)
    except Exception as exc:
        logger.warning("Failed to send email to %s: %s", to, exc)
