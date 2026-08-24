from fastapi import FastAPI
from backend.app.api.routes import router
from backend.app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="Core AI Platform for ArcaCentum",
    version=settings.APP_VERSION,
)



app.include_router(router)