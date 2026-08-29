from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.permissions import require_admin
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.organization import (
    OrganizationCreate,
    OrganizationDetailResponse,
    OrganizationListResponse,
    OrganizationResponse,
)
from backend.app.services.organization import OrganizationService

router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=201,
)
def create_organization(
    request: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrganizationService(db)

    return service.create_organization(
        organization=request,
        owner_id=current_user.id,
    )


@router.get(
    "/",
    response_model=OrganizationListResponse,
)
def list_organizations(
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationService(db)

    organizations = service.list_organizations(
        skip=skip,
        limit=limit,
    )

    return {
        "message": "Organizations retrieved successfully.",
        "data": organizations,
    }


@router.get(
    "/{organization_id}",
    response_model=OrganizationDetailResponse,
)
def get_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = OrganizationService(db)

    return service.get_organization(
        organization_id,
    )