from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.auth_service import login_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


class LoginData(BaseModel):
    username: str
    password: str


@router.post("/login123")
def login(
    data: LoginData,
    db: Session = Depends(get_db),
):
    return login_user(
        db,
        data.username,
        data.password,
    )