"""Email service for BaluHost notifications.

Handles sending email notifications via SMTP.
"""

import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Any
from datetime import datetime

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications."""

    def __init__(self):
        """Initialize the email service."""
        self._settings = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the email service with settings.

        Returns:
            True if email is configured and enabled, False otherwise
        """
        settings = get_settings()

        # Check if email is enabled
        email_enabled = getattr(settings, "email_enabled", False)
        if not email_enabled:
            logger.info("[Email] Email notifications disabled")
            return False

        # Check required settings
        smtp_host = getattr(settings, "smtp_host", "")
        if not smtp_host:
            logger.warning("[Email] SMTP host not configured")
            return False

        self._settings = {
            "smtp_host": smtp_host,
            "smtp_port": getattr(settings, "smtp_port", 587),
            "smtp_use_tls": getattr(settings, "smtp_use_tls", True),
            "smtp_username": getattr(settings, "smtp_username", ""),
            "smtp_password": getattr(settings, "smtp_password", ""),
            "from_address": getattr(settings, "email_from_address", "baluhost@example.com"),
            "from_name": getattr(settings, "email_from_name", "BaluHost"),
        }

        self._initialized = True
        logger.info(f"[Email] Initialized with SMTP server: {smtp_host}:{self._settings['smtp_port']}")
        return True

    def is_available(self) -> bool:
        """Check if email service is available.

        Returns:
            True if initialized and configured
        """
        return self._initialized

    async def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)

        Returns:
            dict with success status and message/error
        """
        if not self._initialized:
            return {
                "success": False,
                "error": "Email service not initialized",
            }

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self._settings['from_name']} <{self._settings['from_address']}>"
            msg["To"] = to

            # Attach plain text part
            if text_body:
                part1 = MIMEText(text_body, "plain", "utf-8")
                msg.attach(part1)

            # Attach HTML part
            part2 = MIMEText(html_body, "html", "utf-8")
            msg.attach(part2)

            # Send email
            context = ssl.create_default_context()

            if self._settings["smtp_use_tls"]:
                with smtplib.SMTP(
                    self._settings["smtp_host"],
                    self._settings["smtp_port"]
                ) as server:
                    server.starttls(context=context)
                    if self._settings["smtp_username"]:
                        server.login(
                            self._settings["smtp_username"],
                            self._settings["smtp_password"]
                        )
                    server.sendmail(
                        self._settings["from_address"],
                        to,
                        msg.as_string()
                    )
            else:
                with smtplib.SMTP_SSL(
                    self._settings["smtp_host"],
                    self._settings["smtp_port"],
                    context=context
                ) as server:
                    if self._settings["smtp_username"]:
                        server.login(
                            self._settings["smtp_username"],
                            self._settings["smtp_password"]
                        )
                    server.sendmail(
                        self._settings["from_address"],
                        to,
                        msg.as_string()
                    )

            logger.info(f"[Email] Sent to {to}: {subject}")
            return {"success": True, "message": "Email sent successfully"}

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[Email] Authentication failed: {e}")
            return {"success": False, "error": "SMTP authentication failed"}
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"[Email] Recipient refused: {e}")
            return {"success": False, "error": f"Recipient refused: {to}"}
        except Exception as e:
            logger.error(f"[Email] Failed to send: {e}")
            return {"success": False, "error": str(e)}

    async def send_notification_email(
        self,
        user: Any,
        notification: Any,
    ) -> dict[str, Any]:
        """Send a notification email to a user.

        Args:
            user: User object with email attribute
            notification: Notification object

        Returns:
            dict with success status
        """
        if not user.email:
            return {"success": False, "error": "User has no email address"}

        # Map notification types to colors
        type_colors = {
            "info": "#3b82f6",      # blue-500
            "warning": "#f59e0b",   # amber-500
            "critical": "#ef4444",  # red-500
        }

        # Map categories to icons (using emoji as fallback)
        category_icons = {
            "raid": "💾",
            "smart": "🔧",
            "backup": "📦",
            "scheduler": "⏰",
            "system": "🖥️",
            "security": "🔒",
            "sync": "🔄",
            "vpn": "🔐",
        }

        color = type_colors.get(notification.notification_type, "#6b7280")
        icon = category_icons.get(notification.category, "🔔")

        # Build HTML email
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <!-- Header -->
        <div style="background-color: #0f172a; padding: 24px; text-align: center;">
            <h1 style="color: #38bdf8; margin: 0; font-size: 24px;">BaluHost</h1>
        </div>

        <!-- Content -->
        <div style="padding: 24px;">
            <!-- Type indicator -->
            <div style="display: inline-block; background-color: {color}; color: white; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 16px;">
                {notification.notification_type}
            </div>

            <!-- Title -->
            <h2 style="color: #1f2937; margin: 0 0 12px 0; font-size: 20px;">
                {icon} {notification.title}
            </h2>

            <!-- Message -->
            <p style="color: #4b5563; line-height: 1.6; margin: 0 0 24px 0;">
                {notification.message}
            </p>

            <!-- Action button -->
            {f'''
            <a href="{notification.action_url}" style="display: inline-block; background-color: #38bdf8; color: #0f172a; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600;">
                Details anzeigen
            </a>
            ''' if notification.action_url else ''}

            <!-- Metadata -->
            <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af;">
                <p style="margin: 0;">Kategorie: {notification.category.upper()}</p>
                <p style="margin: 4px 0 0 0;">Zeitpunkt: {notification.created_at.strftime('%d.%m.%Y %H:%M') if notification.created_at else 'Unbekannt'}</p>
            </div>
        </div>

        <!-- Footer -->
        <div style="background-color: #f9fafb; padding: 16px 24px; text-align: center; font-size: 12px; color: #6b7280;">
            <p style="margin: 0;">Diese E-Mail wurde automatisch von BaluHost generiert.</p>
            <p style="margin: 8px 0 0 0;">
                Du kannst deine Benachrichtigungseinstellungen in den
                <a href="#" style="color: #38bdf8;">Einstellungen</a> anpassen.
            </p>
        </div>
    </div>
</body>
</html>
"""

        # Plain text version
        text_body = f"""
BaluHost Benachrichtigung

{notification.notification_type.upper()}: {notification.title}

{notification.message}

Kategorie: {notification.category}
Zeitpunkt: {notification.created_at.strftime('%d.%m.%Y %H:%M') if notification.created_at else 'Unbekannt'}

---
Diese E-Mail wurde automatisch von BaluHost generiert.
"""

        return await self.send(
            to=user.email,
            subject=f"[BaluHost] {notification.title}",
            html_body=html_body,
            text_body=text_body,
        )

    async def send_test_email(self, to: str) -> dict[str, Any]:
        """Send a test email to verify configuration.

        Args:
            to: Recipient email address

        Returns:
            dict with success status
        """
        html_body = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 24px; border-radius: 8px;">
        <h1 style="color: #0f172a; margin-top: 0;">BaluHost E-Mail Test</h1>
        <p style="color: #475569;">
            Dies ist eine Test-E-Mail von BaluHost, um die E-Mail-Konfiguration zu überprüfen.
        </p>
        <p style="color: #475569;">
            Wenn du diese E-Mail erhalten hast, ist die SMTP-Konfiguration korrekt eingerichtet.
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
        <p style="color: #94a3b8; font-size: 12px;">
            Gesendet am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
        </p>
    </div>
</body>
</html>
""".format(datetime=datetime)

        return await self.send(
            to=to,
            subject="[BaluHost] E-Mail Test",
            html_body=html_body,
            text_body="BaluHost E-Mail Test\n\nDies ist eine Test-E-Mail von BaluHost.",
        )


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton.

    Returns:
        EmailService instance
    """
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


def init_email_service() -> EmailService:
    """Initialize the email service.

    Should be called during application startup.

    Returns:
        EmailService instance
    """
    service = get_email_service()
    service.initialize()

    # Connect to notification service
    if service.is_available():
        from app.services.notification_service import get_notification_service
        notification_service = get_notification_service()
        notification_service.set_email_service(service)
        logger.info("[Email] Connected to notification service")

    return service
