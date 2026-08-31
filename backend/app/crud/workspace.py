from sqlalchemy.orm import Session

from backend.app.models.workspace import Workspace
from backend.app.schemas.workspace import (
    WorkspaceCreate,
)


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------


def create_workspace(
    db: Session,
    organization_id: int,
    created_by: int,
    workspace: WorkspaceCreate,
) -> Workspace:

    db_workspace = Workspace(
        organization_id=organization_id,
        name=workspace.name.strip(),
        slug=workspace.slug.lower().strip(),
        description=workspace.description,
        created_by=created_by,
    )

    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)

    return db_workspace


# ---------------------------------------------------------
# Read
# ---------------------------------------------------------


def get_workspace_by_id(
    db: Session,
    workspace_id: int,
) -> Workspace | None:

    return (
        db.query(Workspace)
        .filter(
            Workspace.id == workspace_id,
        )
        .first()
    )


def get_workspace_by_slug(
    db: Session,
    organization_id: int,
    slug: str,
) -> Workspace | None:

    return (
        db.query(Workspace)
        .filter(
            Workspace.organization_id == organization_id,
            Workspace.slug == slug.lower().strip(),
        )
        .first()
    )


def get_workspaces(
    db: Session,
    organization_id: int,
):

    return (
        db.query(Workspace)
        .filter(
            Workspace.organization_id == organization_id,
        )
        .order_by(
            Workspace.name,
        )
        .all()
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------


def update_workspace(
    db: Session,
    workspace: Workspace,
) -> Workspace:

    db.commit()
    db.refresh(workspace)

    return workspace


# ---------------------------------------------------------
# Delete
# ---------------------------------------------------------


def delete_workspace(
    db: Session,
    workspace: Workspace,
):

    db.delete(workspace)
    db.commit()