from pydantic import BaseModel


class TestmodelBase(BaseModel):
    pass


class TestmodelCreate(TestmodelBase):
    pass


class TestmodelUpdate(BaseModel):
    pass


class TestmodelResponse(TestmodelBase):
    id: int

    model_config = {
        "from_attributes": True,
    }
