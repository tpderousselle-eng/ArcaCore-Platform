from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from backend.app.auth.roles import Role
from backend.app.auth.user_status import UserStatus


# ---------------------------------------------------------
# Requests
# ---------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: str


class UserRoleUpdate(BaseModel):
    role: Role


class UserStatusUpdate(BaseModel):
    status: UserStatus


# ---------------------------------------------------------
# Responses
# ---------------------------------------------------------

class UserSummaryResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    status: UserStatus
    is_verified: bool

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserDetailResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    status: UserStatus
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserListResponse(BaseModel):
    message: str
    data: list[UserSummaryResponse]


class UserResponse(UserDetailResponse):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str