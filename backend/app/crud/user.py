from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app.auth.roles import Role
from backend.app.models.user import User
from backend.app.schemas.user import UserCreate
from backend.app.security.hashing import hash_password


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------

def create_user(
    db: Session,
    user: UserCreate,
):
    db_user = User(
        email=user.email.lower().strip(),
        full_name=user.full_name,
        hashed_password=hash_password(user.password),
        role=Role.USER.value,
        status="active",
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


# ---------------------------------------------------------
# Read
# ---------------------------------------------------------

def get_user_by_id(
    db: Session,
    user_id: int,
):
    return (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )


def get_user_by_email(
    db: Session,
    email: str,
):
    email = email.lower().strip()

    return (
        db.query(User)
        .filter(User.email == email)
        .first()
    )


def get_users(
    db: Session,
    skip: int = 0,
    limit: int = 25,
):
    return (
        db.query(User)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def search_users(
    db: Session,
    search: str,
    skip: int = 0,
    limit: int = 25,
):
    return (
        db.query(User)
        .filter(
            or_(
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            )
        )
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------

def update_user(
    db: Session,
    user: User,
):
    db.commit()
    db.refresh(user)

    return user


def update_user_role(
    db: Session,
    user: User,
    role: str,
):
    user.role = role

    db.commit()
    db.refresh(user)

    return user


def update_user_status(
    db: Session,
    user: User,
    status: str,
):
    user.status = status

    db.commit()
    db.refresh(user)

    return user


# ---------------------------------------------------------
# Soft Delete
# ---------------------------------------------------------

def deactivate_user(
    db: Session,
    user: User,
):
    user.status = "inactive"

    db.commit()
    db.refresh(user)

    return user