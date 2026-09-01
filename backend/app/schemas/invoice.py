from pydantic import BaseModel


class InvoiceBase(BaseModel):
    pass


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    pass


class InvoiceResponse(InvoiceBase):
    id: int

    model_config = {
        "from_attributes": True,
    }
