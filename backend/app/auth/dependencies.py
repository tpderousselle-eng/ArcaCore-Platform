from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.crud.user import get_user_by_email
from backend.app.security.jwt import verify_access_token

# This MUST match your login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = verify_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    email = payload.get("email")

    if not email:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
        )

    user = get_user_by_email(db, email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return user