from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization import get_organization_by_id
from backend.app.crud.organization_member import (
    create_organization_member,
    get_organization_member,
    get_organization_members,
)
from backend.app.crud.user import get_user_by_id
from backend.app.models.organization_member import OrganizationMember
from backend.app.schemas.organization_member import OrganizationMemberCreate


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