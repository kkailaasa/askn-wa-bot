from twilio.request_validator import RequestValidator
from fastapi import Request, HTTPException
from core.config import settings

async def validate_twilio_request(request: Request):
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)

    # Get the full URL of the request
    url = str(request.url)

    # Get the X-Twilio-Signature header
    signature = request.headers.get("X-Twilio-Signature")

    if not signature:
        raise HTTPException(status_code=400, detail="X-Twilio-Signature header is missing")

    # Get the request body
    body = await request.form()

    # Convert body to dict
    params = dict(body)

    # Validate the request
    if not validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    return True