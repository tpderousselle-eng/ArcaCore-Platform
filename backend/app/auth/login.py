from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/login123")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    auth_service = AuthService(db)

    try:
        result = auth_service.login_user(
            form_data.username,
            form_data.password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e),
        )

    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return result