from fastapi import Depends, HTTPException, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.roles import Role
from backend.app.models.user import User


def require_roles(*roles: Role):
    allowed_roles = {role.value for role in roles}

    def dependency(
        current_user: User = Depends(get_current_user),
    ):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return dependency


# ---------------------------------------------------------
# Common Role Dependencies
# ---------------------------------------------------------

require_user = require_roles(
    Role.USER,
    Role.MANAGER,
    Role.ADMIN,
    Role.OWNER,
    Role.SUPER_ADMIN,
)

require_manager = require_roles(
    Role.MANAGER,
    Role.ADMIN,
    Role.OWNER,
    Role.SUPER_ADMIN,
)

require_admin = require_roles(
    Role.ADMIN,
    Role.OWNER,
    Role.SUPER_ADMIN,
)

require_owner = require_roles(
    Role.OWNER,
    Role.SUPER_ADMIN,
)

require_super_admin = require_roles(
    Role.SUPER_ADMIN,
)