from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.db.session import get_db
from backend.app.models.organization_member import OrganizationMember
from backend.app.models.project import Project
from backend.app.models.user import User
from backend.app.models.workspace import Workspace


def require_project_roles(*roles: str):
    """
    Resolve the organization from the project and verify
    the current user's organization role.
    """

    def checker(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> User:

        # ---------------------------------------------------------
        # Global Super Admin bypass
        # ---------------------------------------------------------

        if current_user.role == "super_admin":
            return current_user

        # ---------------------------------------------------------
        # Project lookup
        # ---------------------------------------------------------

        project = (
            db.query(Project)
            .filter(Project.id == project_id)
            .first()
        )

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        # ---------------------------------------------------------
        # Workspace lookup
        # ---------------------------------------------------------

        workspace = (
            db.query(Workspace)
            .filter(Workspace.id == project.workspace_id)
            .first()
        )

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        # ---------------------------------------------------------
        # Organization membership
        # ---------------------------------------------------------

        membership = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.organization_id == workspace.organization_id,
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
        # Role check
        # ---------------------------------------------------------

        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return checker


require_project_admin = require_project_roles(
    "owner",
    "admin",
)

require_project_member = require_project_roles(
    "owner",
    "admin",
    "member",
)