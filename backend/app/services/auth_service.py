from datetime import datetime, timedelta
import secrets

from sqlalchemy.orm import Session

from backend.app.crud.user import get_user_by_email
from backend.app.models.user import User
from backend.app.security.hashing import (
    hash_password,
    verify_password,
)
from backend.app.security.jwt import create_access_token


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Password Helpers
    # ------------------------------------------------------------------

    def create_password_hash(self, password: str) -> str:
        return hash_password(password)

    def verify_user_password(
        self,
        password: str,
        hashed_password: str,
    ) -> bool:
        return verify_password(
            password,
            hashed_password,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate_user(
        self,
        email: str,
        password: str,
    ):
        user = get_user_by_email(
            self.db,
            email,
        )

        if not user:
            return None

        if not verify_password(
            password,
            user.hashed_password,
        ):
            return None

        return user

    def login_user(
        self,
        email: str,
        password: str,
    ):
        user = self.authenticate_user(
            email,
            password,
        )

        if not user:
            return None

        if not user.is_verified:
            raise ValueError(
                "Please verify your email before logging in."
            )

        token = create_access_token(
            {
                "sub": str(user.id),
                "email": user.email,
            }
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
            },
        }

    # ------------------------------------------------------------------
    # Change Password
    # ------------------------------------------------------------------

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ):
        if not verify_password(
            current_password,
            user.hashed_password,
        ):
            raise ValueError(
                "Current password is incorrect."
            )

        user.hashed_password = hash_password(
            new_password
        )

        self.db.commit()
        self.db.refresh(user)

        return {
            "message": "Password changed successfully."
        }

    # ------------------------------------------------------------------
    # Email Verification
    # ------------------------------------------------------------------

    def generate_verification_token(self) -> str:
        return secrets.token_urlsafe(48)

    def set_verification_token(
        self,
        user: User,
    ) -> str:
        token = self.generate_verification_token()

        user.verification_token = token
        user.verification_token_expires = (
            datetime.utcnow()
            + timedelta(hours=24)
        )

        self.db.commit()
        self.db.refresh(user)

        return token

    def verify_email_token(
        self,
        token: str,
    ) -> User | None:
        user = (
            self.db.query(User)
            .filter(
                User.verification_token == token
            )
            .first()
        )

        if not user:
            return None

        if (
            user.verification_token_expires
            is None
            or user.verification_token_expires
            < datetime.utcnow()
        ):
            return None

        user.is_verified = True
        user.verification_token = None
        user.verification_token_expires = None

        self.db.commit()
        self.db.refresh(user)

        return user