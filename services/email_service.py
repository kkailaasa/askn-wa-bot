from envelope import Envelope
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from core.config import settings
import logging

logger = logging.getLogger(__name__)

def send_otp_email(email: str, otp: str):
    subject = 'Your Email Verification OTP'
    message = f'Your OTP for email verification is: {otp}. This OTP is valid for 10 minutes.'

    try:
        envelope = (
            Envelope()
            .from_((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM))  # Use a tuple for name and email
            .to(email)
            .subject(subject)
            .text(message)
        )

        # Convert Envelope to SendGrid Mail object
        mail = Mail(
            from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),  # Use a tuple for email and name
            to_emails=envelope.to()[0].address,
            subject=envelope.subject(),
            plain_text_content=envelope.text_body()
        )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(mail)

        if response.status_code == 202:
            logger.info(f"OTP email sent successfully to {email}")
            return True
        else:
            logger.error(f"Failed to send OTP email to {email}. Status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error sending email to {email}: {str(e)}")
        return False