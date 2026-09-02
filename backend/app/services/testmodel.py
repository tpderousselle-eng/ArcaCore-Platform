from backend.app.crud.testmodel import TestmodelCRUD


class TestmodelService:

    def __init__(self, db):
        self.crud = TestmodelCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()
