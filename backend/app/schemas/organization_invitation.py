from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


# ---------------------------------------------------------
# Create
# ---------------------------------------------------------


class OrganizationInvitationCreate(BaseModel):
    email: EmailStr
    role: str = "member"


# ---------------------------------------------------------
# Accept Invitation
# ---------------------------------------------------------


class OrganizationInvitationAccept(BaseModel):
    token: str


# ---------------------------------------------------------
# Response
# ---------------------------------------------------------


class OrganizationInvitationResponse(BaseModel):
    id: int
    organization_id: int
    email: EmailStr
    role: str
    status: str
    token: str
    invited_by: int
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ---------------------------------------------------------
# List Response
# ---------------------------------------------------------


class OrganizationInvitationListResponse(BaseModel):
    message: str
    data: list[OrganizationInvitationResponse]