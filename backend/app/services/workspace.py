from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.crud.organization import get_organization_by_id
from backend.app.crud.workspace import (
    create_workspace,
    delete_workspace,
    get_workspace_by_id,
    get_workspace_by_slug,
    get_workspaces,
    update_workspace,
)
from backend.app.models.workspace import Workspace
from backend.app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
)


class WorkspaceService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    def create_workspace(
        self,
        organization_id: int,
        created_by: int,
        request: WorkspaceCreate,
    ) -> Workspace:

        organization = get_organization_by_id(
            self.db,
            organization_id,
        )

        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )

        existing = get_workspace_by_slug(
            self.db,
            organization_id,
            request.slug,
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workspace slug already exists.",
            )

        return create_workspace(
            db=self.db,
            organization_id=organization_id,
            created_by=created_by,
            workspace=request,
        )

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    def list_workspaces(
        self,
        organization_id: int,
    ):

        return get_workspaces(
            self.db,
            organization_id,
        )

    def get_workspace(
        self,
        workspace_id: int,
    ) -> Workspace:

        workspace = get_workspace_by_id(
            self.db,
            workspace_id,
        )

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        return workspace

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    def update_workspace(
        self,
        workspace_id: int,
        request: WorkspaceUpdate,
    ) -> Workspace:

        workspace = get_workspace_by_id(
            self.db,
            workspace_id,
        )

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        if request.name is not None:
            workspace.name = request.name.strip()

        if request.slug is not None:

            existing = get_workspace_by_slug(
                self.db,
                workspace.organization_id,
                request.slug,
            )

            if (
                existing is not None
                and existing.id != workspace.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Workspace slug already exists.",
                )

            workspace.slug = request.slug.lower().strip()

        if request.description is not None:
            workspace.description = request.description

        return update_workspace(
            self.db,
            workspace,
        )

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    def delete_workspace(
        self,
        workspace_id: int,
    ) -> dict:

        workspace = get_workspace_by_id(
            self.db,
            workspace_id,
        )

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        delete_workspace(
            self.db,
            workspace,
        )

        return {
            "message": "Workspace deleted successfully.",
        }