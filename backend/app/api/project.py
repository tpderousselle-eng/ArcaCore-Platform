from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from backend.app.security.organization_permissions import (
    require_admin,
)
from backend.app.services.project import ProjectService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/projects",
    tags=["Projects"],
)


@router.post(
    "",
    response_model=ProjectResponse,
)
def create_project(
    workspace_id: int,
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = ProjectService(db)

    try:
        return service.create_project(
            workspace_id=workspace_id,
            user_id=current_user.id,
            project=project,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


@router.get(
    "",
    response_model=ProjectListResponse,
)
def list_projects(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = ProjectService(db)

    return {
        "message": "Projects retrieved successfully.",
        "data": service.list_projects(workspace_id),
    }


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    workspace_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = ProjectService(db)

    try:
        return service.get_project(project_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
)
def update_project(
    workspace_id: int,
    project_id: int,
    project: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = ProjectService(db)

    try:
        return service.update_project(
            project_id,
            project,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


@router.delete(
    "/{project_id}",
)
def delete_project(
    workspace_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = ProjectService(db)

    try:
        return service.delete_project(project_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )