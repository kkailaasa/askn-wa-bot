from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent, Attachment, FileContent, FileName, FileType, Disposition
from core.config import settings
import logging
import structlog
from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import base64
import json
import asyncio
from utils.redis_helpers import RedisLock, cache
from core.sequence_errors import SequenceException, SequenceErrorCode
import jinja2
import aiofiles
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

logger = structlog.get_logger(__name__)

class EmailTemplateManager:
    """Manages email templates with caching"""
    def __init__(self, template_dir: str):
        self.template_dir = template_dir
        self.cache_prefix = "email:template:"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=True,
            enable_async=True
        )

    async def get_template(self, template_name: str) -> str:
        """Get template with caching"""
        cache_key = f"{self.cache_prefix}{template_name}"

        # Try cache first
        cached = await cache.get(cache_key)
        if cached:
            return cached

        # Load template
        try:
            template_path = os.path.join(self.template_dir, template_name)
            async with aiofiles.open(template_path, mode='r') as f:
                content = await f.read()

            # Cache template
            await cache.set(cache_key, content, expiry=3600)
            return content

        except Exception as e:
            logger.error(
                "template_load_failed",
                template=template_name,
                error=str(e)
            )
            raise SequenceException(
                error_code=SequenceErrorCode.SYSTEM_ERROR,
                message=f"Failed to load email template: {template_name}"
            )

    async def render_template(
        self,
        template_name: str,
        context: Dict[str, Any]
    ) -> str:
        """Render template with context"""
        try:
            template = self.env.get_template(template_name)
            return await template.render_async(**context)
        except Exception as e:
            logger.error(
                "template_render_failed",
                template=template_name,
                error=str(e)
            )
            raise SequenceException(
                error_code=SequenceErrorCode.SYSTEM_ERROR,
                message="Failed to render email template"
            )

class EmailDeliveryTracker:
    """Tracks email delivery status and retries"""
    def __init__(self):
        self.cache_prefix = "email:delivery:"

    async def track_attempt(
        self,
        email: str,
        message_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Track delivery attempt"""
        key = f"{self.cache_prefix}{message_id}"
        data = {
            "email": email,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {}
        }
        await cache.set(key, json.dumps(data), expiry=86400)  # 24 hours

    async def get_status(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get delivery status"""
        key = f"{self.cache_prefix}{message_id}"
        data = await cache.get(key)
        return json.loads(data) if data else None

class EmailRateLimiter:
    """Handles rate limiting for email sending"""
    def __init__(self):
        self.cache_prefix = "email:ratelimit:"
        self.window = 3600  # 1 hour
        self.limit = 3  # emails per hour per recipient

    async def check_rate_limit(self, email: str) -> Tuple[bool, int]:
        """Check if rate limited"""
        key = f"{self.cache_prefix}{email}"

        async with RedisLock(f"ratelimit:{email}"):
            count = int(await cache.get(key) or 0)
            if count >= self.limit:
                return True, self.window

            await cache.set(key, str(count + 1), expiry=self.window)
            return False, 0

class EmailService:
    """Enhanced email service with improved error handling and features"""
    def __init__(self):
        self.project_root = self._get_project_root()
        self.template_dir = os.path.join(self.project_root, "templates")
        self.template_manager = EmailTemplateManager(self.template_dir)
        self.delivery_tracker = EmailDeliveryTracker()
        self.rate_limiter = EmailRateLimiter()

        try:
            self.sg_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
            logger.info("sendgrid_client_initialized")
        except Exception as e:
            logger.error("sendgrid_init_failed", error=str(e))
            raise

        # Ensure template directory exists
        os.makedirs(self.template_dir, exist_ok=True)

        logger.debug("email_service_initialized", template_dir=self.template_dir)

    def _get_project_root(self) -> str:
        """Get project root directory"""
        current_dir = Path(__file__).resolve().parent
        while current_dir.parent != current_dir:
            if (current_dir / "docker-compose.yml").exists():
                return str(current_dir)
            current_dir = current_dir.parent
        return str(Path(__file__).resolve().parent)

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

        # Check rate limit
        is_limited, retry_after = await self.rate_limiter.check_rate_limit(email)
        if is_limited:
            raise SequenceException(
                error_code=SequenceErrorCode.RATE_LIMIT,
                message="Too many email requests",
                retry_after=retry_after
            )

        logger.debug("preparing_otp_email", email=email)

        try:
            # Prepare email content
            template_context = {
                'otp_code': otp,
                'current_year': datetime.utcnow().year,
                'expiry_minutes': 10
            }

            html_content = await self.template_manager.render_template(
                'email_template.html',
                template_context
            )

            # Create email message
            message = Mail(
                from_email=Email(
                    email=settings.EMAIL_FROM,
                    name=settings.EMAIL_FROM_NAME
                ),
                to_emails=To(email=email),
                subject='Your Email Verification Code',
                html_content=HtmlContent(html_content)
            )

            # Add plain text alternative
            message.add_content(
                Content(
                    "text/plain",
                    f"Your verification code is: {otp}\n\n"
                    "This code will expire in 10 minutes.\n\n"
                    "If you didn't request this code, please ignore this email."
                )
            )

            # Send email with retries
            last_error = None
            for attempt in range(retry_count):
                try:
                    response = await asyncio.to_thread(
                        self.sg_client.send,
                        message
                    )

                    if response.status_code == 202:
                        # Track successful delivery
                        await self.delivery_tracker.track_attempt(
                            email=email,
                            message_id=response.headers.get('X-Message-Id'),
                            status='sent',
                            details={'attempt': attempt + 1}
                        )

                        logger.info(
                            "otp_email_sent",
                            email=email,
                            message_id=response.headers.get('X-Message-Id')
                        )

                        return {
                            'success': True,
                            'message_id': response.headers.get('X-Message-Id'),
                            'timestamp': datetime.utcnow().isoformat()
                        }

                except Exception as e:
                    last_error = e
                    if attempt < retry_count - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    break

            # Track failed delivery
            await self.delivery_tracker.track_attempt(
                email=email,
                message_id='failed',
                status='failed',
                details={
                    'error': str(last_error),
                    'attempts': retry_count
                }
            )

            logger.error(
                "otp_email_failed",
                email=email,
                error=str(last_error),
                attempts=retry_count
            )

            raise SequenceException(
                error_code=SequenceErrorCode.EMAIL_ERROR,
                message="Failed to send OTP email"
            )

        except SequenceException:
            raise
        except Exception as e:
            logger.error(
                "unexpected_email_error",
                email=email,
                error=str(e),
                error_type=type(e).__name__
            )
            raise SequenceException(
                error_code=SequenceErrorCode.SYSTEM_ERROR,
                message="Unexpected error sending email"
            )

    async def initialize_templates(self) -> None:
        """Initialize email templates"""
        try:
            template_path = os.path.join(self.template_dir, 'email_template.html')
            if not os.path.exists(template_path):
                logger.info("creating_email_template", path=template_path)

                # Create default template
                default_template = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Verification</title>
    <style>
        /* Add your CSS styles here */
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
            <p>&copy; KAILASA's E-Citizen Service</p>
        </div>
    </div>
</body>
</html>'''

                async with aiofiles.open(template_path, 'w') as f:
                    await f.write(default_template)

                logger.info("email_template_created")

        except Exception as e:
            logger.error(
                "template_initialization_failed",
                error=str(e)
            )
            raise

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

# Export the service
__all__ = ['email_service']