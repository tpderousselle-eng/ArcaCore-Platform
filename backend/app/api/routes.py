from fastapi import APIRouter

from backend.app.auth.change_password import (
    router as change_password_router,
)
from backend.app.auth.forgot_password import (
    router as forgot_password_router,
)
from backend.app.auth.login import router as login_router
from backend.app.auth.me import router as me_router
from backend.app.auth.register import router as register_router
from backend.app.auth.resend_verification import (
    router as resend_verification_router,
)
from backend.app.auth.reset_password import (
    router as reset_password_router,
)
from backend.app.auth.verify_email import (
    router as verify_email_router,
)

router = APIRouter()


@router.get("/")
def root():
    return {
        "message": "Welcome to ArcaCore!",
        "status": "online",
    }


@router.get("/health")
def health():
    return {
        "status": "healthy",
    }


router.include_router(register_router)
router.include_router(login_router)
router.include_router(me_router)
router.include_router(verify_email_router)
router.include_router(forgot_password_router)
router.include_router(reset_password_router)
router.include_router(resend_verification_router)
router.include_router(change_password_router)