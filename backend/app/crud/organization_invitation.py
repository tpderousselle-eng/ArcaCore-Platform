from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.organization_invitation import OrganizationInvitation


def create_invitation(
    db: Session,
    invitation: OrganizationInvitation,
) -> OrganizationInvitation:
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def list_pending_invitations(
    db: Session,
    organization_id: int,
) -> list[OrganizationInvitation]:
    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.accepted_at.is_(None),
        )
        .all()
    )


def get_invitation_by_token(
    db: Session,
    token: str,
) -> OrganizationInvitation | None:
    return (
        db.query(OrganizationInvitation)
        .filter(OrganizationInvitation.token == token)
        .first()
    )


def accept_invitation(
    db: Session,
    invitation: OrganizationInvitation,
) -> OrganizationInvitation:
    invitation.accepted_at = datetime.utcnow()

    db.commit()
    db.refresh(invitation)

    return invitation