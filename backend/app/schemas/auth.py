from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

   