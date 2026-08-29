from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.permissions import require_admin
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.organization_invitation import (
    AcceptInvitationRequest,
    OrganizationInvitationCreate,
    OrganizationInvitationListResponse,
    OrganizationInvitationResponse,
)
from backend.app.services.organization_invitation import (
    OrganizationInvitationService,
)

router = APIRouter(
    prefix="/organizations",
    tags=["Organization Invitations"],
)


@router.post(
    "/{organization_id}/invitations",
    response_model=OrganizationInvitationResponse,
    status_code=201,
)
def create_invitation(
    organization_id: int,
    request: OrganizationInvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    service = OrganizationInvitationService(db)

    return service.create_invitation(
        organization_id=organization_id,
        invitation=request,
        invited_by=current_user.id,
    )


@router.get(
    "/{organization_id}/invitations",
    response_model=OrganizationInvitationListResponse,
)
def list_pending_invitations(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    service = OrganizationInvitationService(db)

    invitations = service.list_pending_invitations(
        organization_id,
    )

    return {
        "message": "Pending invitations retrieved successfully.",
        "data": invitations,
    }


@router.post(
    "/accept-invitation",
    response_model=OrganizationInvitationResponse,
)
def accept_invitation(
    request: AcceptInvitationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrganizationInvitationService(db)

    return service.accept_invitation(
        invitation_request=request,
        current_user_id=current_user.id,
    )