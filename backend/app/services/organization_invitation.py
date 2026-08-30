from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization import get_organization_by_id
from backend.app.crud.organization_invitation import (
    create_organization_invitation,
    delete_organization_invitation,
    get_organization_invitations,
    get_pending_organization_invitation,
    get_valid_organization_invitation_by_token,
    update_organization_invitation,
)
from backend.app.crud.organization_member import (
    create_organization_member,
    get_organization_member,
)
from backend.app.crud.user import get_user_by_email
from backend.app.models.organization_invitation import (
    OrganizationInvitation,
)
from backend.app.schemas.organization_invitation import (
    OrganizationInvitationCreate,
)


class OrganizationInvitationService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    def invite_member(
        self,
        organization_id: int,
        invited_by: int,
        request: OrganizationInvitationCreate,
    ) -> OrganizationInvitation:

        organization = get_organization_by_id(
            self.db,
            organization_id,
        )

        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )

        existing = get_pending_organization_invitation(
            self.db,
            organization_id,
            request.email,
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pending invitation already exists for this email.",
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

        existing_user = get_user_by_email(
            self.db,
            request.email,
        )

        if existing_user:

            existing_member = get_organization_member(
                self.db,
                organization_id,
                existing_user.id,
            )

            if existing_member:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User is already a member of this organization.",
                )

        token = token_urlsafe(32)

        expires_at = (
            datetime.now(UTC).replace(tzinfo=None)
            + timedelta(days=7)
        )

        return create_organization_invitation(
            db=self.db,
            organization_id=organization_id,
            email=request.email,
            role=request.role,
            token=token,
            invited_by=invited_by,
            expires_at=expires_at,
        )

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    def list_invitations(
        self,
        organization_id: int,
    ):

        return get_organization_invitations(
            self.db,
            organization_id,
        )

    # ---------------------------------------------------------
    # Accept
    # ---------------------------------------------------------

    def accept_invitation(
        self,
        token: str,
    ) -> OrganizationInvitation:

        invitation = get_valid_organization_invitation_by_token(
            self.db,
            token,
        )

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found or already used.",
            )

        user = get_user_by_email(
            self.db,
            invitation.email,
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account not found.",
            )

        existing_member = get_organization_member(
            self.db,
            invitation.organization_id,
            user.id,
        )

        if existing_member is None:
            create_organization_member(
                self.db,
                organization_id=invitation.organization_id,
                user_id=user.id,
                role=invitation.role,
            )

        invitation.status = "accepted"

        invitation.accepted_at = (
            datetime.now(UTC)
            .replace(tzinfo=None)
        )

        update_organization_invitation(
            self.db,
            invitation,
        )

        return invitation

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    def cancel_invitation(
        self,
        invitation: OrganizationInvitation,
    ):

        delete_organization_invitation(
            self.db,
            invitation,
        )

        return {
            "message": "Invitation cancelled successfully.",
        }