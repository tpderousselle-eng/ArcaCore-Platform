from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.auth.permissions import (
    require_admin,
    require_owner,
)
from backend.app.db.session import get_db
from backend.app.schemas.user import (
    UserDetailResponse,
    UserListResponse,
    UserRoleUpdate,
    UserStatusUpdate,
    UserSummaryResponse,
    UserUpdate,
)
from backend.app.services.user_service import UserService

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/",
    response_model=UserListResponse,
)
def list_users(
    search: Optional[str] = Query(
        default=None,
        description="Search by email or full name",
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = UserService(db)

    users = service.list_users(
        search=search,
        skip=skip,
        limit=limit,
    )

    return {
        "message": "Users retrieved successfully.",
        "data": users,
    }


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = UserService(db)

    return service.get_user(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserDetailResponse,
)
def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = UserService(db)

    return service.update_user(
        user_id=user_id,
        full_name=request.full_name,
    )


@router.patch(
    "/{user_id}/role",
    response_model=UserDetailResponse,
)
def change_role(
    user_id: int,
    request: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_owner),
):
    service = UserService(db)

    return service.change_role(
        user_id=user_id,
        role=request.role.value,
    )


@router.patch(
    "/{user_id}/status",
    response_model=UserDetailResponse,
)
def change_status(
    user_id: int,
    request: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = UserService(db)

    return service.change_status(
        user_id=user_id,
        status_value=request.status,
    )