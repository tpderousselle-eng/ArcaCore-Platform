from backend.app.crud.customer import CustomerCRUD


class CustomerService:

    def __init__(self, db):
        self.crud = CustomerCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()
