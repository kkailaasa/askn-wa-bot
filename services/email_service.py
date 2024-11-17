# services/email_service.py

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent
from core.config import settings
import structlog
from datetime import datetime
import os
from pathlib import Path
from typing import Dict, Any, Optional
import json
import asyncio
from utils.redis_helpers import AsyncRedisLock, AsyncCache
from core.sequence_errors import SequenceException, SequenceErrorCode
import aiofiles
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

logger = structlog.get_logger(__name__)

class EmailService:
    """Enhanced email service with improved error handling and features"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmailService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.project_root = self._get_project_root()
        self.template_dir = os.path.join(self.project_root, "templates")
        self.cache = AsyncCache(prefix="email:")

        try:
            self.sg_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
            logger.info("sendgrid_client_initialized")
        except Exception as e:
            logger.error("sendgrid_init_failed", error=str(e))
            raise

        # Ensure template directory exists
        os.makedirs(self.template_dir, exist_ok=True)
        logger.debug("email_service_initialized", template_dir=self.template_dir)
        self._initialized = True

    def _get_project_root(self) -> str:
        """Get project root directory"""
        return str(Path(__file__).resolve().parent.parent)

    async def initialize_templates(self) -> None:
        """Initialize email templates"""
        try:
            template_path = os.path.join(self.template_dir, 'email_template.html')
            if not os.path.exists(template_path):
                logger.info("creating_email_template", path=template_path)

                default_template = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Verification</title>
    <style>
        .email-container {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            font-family: Arial, sans-serif;
        }
        .header {
            text-align: center;
            padding: 20px;
            background-color: #f8f9fa;
        }
        .content {
            padding: 20px;
            background-color: white;
        }
        .otp-container {
            text-align: center;
            padding: 20px;
            margin: 20px 0;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        .otp-code {
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
            letter-spacing: 2px;
        }
        .instructions {
            margin: 20px 0;
        }
        .footer {
            text-align: center;
            padding: 20px;
            font-size: 12px;
            color: #6c757d;
        }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>Email Verification</h1>
        </div>

        <div class="content">
            <p>Hello!</p>
            <p>Thank you for signing up. To complete your registration, please use the following verification code:</p>

            <div class="otp-container">
                <div class="otp-code">{{ otp_code }}</div>
                <p>Code expires in {{ expiry_minutes }} minutes</p>
            </div>

            <div class="instructions">
                <h2>Instructions:</h2>
                <ul>
                    <li>Enter this code in the verification window</li>
                    <li>Don't share this code with anyone</li>
                    <li>The code is valid for {{ expiry_minutes }} minutes only</li>
                </ul>
            </div>

            <p>If you didn't request this verification code, please ignore this email.</p>
        </div>

        <div class="footer">
            <p>This is an automated message, please do not reply to this email.</p>
            <p>&copy; {{ current_year }} Your Company</p>
        </div>
    </div>
</body>
</html>'''

                os.makedirs(self.template_dir, exist_ok=True)
                async with aiofiles.open(template_path, 'w') as f:
                    await f.write(default_template)

                logger.info("email_template_created")

        except Exception as e:
            logger.error(
                "template_initialization_failed",
                error=str(e)
            )
            raise

    def _validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    async def send_otp_email(
        self,
        email: str,
        otp: str,
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """Send OTP email with enhanced error handling and tracking"""
        if not self._validate_email(email):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_EMAIL,
                message="Invalid email format"
            )

        template_path = os.path.join(self.template_dir, 'email_template.html')
        if not os.path.exists(template_path):
            await self.initialize_templates()

        try:
            # Read template
            async with aiofiles.open(template_path, 'r') as f:
                template_content = await f.read()

            # Replace placeholders
            current_year = datetime.utcnow().year
            html_content = template_content.replace('{{ otp_code }}', otp)\
                                        .replace('{{ expiry_minutes }}', '10')\
                                        .replace('{{ current_year }}', str(current_year))

            message = Mail(
                from_email=Email(
                    email=settings.EMAIL_FROM,
                    name=settings.EMAIL_FROM_NAME
                ),
                to_emails=To(email=email),
                subject='Your Email Verification Code',
                html_content=HtmlContent(html_content)
            )

            # Add plain text version
            message.add_content(
                Content(
                    "text/plain",
                    f"Your verification code is: {otp}\n\n"
                    "This code will expire in 10 minutes.\n\n"
                    "If you didn't request this code, please ignore this email."
                )
            )

            # Send with retries
            for attempt in range(retry_count):
                try:
                    response = await asyncio.to_thread(
                        self.sg_client.send,
                        message
                    )

                    if response.status_code == 202:
                        logger.info(
                            "otp_email_sent",
                            email=email,
                            message_id=response.headers.get('X-Message-Id')
                        )
                        return {
                            'success': True,
                            'message_id': response.headers.get('X-Message-Id')
                        }

                except Exception as e:
                    if attempt == retry_count - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

            raise SequenceException(
                error_code=SequenceErrorCode.EMAIL_ERROR,
                message="Failed to send OTP email after retries"
            )

        except Exception as e:
            logger.error(
                "send_otp_email_failed",
                email=email,
                error=str(e)
            )
            raise SequenceException(
                error_code=SequenceErrorCode.EMAIL_ERROR,
                message=str(e)
            )

    async def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        try:
            response = await asyncio.to_thread(
                self.sg_client.client.api_keys.get
            )

            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'api_connected': True,
                'templates_initialized': os.path.exists(
                    os.path.join(self.template_dir, 'email_template.html')
                ),
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

# Initialize email service
email_service = EmailService()

__all__ = ['EmailService', 'email_service']