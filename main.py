from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.routes import router
from core.config import Settings
from services.ecitizen_auth import KeycloakOperationError
from utils.http_client import http_pool
from utils.redis_pool import redis_pool
import atexit
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
settings = Settings()

@atexit.register
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application")
    http_pool.close_all()
    redis_pool.close()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.exception_handler(KeycloakOperationError)
async def keycloak_exception_handler(request: Request, exc: KeycloakOperationError):
    logger.error(f"Keycloak operation failed: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "An error occurred while processing your request."},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected error occurred."},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)