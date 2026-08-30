from fastapi import Depends, FastAPI

from backend.app.api.routes import router
from backend.app.auth.dependencies import get_current_user
from backend.app.core.config import settings
from backend.app.schemas.auth import UserResponse

app = FastAPI(
    title=settings.APP_NAME,
    description="Core AI Platform for ArcaCentum",
    version=settings.APP_VERSION,
)

app.include_router(router)


@app.get(
    "/users/me",
    response_model=UserResponse,
    tags=["Users"],
)
def read_current_user(
    current_user=Depends(get_current_user),
):
    return current_user