from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from core.config import Settings
from core.security_settings import security_settings
from starlette.middleware.trustedhost import TrustedHostMiddleware
from typing import List
import logging
import re

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
settings = Settings()

# Use TrustedHostMiddleware with your allowed domains
app.add_middleware(TrustedHostMiddleware, allowed_hosts=security_settings.ALLOWED_DOMAINS + ["localhost", "127.0.0.1"])

def is_valid_domain(host: str) -> bool:
    # Basic domain validation regex
    domain_pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return re.match(domain_pattern, host) is not None

def is_allowed_domain(host: str, allowed_domains: List[str]) -> bool:
    return any(host.endswith(domain) for domain in allowed_domains)

# Custom middleware for domain whitelisting
@app.middleware("http")
async def domain_whitelist_middleware(request: Request, call_next):
    host = request.headers.get("Host", "").split(':')[0]  # Remove port if present

    logger.debug(f"Request Host: {host}")
    logger.debug(f"Allowed Domains: {security_settings.ALLOWED_DOMAINS}")

    if not is_valid_domain(host):
        logger.warning(f"Invalid domain or IP request: {host}")
        raise HTTPException(status_code=403, detail="Access forbidden: Invalid domain")

    if not is_allowed_domain(host, security_settings.ALLOWED_DOMAINS):
        logger.warning(f"Access forbidden for Host: {host}")
        raise HTTPException(status_code=403, detail="Access forbidden: Domain not allowed")
    
    logger.info(f"Access allowed for Host: {host}")
    response = await call_next(request)
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=security_settings.ALLOWED_DOMAINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)