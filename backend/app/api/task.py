from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from backend.app.security.project_permissions import (
    require_project_admin,
)
from backend.app.services.task import TaskService

router = APIRouter(
    prefix="/projects/{project_id}/tasks",
    tags=["Tasks"],
)


@router.post(
    "",
    response_model=TaskResponse,
    status_code=201,
)
def create_task(
    project_id: int,
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_project_admin),
):
    service = TaskService(db)

    try:
        return service.create_task(
            project_id=project_id,
            user_id=current_user.id,
            task=task,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


@router.get(
    "",
    response_model=TaskListResponse,
)
def list_tasks(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_project_admin),
):
    service = TaskService(db)

    return {
        "message": "Tasks retrieved successfully.",
        "data": service.list_tasks(project_id),
    }


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
)
def get_task(
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_project_admin),
):
    service = TaskService(db)

    try:
        return service.get_task(task_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
)
def update_task(
    project_id: int,
    task_id: int,
    task: TaskUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_project_admin),
):
    service = TaskService(db)

    try:
        return service.update_task(
            task_id,
            task,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


@router.delete(
    "/{task_id}",
)
def delete_task(
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_project_admin),
):
    service = TaskService(db)

    try:
        return service.delete_task(task_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )