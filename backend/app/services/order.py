from backend.app.crud.order import OrderCRUD


class OrderService:

    def __init__(self, db):
        self.crud = OrderCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()
