from sqlalchemy.orm import Session

from backend.app.models.organization_member import OrganizationMember


def create_organization_member(
    db: Session,
    organization_id: int,
    user_id: int,
    role: str = "member",
) -> OrganizationMember:
    membership = OrganizationMember(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()
    db.refresh(membership)

    return membership


def get_organization_member(
    db: Session,
    organization_id: int,
    user_id: int,
) -> OrganizationMember | None:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        .first()
    )


def get_organization_members(
    db: Session,
    organization_id: int,
):
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
        )
        .all()
    )


def delete_organization_member(
    db: Session,
    member: OrganizationMember,
) -> None:
    db.delete(member)
    db.commit()