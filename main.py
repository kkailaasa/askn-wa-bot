from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from core.config import Settings
from core.security_settings import security_settings
from starlette.middleware.trustedhost import TrustedHostMiddleware

app = FastAPI()
settings = Settings()

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["yourdomain.com"])

def get_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.client.host

def is_allowed_domain(host: str, allowed_domains: List[str]) -> bool:
    return any(host.endswith(domain) for domain in allowed_domains)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=security_settings.ALLOWED_DOMAINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware for IP whitelisting
@app.middleware("http")
async def ip_and_domain_whitelist_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)
    host = request.headers.get("Host", "").split(':')[0]  # Remove port if present

    logger.debug(f"Client IP: {client_ip}")
    logger.debug(f"Request Host: {host}")
    logger.debug(f"Allowed IPs: {security_settings.ALLOWED_IPS}")
    logger.debug(f"Allowed Domains: {security_settings.ALLOWED_DOMAINS}")
    logger.debug(f"Twilio IP Ranges: {security_settings.TWILIO_IP_RANGES}")

    ip_allowed = (
        client_ip in security_settings.ALLOWED_IPS or
        any(ipaddress.ip_address(client_ip) in ipaddress.ip_network(twilio_range, strict=False)
            for twilio_range in security_settings.TWILIO_IP_RANGES)
    )

    domain_allowed = is_allowed_domain(host, security_settings.ALLOWED_DOMAINS)

    if not (ip_allowed or domain_allowed):
        raise HTTPException(status_code=403, detail="Access forbidden")
    
    response = await call_next(request)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)