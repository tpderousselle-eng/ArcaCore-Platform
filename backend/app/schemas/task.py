from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    slug: str
    description: str | None = None
    assigned_to: int | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assigned_to: int | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    parent_task_id: int | None
    title: str
    slug: str
    description: str | None
    status: str
    priority: str
    created_by: int
    assigned_to: int | None
    start_date: datetime | None
    due_date: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class TaskListResponse(BaseModel):
    message: str
    data: list[TaskResponse]