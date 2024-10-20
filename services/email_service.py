from envelope import Envelope
from core.config import settings
import logging
import smtplib

logger = logging.getLogger(__name__)

def send_otp_email(email: str, otp: str):
    subject = 'Your Email Verification OTP'
    message = f'Your OTP for email verification is: {otp}. This OTP is valid for 10 minutes.'

    envelope = Envelope(
        from_addr=(settings.EMAIL_FROM, 'OTP Verification'),
        to_addr=(email, 'User'),
        subject=subject,
        text_body=message
    )

    try:
        envelope.send(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            user=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            tls=settings.SMTP_USE_TLS
        )
        logger.info(f"OTP email sent successfully to {email}")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email to {email}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email to {email}: {str(e)}")
        return False