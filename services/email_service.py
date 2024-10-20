from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from core.config import settings
import logging

logger = logging.getLogger(__name__)

def send_otp_email(email: str, otp: str):
    subject = 'Your Email Verification OTP'
    message = f'Your OTP for email verification is: {otp}. This OTP is valid for 10 minutes.'

    try:
        logger.debug(f"Creating SendGrid Mail object")
        from_email = Email(email=settings.EMAIL_FROM, name=settings.EMAIL_FROM_NAME)
        to_email = To(email=email)
        content = Content("text/plain", message)
        mail = Mail(from_email, to_email, subject, content)

        logger.debug(f"Sending email via SendGrid")
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(mail)

        if response.status_code == 202:
            logger.info(f"OTP email sent successfully to {email}")
            return True
        else:
            logger.error(f"Failed to send OTP email to {email}. Status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error sending email to {email}: {str(e)}", exc_info=True)
        return False