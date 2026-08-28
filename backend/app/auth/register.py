from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import RegisterRequest
from backend.app.security.hashing import hash_password
from backend.app.services.auth_service import AuthService
from backend.app.services.email_service import EmailService

router = APIRouter(tags=["Authentication"])


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(User)
        .filter(User.email == request.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered.",
        )

    user = User(
        email=request.email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    auth_service = AuthService(db)
    verification_token = auth_service.set_verification_token(user)

    email_service = EmailService()

    email_service.send_verification_email(
        to_email=user.email,
        token=verification_token,
    )

    return {
        "message": (
            "Registration successful. "
            "Please check your email to verify your account."
        )
    }