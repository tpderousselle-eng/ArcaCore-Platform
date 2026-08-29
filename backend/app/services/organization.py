from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization import (
    get_organization_by_id,
    get_organization_by_slug,
    get_organizations,
)
from backend.app.models.organization import Organization


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Organizations
    # ---------------------------------------------------------

    def list_organizations(
        self,
        skip: int = 0,
        limit: int = 25,
    ):
        return get_organizations(
            self.db,
            skip,
            limit,
        )

    def get_organization(
        self,
        organization_id: int,
    ) -> Organization:
        organization = get_organization_by_id(
            self.db,
            organization_id,
        )

        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )

        return organization

    def get_organization_by_slug(
        self,
        slug: str,
    ) -> Organization | None:
        return get_organization_by_slug(
            self.db,
            slug,
        )