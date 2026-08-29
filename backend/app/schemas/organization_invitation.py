from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class OrganizationInvitationCreate(BaseModel):
    email: EmailStr
    role: str


class OrganizationInvitationResponse(BaseModel):
    id: int
    organization_id: int
    email: EmailStr
    role: str
    token: str
    invited_by: int
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OrganizationInvitationListResponse(BaseModel):
    message: str
    data: list[OrganizationInvitationResponse]


class AcceptInvitationRequest(BaseModel):
    token: str