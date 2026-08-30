from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization import get_organization_by_id
from backend.app.crud.organization_member import (
    create_organization_member,
    delete_organization_member,
    get_organization_member,
    get_organization_members,
)
from backend.app.crud.user import get_user_by_id
from backend.app.models.organization_member import OrganizationMember
from backend.app.schemas.organization_member import (
    OrganizationMemberCreate,
    OrganizationMemberRoleUpdate,
)


class OrganizationMemberService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    def add_member(
        self,
        organization_id: int,
        request: OrganizationMemberCreate,
    ) -> OrganizationMember:

        organization = get_organization_by_id(
            self.db,
            organization_id,
        )

        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )

        user = get_user_by_id(
            self.db,
            request.user_id,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        existing = get_organization_member(
            self.db,
            organization_id,
            request.user_id,
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization.",
            )

        return create_organization_member(
            self.db,
            organization_id=organization_id,
            user_id=request.user_id,
            role=request.role,
        )

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    def list_members(
        self,
        organization_id: int,
    ):
        return get_organization_members(
            self.db,
            organization_id,
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    def change_member_role(
        self,
        organization_id: int,
        user_id: int,
        request: OrganizationMemberRoleUpdate,
    ) -> OrganizationMember:

        member = get_organization_member(
            self.db,
            organization_id,
            user_id,
        )

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization member not found.",
            )

        valid_roles = {
            "owner",
            "admin",
            "member",
            "viewer",
        }

        if request.role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid organization role.",
            )

        if member.role == "owner":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owner role cannot be changed. Transfer ownership instead.",
            )

        member.role = request.role

        self.db.commit()
        self.db.refresh(member)

        return member

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    def remove_member(
        self,
        organization_id: int,
        user_id: int,
    ) -> dict:

        member = get_organization_member(
            self.db,
            organization_id,
            user_id,
        )

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization member not found.",
            )

        if member.role == "owner":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The organization owner cannot be removed.",
            )

        delete_organization_member(
            self.db,
            member,
        )

        return {
            "message": "Organization member removed successfully.",
        }

    # ---------------------------------------------------------
    # Leave Organization
    # ---------------------------------------------------------

    def leave_organization(
        self,
        organization_id: int,
        current_user_id: int,
    ) -> dict:

        member = get_organization_member(
            self.db,
            organization_id,
            current_user_id,
        )

        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not a member of this organization.",
            )

        if member.role == "owner":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The organization owner cannot leave. Transfer ownership first.",
            )

        delete_organization_member(
            self.db,
            member,
        )

        return {
            "message": "You have successfully left the organization.",
        }