from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------


class WorkspaceMemberCreate(BaseModel):
    user_id: int

    role: str = Field(
        default="member",
        min_length=3,
        max_length=20,
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------


class WorkspaceMemberRoleUpdate(BaseModel):
    role: str = Field(
        min_length=3,
        max_length=20,
    )


# ---------------------------------------------------------
# Response
# ---------------------------------------------------------


class WorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    workspace_id: int
    user_id: int
    role: str
    created_at: datetime


class WorkspaceMemberDetailResponse(BaseModel):
    message: str
    data: WorkspaceMemberResponse


class WorkspaceMemberListResponse(BaseModel):
    message: str
    data: list[WorkspaceMemberResponse]