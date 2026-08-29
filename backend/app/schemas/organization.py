from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------
# Requests
# ---------------------------------------------------------

class OrganizationCreate(BaseModel):
    name: str
    slug: str


class OrganizationUpdate(BaseModel):
    name: str


# ---------------------------------------------------------
# Responses
# ---------------------------------------------------------

class OrganizationSummaryResponse(BaseModel):
    id: int
    name: str
    slug: str
    owner_id: int

    model_config = ConfigDict(
        from_attributes=True,
    )


class OrganizationDetailResponse(BaseModel):
    id: int
    name: str
    slug: str
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class OrganizationListResponse(BaseModel):
    message: str
    data: list[OrganizationSummaryResponse]


class OrganizationResponse(OrganizationDetailResponse):
    pass