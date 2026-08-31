from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from backend.app.security.organization_permissions import (
    require_admin,
    require_member,
)
from backend.app.services.workspace import WorkspaceService

router = APIRouter(
    prefix="/organizations",
    tags=["Workspaces"],
)


# ---------------------------------------------------------
# Create Workspace
# ---------------------------------------------------------


@router.post(
    "/{organization_id}/workspaces",
    response_model=WorkspaceResponse,
    status_code=201,
)
def create_workspace(
    organization_id: int,
    request: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = WorkspaceService(db)

    return service.create_workspace(
        organization_id=organization_id,
        created_by=current_user.id,
        request=request,
    )


# ---------------------------------------------------------
# List Workspaces
# ---------------------------------------------------------


@router.get(
    "/{organization_id}/workspaces",
    response_model=WorkspaceListResponse,
)
def list_workspaces(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_member),
):
    service = WorkspaceService(db)

    workspaces = service.list_workspaces(
        organization_id,
    )

    return {
        "message": "Workspaces retrieved successfully.",
        "data": workspaces,
    }


# ---------------------------------------------------------
# Get Workspace
# ---------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceResponse,
)
def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_member),
):
    service = WorkspaceService(db)

    return service.get_workspace(
        workspace_id,
    )


# ---------------------------------------------------------
# Update Workspace
# ---------------------------------------------------------


@router.put(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceResponse,
)
def update_workspace(
    workspace_id: int,
    request: WorkspaceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = WorkspaceService(db)

    return service.update_workspace(
        workspace_id,
        request,
    )


# ---------------------------------------------------------
# Delete Workspace
# ---------------------------------------------------------


@router.delete(
    "/workspaces/{workspace_id}",
)
def delete_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = WorkspaceService(db)

    return service.delete_workspace(
        workspace_id,
    )