from backend.app.crud.invoice import InvoiceCRUD


class InvoiceService:

    def __init__(self, db):
        self.crud = InvoiceCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()
