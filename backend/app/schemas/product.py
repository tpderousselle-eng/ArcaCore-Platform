from pydantic import BaseModel


class ProductBase(BaseModel):
    pass


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    pass


class ProductResponse(ProductBase):
    id: int

    model_config = {
        "from_attributes": True,
    }
