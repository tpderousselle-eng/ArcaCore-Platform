from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
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
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    result = login_user(
    db,
    form_data.username,
    form_data.password,
)

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    return result