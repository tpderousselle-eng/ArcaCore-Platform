from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.auth_service import login_user
from backend.app.schemas.auth import LoginResponse
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/login", response_model=LoginResponse)
def login(
    email: str,
    password: str,
    db: Session = Depends(get_db),
):
    result = login_user(
        db,
        email,
        password,
    )

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    return result