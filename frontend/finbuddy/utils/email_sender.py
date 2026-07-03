"""
Email Sender Utility

Sends verification emails for signup using SMTP with SSL.
Configuration via environment variables:
- SMTP_SERVER: SMTP server hostname
- SMTP_PORT: SMTP port (465 for SSL)
- SMTP_USERNAME: SMTP username/email
- SMTP_PASSWORD: SMTP password
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_verification_email(to_email: str, verification_code: str) -> tuple[bool, str]:
    """
    Send a verification code email to the user.

    Args:
        to_email: Recipient email address
        verification_code: 6-digit verification code

    Returns:
        Tuple of (success: bool, error_message: str)
        On success: (True, "")
        On failure: (False, "error description")
    """
    # Get SMTP configuration from environment
    smtp_server = os.getenv("SMTP_SERVER", "smtpout.secureserver.net")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_username = os.getenv("SMTP_USERNAME", "contact@finbuddygroup.com")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not smtp_password:
        print("[email_sender] ERROR: SMTP_PASSWORD not configured", flush=True)
        return False, "Email service not configured"

    # Build the email
    sender_email = smtp_username
    subject = "FinBuddy - Verify Your Email"

    # HTML email body
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .code {{ font-size: 32px; font-weight: bold; color: #2563eb; letter-spacing: 8px; text-align: center; padding: 20px; background-color: white; border-radius: 8px; margin: 20px 0; }}
            .footer {{ text-align: center; color: #64748b; font-size: 12px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>FinBuddy</h1>
            </div>
            <div class="content">
                <h2>Verify Your Email</h2>
                <p>Thank you for signing up! Please use the following verification code to complete your registration:</p>
                <div class="code">{verification_code}</div>
                <p>This code will expire in <strong>15 minutes</strong>.</p>
                <p>If you didn't request this code, please ignore this email.</p>
            </div>
            <div class="footer">
                <p>&copy; 2025 FinBuddy Group. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Plain text fallback
    text_body = f"""
FinBuddy - Email Verification

Your verification code is: {verification_code}

This code will expire in 15 minutes.

If you didn't request this code, please ignore this email.

- FinBuddy Team
    """

    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"FinBuddy <{sender_email}>"
        message["To"] = to_email

        # Attach both plain text and HTML versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        message.attach(part1)
        message.attach(part2)

        # Create SSL context and send
        context = ssl.create_default_context()

        print(f"[email_sender] Connecting to {smtp_server}:{smtp_port}...", flush=True)

        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, to_email, message.as_string())

        print(f"[email_sender] Verification email sent to {to_email}", flush=True)
        return True, ""

    except smtplib.SMTPAuthenticationError as e:
        error_code = e.smtp_code if hasattr(e, 'smtp_code') else 'unknown'
        error_msg = e.smtp_error if hasattr(e, 'smtp_error') else str(e)
        print(f"[email_sender] Authentication error (code {error_code}): {error_msg}", flush=True)
        # 535 can be temporary rate limiting or actual auth failure
        if error_code == 535:
            return False, "Email service temporarily unavailable. Please try again in a few minutes."
        return False, "Email authentication failed"
    except smtplib.SMTPRecipientsRefused as e:
        print(f"[email_sender] Recipient refused: {e}", flush=True)
        return False, "Invalid email address"
    except smtplib.SMTPException as e:
        print(f"[email_sender] SMTP error: {e}", flush=True)
        return False, "Failed to send email"
    except Exception as e:
        print(f"[email_sender] Unexpected error: {e}", flush=True)
        return False, "Email service error"


def validate_email_format(email: str) -> bool:
    """
    Basic email format validation using regex.

    Args:
        email: Email address to validate

    Returns:
        True if email format is valid, False otherwise
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
