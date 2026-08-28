from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.crud.user import get_user_by_email
from backend.app.db.session import get_db
from backend.app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
)
from backend.app.services.auth_service import AuthService
from backend.app.services.email_service import EmailService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
)
def resend_verification(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    user = get_user_by_email(
        db,
        request.email,
    )

    if not user:
        return MessageResponse(
            message=(
                "If an account exists with that email, "
                "a verification email has been sent."
            )
        )

    if user.is_verified:
        return MessageResponse(
            message="This email address is already verified."
        )

    auth_service = AuthService(db)

    token = auth_service.set_verification_token(user)

    email_service = EmailService()

    email_service.send_verification_email(
        to_email=user.email,
        token=token,
    )

    return MessageResponse(
        message=(
            "If an account exists with that email, "
            "a verification email has been sent."
        )
    )