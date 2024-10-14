from fastapi import FastAPI
from api.routes import router
from config import Settings

app = FastAPI()
settings = Settings()

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)