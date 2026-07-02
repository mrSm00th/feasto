import logging
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import aiosmtplib
import certifi

from app.core.config import settings

logger = logging.getLogger("app.email")


async def send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html_content: str | None = None,
) -> None:
    logger.info("Sending email to=%s subject=%r", to_email, subject)

    message = MIMEMultipart("alternative")
    message["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
    message["To"] = to_email
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message["Reply-To"] = settings.mail_from

    message.attach(MIMEText(plain_text, "plain"))
    if html_content:
        message.attach(MIMEText(html_content, "html"))

    tls_context = ssl.create_default_context(cafile=certifi.where())

    smtp_kwargs = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
        "username": settings.smtp_user,
        "password": settings.smtp_password,
        "tls_context": tls_context,
        "timeout": 15,
    }
    if settings.mail_use_tls:
        smtp_kwargs["start_tls"] = True
    else:
        smtp_kwargs["use_tls"] = True

    try:
        response = await aiosmtplib.send(message, **smtp_kwargs)
        logger.info("Email sent to=%s response=%s", to_email, response)
    except aiosmtplib.SMTPAuthenticationError:
        logger.exception("SMTP auth failed for user=%s", settings.smtp_user)
        raise
    except aiosmtplib.SMTPConnectTimeoutError:
        logger.exception(
            "SMTP connection timeout host=%s port=%s",
            settings.smtp_host,
            settings.smtp_port,
        )
        raise
    except aiosmtplib.SMTPException:
        logger.exception("SMTP error sending to=%s", to_email)
        raise
    except Exception:
        logger.exception("Unexpected error sending email to=%s", to_email)
        raise


async def send_otp_email(
    to_email: str,
    full_name: str,
    otp: str,
) -> None:
    plain_text = f"""Hi {full_name},

Your Feasto email verification OTP is: {otp}

This OTP is valid for {settings.otp_expire_minutes} minutes.
Do not share this with anyone.

If you did not create a Feasto account, ignore this email.

- Feasto Team
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #333;">
    <p>Hi {full_name},</p>
    <p>Your Feasto email verification code is:</p>
    <p style="font-size: 24px; font-weight: bold;">{otp}</p>
    <p>This code is valid for {settings.otp_expire_minutes} minutes. Do not share this with anyone.</p>
    <p>If you did not create a Feasto account, you can ignore this email.</p>
    <p>— Feasto Team</p>
</body>
</html>
"""

    await send_email(
        to_email=to_email,
        subject="Verify your email - Feasto",
        plain_text=plain_text,
        html_content=html_content,
    )


async def send_password_reset_email(
    to_email: str,
    full_name: str,
    reset_token: str,
) -> None:
    reset_url = (
        f"{settings.frontend_url}/reset-password"
        f"?token={reset_token}&email={to_email}"
    )

    plain_text = f"""Hi {full_name},

We received a request to reset your Feasto password.

Click the link below to set a new password:
{reset_url}

This link expires in {settings.otp_expire_minutes} minutes.
If you did not request this, ignore this email.

- Feasto Team
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #333;">
    <p>Hi {full_name},</p>
    <p>We received a request to reset your password.</p>
    <p><a href="{reset_url}">Reset your password</a></p>
    <p>This link expires in {settings.otp_expire_minutes} minutes. If you did not request this, ignore this email.</p>
    <p>— Feasto Team</p>
</body>
</html>
"""

    await send_email(
        to_email=to_email,
        subject="Reset your password - Feasto",
        plain_text=plain_text,
        html_content=html_content,
    )
