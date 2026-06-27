import asyncio
import logging

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key


async def send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html_content: str | None = None,
) -> None:
    params = {
        "from": f"{settings.mail_from_name} <{settings.mail_from}>",
        "to": [to_email],
        "subject": subject,
        "text": plain_text,
    }
    if html_content:
        params["html"] = html_content

    try:
        # resend SDK is sync — run in thread to avoid blocking event loop
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as exc:
        logger.exception("Failed to send email to %s: %s", to_email, exc)
        raise


async def send_otp_email(
    to_email: str,
    full_name: str,
    otp: str,
) -> None:
    plain_text = f"""Hi {full_name},

Your KartFlow email verification OTP is: {otp}

This OTP is valid for {settings.otp_expire_minutes} minutes.
Do not share this with anyone.

If you did not create a KartFlow account, ignore this email.

- KartFlow Team
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 480px;
             margin: 0 auto; padding: 24px;">
    <h2 style="color: #111;">KartFlow</h2>
    <p>Hi {full_name},</p>
    <p>Your email verification OTP is:</p>
    <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px;
                background: #f4f4f4; padding: 16px 24px; border-radius: 8px;
                text-align: center; margin: 24px 0;">
        {otp}
    </div>
    <p>Valid for <strong>{settings.otp_expire_minutes} minutes</strong>.
       Do not share this with anyone.</p>
    <p style="color: #666; font-size: 13px;">
        If you did not create a KartFlow account, ignore this email.
    </p>
    <p style="color: #999; font-size: 12px; margin-top: 32px;">
        — KartFlow Team
    </p>
</body>
</html>
"""

    await send_email(
        to_email=to_email,
        subject="Verify your email - KartFlow",
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

We received a request to reset your KartFlow password.

Click the link below to set a new password:
{reset_url}

This link expires in {settings.otp_expire_minutes} minutes.
If you did not request this, ignore this email.

- KartFlow Team
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 480px;
             margin: 0 auto; padding: 24px;">
    <h2 style="color: #111;">KartFlow</h2>
    <p>Hi {full_name},</p>
    <p>We received a request to reset your password.</p>
    <a href="{reset_url}"
       style="display: inline-block; margin: 24px 0; padding: 12px 28px;
              background: #111; color: #fff; text-decoration: none;
              border-radius: 6px; font-weight: bold; font-size: 15px;">
        Reset Password
    </a>
    <p style="color: #666; font-size: 13px;">
        This link expires in
        <strong>{settings.otp_expire_minutes} minutes</strong>.<br>
        If you did not request this, ignore this email.
    </p>
    <p style="color: #999; font-size: 12px; margin-top: 32px;">
        — KartFlow Team
    </p>
</body>
</html>
"""

    await send_email(
        to_email=to_email,
        subject="Reset your password - KartFlow",
        plain_text=plain_text,
        html_content=html_content,
    )
