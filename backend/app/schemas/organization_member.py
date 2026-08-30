from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrganizationMemberCreate(BaseModel):
    user_id: int
    role: str = "member"


class OrganizationMemberRoleUpdate(BaseModel):
    role: str


class OrganizationMemberResponse(BaseModel):
    id: int
    organization_id: int
    user_id: int
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationMemberListResponse(BaseModel):
    message: str
    data: list[OrganizationMemberResponse]