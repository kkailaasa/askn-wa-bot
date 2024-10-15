from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from core.config import Settings
from core.security_settings import security_settings

app = FastAPI()
settings = Settings()

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
async def ip_whitelist_middleware(request: Request, call_next):
    client_ip = request.client.host
    if client_ip not in security_settings.ALLOWED_IPS:
        raise HTTPException(status_code=403, detail="Access forbidden")
    response = await call_next(request)
    return response

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)