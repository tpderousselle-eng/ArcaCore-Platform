from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------


class WorkspaceCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100,
    )

    slug: str = Field(
        min_length=2,
        max_length=100,
    )

    description: str | None = Field(
        default=None,
        max_length=500,
    )


# ---------------------------------------------------------
# Update
# ---------------------------------------------------------


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    description: str | None = Field(
        default=None,
        max_length=500,
    )


# ---------------------------------------------------------
# Response
# ---------------------------------------------------------


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    organization_id: int
    name: str
    slug: str
    description: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class WorkspaceDetailResponse(BaseModel):
    message: str
    data: WorkspaceResponse


class WorkspaceListResponse(BaseModel):
    message: str
    data: list[WorkspaceResponse]