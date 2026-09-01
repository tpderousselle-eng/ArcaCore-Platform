from sqlalchemy.orm import Session

from backend.app.models.workspace_member import WorkspaceMember


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------


def create_workspace_member(
    db: Session,
    workspace_id: int,
    user_id: int,
    role: str,
) -> WorkspaceMember:

    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
    )

    db.add(member)
    db.commit()
    db.refresh(member)

    return member


# ---------------------------------------------------------
# Read
# ---------------------------------------------------------


def get_workspace_member(
    db: Session,
    workspace_id: int,
    user_id: int,
) -> WorkspaceMember | None:

    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )


def get_workspace_members(
    db: Session,
    workspace_id: int,
):

    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
        )
        .all()
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------


def update_workspace_member(
    db: Session,
    member: WorkspaceMember,
) -> WorkspaceMember:

    db.commit()
    db.refresh(member)

    return member


# ---------------------------------------------------------
# Delete
# ---------------------------------------------------------


def delete_workspace_member(
    db: Session,
    member: WorkspaceMember,
):

    db.delete(member)
    db.commit()