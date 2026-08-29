from sqlalchemy.orm import Session

from backend.app.models.organization import Organization
from backend.app.schemas.organization import (
    OrganizationCreate,
)


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------

def create_organization(
    db: Session,
    organization: OrganizationCreate,
    owner_id: int,
):
    db_organization = Organization(
        name=organization.name,
        slug=organization.slug.lower().strip(),
        owner_id=owner_id,
    )

    db.add(db_organization)
    db.commit()
    db.refresh(db_organization)

    return db_organization


# ---------------------------------------------------------
# Read
# ---------------------------------------------------------

def get_organization_by_id(
    db: Session,
    organization_id: int,
):
    return (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )


def get_organization_by_slug(
    db: Session,
    slug: str,
):
    slug = slug.lower().strip()

    return (
        db.query(Organization)
        .filter(Organization.slug == slug)
        .first()
    )


def get_organizations(
    db: Session,
    skip: int = 0,
    limit: int = 25,
):
    return (
        db.query(Organization)
        .order_by(Organization.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------

def update_organization(
    db: Session,
    organization: Organization,
):
    db.commit()
    db.refresh(organization)

    return organization


# ---------------------------------------------------------
# Delete
# ---------------------------------------------------------

def delete_organization(
    db: Session,
    organization: Organization,
):
    db.delete(organization)
    db.commit()