from pydantic import BaseModel


class CustomerBase(BaseModel):
    pass


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    pass


class CustomerResponse(CustomerBase):
    id: int

    model_config = {
        "from_attributes": True,
    }
