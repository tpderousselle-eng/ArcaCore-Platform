from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.crud.user import (
    create_user,
    get_user_by_email,
)
from backend.app.db.session import get_db
from backend.app.schemas.user import UserCreate
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
def register(
    email: str,
    full_name: str,
    password: str,
    db: Session = Depends(get_db),
):
    existing = get_user_by_email(db, email)

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    user_data = UserCreate(
        email=email,
        full_name=full_name,
        password=password,
    )

    user = create_user(db, user_data)

    return {
        "message": "User created successfully",
        "user_id": user.id,
        "email": user.email,
    }