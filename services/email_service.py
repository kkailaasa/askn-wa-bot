from envelope import Envelope
from core.config import settings
import logging

logger = logging.getLogger(__name__)

def send_otp_email(email: str, otp: str):
    subject = 'Your Email Verification OTP'
    message = f'Your OTP for email verification is: {otp}. This OTP is valid for 10 minutes.'

    try:
        envelope = (
            Envelope(message)
            .subject(subject)
            .from_(settings.EMAIL_FROM)
            .to(email)
        )

        envelope.smtp(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            user=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            security="starttls" if settings.SMTP_USE_TLS else None
        ).send()

        logger.info(f"OTP email sent successfully to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {email}: {str(e)}")
        return False