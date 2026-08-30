from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.db.session import get_db
from backend.app.models.organization_member import OrganizationMember
from backend.app.models.user import User


def require_organization_roles(*roles: str):
    """
    Require that the current user belongs to the organization
    and has one of the allowed organization roles.

    Usage:

        current_user = Depends(
            require_organization_roles(
                "owner",
                "admin",
            )
        )
    """

    def checker(
        organization_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> User:

        # ---------------------------------------------------------
        # Global Super Admin bypass
        # ---------------------------------------------------------

        if current_user.role == "super_admin":
            return current_user

        # ---------------------------------------------------------
        # Organization membership
        # ---------------------------------------------------------

        membership = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == current_user.id,
            )
            .first()
        )

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this organization.",
            )

        # ---------------------------------------------------------
        # Organization role check
        # ---------------------------------------------------------

        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return checker


require_owner = require_organization_roles(
    "owner",
)

require_admin = require_organization_roles(
    "owner",
    "admin",
)

require_member = require_organization_roles(
    "owner",
    "admin",
    "member",
)

require_viewer = require_organization_roles(
    "owner",
    "admin",
    "member",
    "viewer",
)