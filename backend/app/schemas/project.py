from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    slug: str
    description: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class ProjectListResponse(BaseModel):
    message: str
    data: list[ProjectResponse]