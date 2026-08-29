from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.auth.permissions import require_admin
from backend.app.db.session import get_db
from backend.app.schemas.organization_member import (
    OrganizationMemberCreate,
    OrganizationMemberListResponse,
    OrganizationMemberResponse,
)
from backend.app.services.organization_member import (
    OrganizationMemberService,
)

router = APIRouter(
    prefix="/organizations",
    tags=["Organization Members"],
)


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=201,
)
def add_member(
    organization_id: int,
    request: OrganizationMemberCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationMemberService(db)

    return service.add_member(
        organization_id=organization_id,
        request=request,
    )


@router.get(
    "/{organization_id}/members",
    response_model=OrganizationMemberListResponse,
)
def list_members(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationMemberService(db)

    members = service.list_members(
        organization_id,
    )

    return {
        "message": "Organization members retrieved successfully.",
        "data": members,
    }