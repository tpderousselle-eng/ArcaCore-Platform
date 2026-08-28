from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
)
from backend.app.services.email_service import EmailService
from backend.app.services.password_reset_service import (
    PasswordResetService,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
)
def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    password_reset_service = PasswordResetService(db)

    token = password_reset_service.create_reset_token(
        request.email,
    )

    if token:
        email_service = EmailService()

        email_service.send_password_reset_email(
            to_email=request.email,
            token=token,
        )

    return MessageResponse(
        message=(
            "If an account exists with that email, "
            "a password reset email has been sent."
        )
    )