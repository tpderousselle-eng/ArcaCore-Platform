from sqlalchemy.orm import Session

from backend.app.models.organization_invitation import (
    OrganizationInvitation,
)


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------


def create_organization_invitation(
    db: Session,
    organization_id: int,
    email: str,
    role: str,
    token: str,
    invited_by: int,
    expires_at,
) -> OrganizationInvitation:

    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email,
        role=role,
        token=token,
        invited_by=invited_by,
        expires_at=expires_at,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return invitation


# ---------------------------------------------------------
# Read
# ---------------------------------------------------------


def get_organization_invitation_by_id(
    db: Session,
    invitation_id: int,
) -> OrganizationInvitation | None:

    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.id == invitation_id,
        )
        .first()
    )


def get_organization_invitation_by_token(
    db: Session,
    token: str,
) -> OrganizationInvitation | None:

    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.token == token,
        )
        .first()
    )


def get_pending_organization_invitation(
    db: Session,
    organization_id: int,
    email: str,
) -> OrganizationInvitation | None:

    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.status == "pending",
        )
        .first()
    )


def get_organization_invitations(
    db: Session,
    organization_id: int,
):

    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id == organization_id,
        )
        .all()
    )


def get_valid_organization_invitation_by_token(
    db: Session,
    token: str,
) -> OrganizationInvitation | None:

    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.token == token,
            OrganizationInvitation.status == "pending",
        )
        .first()
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------


def update_organization_invitation(
    db: Session,
    invitation: OrganizationInvitation,
) -> OrganizationInvitation:

    db.commit()
    db.refresh(invitation)

    return invitation


# ---------------------------------------------------------
# Delete
# ---------------------------------------------------------


def delete_organization_invitation(
    db: Session,
    invitation: OrganizationInvitation,
):

    db.delete(invitation)
    db.commit()