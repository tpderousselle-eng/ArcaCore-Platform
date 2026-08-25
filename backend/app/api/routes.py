from fastapi import APIRouter
from backend.app.auth.login import router as login_router
from backend.app.auth.register import router as register_router
router = APIRouter()


@router.get("/")
def root():
    return {
        "message": "Welcome to ArcaCore!",
        "status": "online"
    }


@router.get("/health")
def health():
    return {
        "status": "healthy"
    }

router.include_router(register_router)
router.include_router(login_router)
