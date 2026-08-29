from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrganizationCreate(BaseModel):
    name: str
    slug: str


class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationDetailResponse(OrganizationResponse):
    pass


class OrganizationListResponse(BaseModel):
    message: str
    data: list[OrganizationResponse]