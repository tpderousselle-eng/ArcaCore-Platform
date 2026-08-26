from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.auth_service import login_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/login123")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    return login_user(
        db,
        form_data.username,
        form_data.password,
    )