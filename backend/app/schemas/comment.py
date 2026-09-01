from pydantic import BaseModel


class CommentBase(BaseModel):
    pass


class CommentCreate(CommentBase):
    pass


class CommentUpdate(BaseModel):
    pass


class CommentResponse(CommentBase):
    id: int

    model_config = {
        "from_attributes": True,
    }