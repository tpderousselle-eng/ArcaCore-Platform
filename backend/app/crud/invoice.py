from sqlalchemy.orm import Session

from backend.app.models.invoice import Invoice


class InvoiceCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return self.db.query(Invoice).filter(Invoice.id == item_id).first()

    def list(self):
        return self.db.query(Invoice).all()
