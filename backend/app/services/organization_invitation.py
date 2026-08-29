from datetime import datetime, timedelta
import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization_invitation import (
    accept_invitation,
    create_invitation,
    get_invitation_by_token,
    list_pending_invitations,
)
from backend.app.crud.organization_member import (
    create_organization_member,
)
from backend.app.models.organization_invitation import OrganizationInvitation
from backend.app.schemas.organization_invitation import (
    AcceptInvitationRequest,
    OrganizationInvitationCreate,
)


class OrganizationInvitationService:
    def __init__(self, db: Session):
        self.db = db

    def create_invitation(
        self,
        organization_id: int,
        invitation: OrganizationInvitationCreate,
        invited_by: int,
    ) -> OrganizationInvitation:
        db_invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=invitation.email,
            role=invitation.role,
            token=secrets.token_urlsafe(32),
            invited_by=invited_by,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )

        return create_invitation(
            self.db,
            db_invitation,
        )

    def list_pending_invitations(
        self,
        organization_id: int,
    ) -> list[OrganizationInvitation]:
        return list_pending_invitations(
            self.db,
            organization_id,
        )

    def accept_invitation(
        self,
        invitation_request: AcceptInvitationRequest,
        current_user_id: int,
    ) -> OrganizationInvitation:
        invitation = get_invitation_by_token(
            self.db,
            invitation_request.token,
        )

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found.",
            )

        if invitation.accepted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has already been accepted.",
            )

        if invitation.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has expired.",
            )

        create_organization_member(
            self.db,
            organization_id=invitation.organization_id,
            user_id=current_user_id,
            role=invitation.role,
        )

        return accept_invitation(
            self.db,
            invitation,
        )