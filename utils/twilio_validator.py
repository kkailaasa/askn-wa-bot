import logging
from twilio.request_validator import RequestValidator
from fastapi import Request, HTTPException
from core.config import settings

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def validate_twilio_request(request: Request):
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)

    url = str(request.url)
    signature = request.headers.get("X-Twilio-Signature")

    if not signature:
        logger.error("X-Twilio-Signature header is missing")
        raise HTTPException(status_code=400, detail="X-Twilio-Signature header is missing")

    body = await request.form()
    params = dict(body)

    logger.debug(f"Validating Twilio request: URL={url}, Signature={signature}, Params={params}")

    if not validator.validate(url, params, signature):
        logger.error(f"Invalid Twilio signature: URL={url}, Signature={signature}, Params={params}")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    logger.info("Twilio request validation successful")
    return True