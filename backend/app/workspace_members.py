from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.workspace_member import (
    WorkspaceMemberCreate,
    WorkspaceMemberListResponse,
    WorkspaceMemberResponse,
    WorkspaceMemberRoleUpdate,
)
from backend.app.security.organization_permissions import (
    require_admin,
    require_member,
)
from backend.app.services.workspace_member import (
    WorkspaceMemberService,
)

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspace Members"],
)


# ---------------------------------------------------------
# Add Member
# ---------------------------------------------------------


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
)
def add_member(
    workspace_id: int,
    request: WorkspaceMemberCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = WorkspaceMemberService(db)

    return service.add_member(
        workspace_id,
        request,
    )


# ---------------------------------------------------------
# List Members
# ---------------------------------------------------------


@router.get(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberListResponse,
)
def list_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_member),
):
    service = WorkspaceMemberService(db)

    members = service.list_members(
        workspace_id,
    )

    return {
        "message": "Workspace members retrieved successfully.",
        "data": members,
    }


# ---------------------------------------------------------
# Change Role
# ---------------------------------------------------------


@router.put(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberResponse,
)
def change_role(
    workspace_id: int,
    user_id: int,
    request: WorkspaceMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = WorkspaceMemberService(db)

    return service.change_member_role(
        workspace_id,
        user_id,
        request,
    )


# ---------------------------------------------------------
# Remove Member
# ---------------------------------------------------------


@router.delete(
    "/{workspace_id}/members/{user_id}",
)
def remove_member(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    service = WorkspaceMemberService(db)

    return service.remove_member(
        workspace_id,
        user_id,
    )