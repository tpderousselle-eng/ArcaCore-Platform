from backend.app.crud.product import ProductCRUD


class ProductService:

    def __init__(self, db):
        self.crud = ProductCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()
