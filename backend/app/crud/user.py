from sqlalchemy.orm import Session

from backend.app.auth.roles import Role
from backend.app.models.user import User
from backend.app.schemas.user import UserCreate
from backend.app.security.hashing import hash_password


def get_user_by_email(db: Session, email: str):
    email = email.lower().strip()

    return (
        db.query(User)
        .filter(User.email == email)
        .first()
    )


def create_user(db: Session, user: UserCreate):
    db_user = User(
        email=user.email.lower().strip(),
        full_name=user.full_name,
        hashed_password=hash_password(user.password),
        role=Role.USER.value,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user