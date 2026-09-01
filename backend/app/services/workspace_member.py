from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization_member import (
    get_organization_member,
)
from backend.app.crud.user import get_user_by_id
from backend.app.crud.workspace import get_workspace_by_id
from backend.app.crud.workspace_member import (
    create_workspace_member,
    delete_workspace_member,
    get_workspace_member,
    get_workspace_members,
    update_workspace_member,
)
from backend.app.models.workspace_member import WorkspaceMember
from backend.app.schemas.workspace_member import (
    WorkspaceMemberCreate,
    WorkspaceMemberRoleUpdate,
)


class WorkspaceMemberService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    def add_member(
        self,
        workspace_id: int,
        request: WorkspaceMemberCreate,
    ) -> WorkspaceMember:

        workspace = get_workspace_by_id(
            self.db,
            workspace_id,
        )

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        user = get_user_by_id(
            self.db,
            request.user_id,
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        organization_member = get_organization_member(
            self.db,
            workspace.organization_id,
            request.user_id,
        )

        if organization_member is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must belong to the organization before joining a workspace.",
            )

        existing = get_workspace_member(
            self.db,
            workspace_id,
            request.user_id,
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this workspace.",
            )

        valid_roles = {
            "admin",
            "member",
            "viewer",
        }

        if request.role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace role.",
            )

        return create_workspace_member(
            self.db,
            workspace_id=workspace_id,
            user_id=request.user_id,
            role=request.role,
        )

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    def list_members(
        self,
        workspace_id: int,
    ):

        return get_workspace_members(
            self.db,
            workspace_id,
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    def change_member_role(
        self,
        workspace_id: int,
        user_id: int,
        request: WorkspaceMemberRoleUpdate,
    ) -> WorkspaceMember:

        member = get_workspace_member(
            self.db,
            workspace_id,
            user_id,
        )

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace member not found.",
            )

        valid_roles = {
            "admin",
            "member",
            "viewer",
        }

        if request.role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace role.",
            )

        member.role = request.role

        return update_workspace_member(
            self.db,
            member,
        )

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    def remove_member(
        self,
        workspace_id: int,
        user_id: int,
    ) -> dict:

        member = get_workspace_member(
            self.db,
            workspace_id,
            user_id,
        )

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace member not found.",
            )

        delete_workspace_member(
            self.db,
            member,
        )

        return {
            "message": "Workspace member removed successfully.",
        }