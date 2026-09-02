from pydantic import BaseModel


class OrderBase(BaseModel):
    pass


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    pass


class OrderResponse(OrderBase):
    id: int

    model_config = {
        "from_attributes": True,
    }
