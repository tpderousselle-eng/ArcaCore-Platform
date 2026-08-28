from datetime import datetime, timedelta
import secrets

from sqlalchemy.orm import Session

from backend.app.crud.user import get_user_by_email
from backend.app.models.user import User
from backend.app.security.hashing import hash_password


class PasswordResetService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Token Generation
    # ---------------------------------------------------------

    def generate_reset_token(self) -> str:
        return secrets.token_urlsafe(48)

    # ---------------------------------------------------------
    # Forgot Password
    # ---------------------------------------------------------

    def create_reset_token(
        self,
        email: str,
    ) -> str | None:

        user = get_user_by_email(self.db, email)

        if not user:
            return None

        token = self.generate_reset_token()

        user.password_reset_token = token
        user.password_reset_token_expires = (
            datetime.utcnow() + timedelta(hours=1)
        )

        self.db.commit()
        self.db.refresh(user)

        return token

    # ---------------------------------------------------------
    # Validate Token
    # ---------------------------------------------------------

    def validate_reset_token(
        self,
        token: str,
    ) -> User | None:

        user = (
            self.db.query(User)
            .filter(User.password_reset_token == token)
            .first()
        )

        if not user:
            return None

        if (
            user.password_reset_token_expires is None
            or user.password_reset_token_expires < datetime.utcnow()
        ):
            return None

        return user

    # ---------------------------------------------------------
    # Reset Password
    # ---------------------------------------------------------

    def reset_password(
        self,
        token: str,
        new_password: str,
    ) -> bool:

        user = self.validate_reset_token(token)

        if not user:
            return False

        user.hashed_password = hash_password(new_password)

        user.password_reset_token = None
        user.password_reset_token_expires = None

        self.db.commit()
        self.db.refresh(user)

        return True