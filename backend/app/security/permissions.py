from fastapi import Depends, HTTPException, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.roles import Role
from backend.app.models.user import User


def require_role(*roles: Role):
    def checker(
        current_user: User = Depends(get_current_user),
    ):
        user_role = Role(current_user.role)

        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return checker