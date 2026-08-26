from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.auth_service import AuthService

router = APIRouter()


@router.get("/verify-email")
def verify_email(
    token: str,
    db: Session = Depends(get_db),
):
    auth_service = AuthService(db)

    user = auth_service.verify_email_token(token)

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token.",
        )

    return {
        "message": "Email verified successfully."
    }