from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.organization_invitation import (
    OrganizationInvitationCreate,
    OrganizationInvitationListResponse,
    OrganizationInvitationResponse,
)
from backend.app.security.organization_permissions import (
    require_admin,
)
from backend.app.services.organization_invitation import (
    OrganizationInvitationService,
)

router = APIRouter(
    prefix="/organizations",
    tags=["Organization Invitations"],
)


# ---------------------------------------------------------
# Invite Member
# ---------------------------------------------------------

@router.post(
    "/{organization_id}/invitations",
    response_model=OrganizationInvitationResponse,
    status_code=201,
)
def invite_member(
    organization_id: int,
    request: OrganizationInvitationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationInvitationService(db)

    return service.invite_member(
        organization_id=organization_id,
        invited_by=current_user.id,
        request=request,
    )


# ---------------------------------------------------------
# List Invitations
# ---------------------------------------------------------

@router.get(
    "/{organization_id}/invitations",
    response_model=OrganizationInvitationListResponse,
)
def list_invitations(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationInvitationService(db)

    invitations = service.list_invitations(
        organization_id,
    )

    return {
        "message": "Organization invitations retrieved successfully.",
        "data": invitations,
    }


# ---------------------------------------------------------
# Accept Invitation
# ---------------------------------------------------------

@router.post(
    "/invitations/{token}/accept",
    response_model=OrganizationInvitationResponse,
)
def accept_invitation(
    token: str,
    db: Session = Depends(get_db),
):
    service = OrganizationInvitationService(db)

    return service.accept_invitation(
        token,
    )