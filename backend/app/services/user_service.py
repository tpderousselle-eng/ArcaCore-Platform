from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.user import (
    get_user_by_id,
    get_users,
    search_users,
    update_user,
    update_user_role,
    update_user_status,
    deactivate_user,
)
from backend.app.models.user import User


class UserService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Users
    # ---------------------------------------------------------

    def list_users(
        self,
        search: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ):
        if search:
            return search_users(
                self.db,
                search,
                skip,
                limit,
            )

        return get_users(
            self.db,
            skip,
            limit,
        )

    def get_user(
        self,
        user_id: int,
    ) -> User:
        user = get_user_by_id(
            self.db,
            user_id,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        return user

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    def update_user(
        self,
        user_id: int,
        full_name: str,
    ) -> User:
        user = self.get_user(user_id)

        user.full_name = full_name.strip()

        return update_user(
            self.db,
            user,
        )

    def change_role(
        self,
        user_id: int,
        role: str,
    ) -> User:
        user = self.get_user(user_id)

        return update_user_role(
            self.db,
            user,
            role,
        )

    def change_status(
        self,
        user_id: int,
        status_value: str,
    ) -> User:
        user = self.get_user(user_id)

        return update_user_status(
            self.db,
            user,
            status_value,
        )

    # ---------------------------------------------------------
    # Soft Delete
    # ---------------------------------------------------------

    def deactivate_user(
        self,
        user_id: int,
    ) -> User:
        user = self.get_user(user_id)

        return deactivate_user(
            self.db,
            user,
        )