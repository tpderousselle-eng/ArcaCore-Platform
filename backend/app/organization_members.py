from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.organization_member import (
    OrganizationMemberCreate,
    OrganizationMemberListResponse,
    OrganizationMemberResponse,
    OrganizationMemberRoleUpdate,
)
from backend.app.security.organization_permissions import (
    require_admin,
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


@router.patch(
    "/{organization_id}/members/{user_id}/role",
    response_model=OrganizationMemberResponse,
)
def change_member_role(
    organization_id: int,
    user_id: int,
    request: OrganizationMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationMemberService(db)

    return service.change_member_role(
        organization_id=organization_id,
        user_id=user_id,
        request=request,
    )


@router.delete(
    "/{organization_id}/members/{user_id}",
)
def remove_member(
    organization_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationMemberService(db)

    return service.remove_member(
        organization_id=organization_id,
        user_id=user_id,
    )


@router.post(
    "/{organization_id}/leave",
)
def leave_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrganizationMemberService(db)

    return service.leave_organization(
        organization_id=organization_id,
        current_user_id=current_user.id,
    )