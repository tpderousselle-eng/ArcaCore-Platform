from sqlalchemy.orm import Session

from backend.app.models.order import Order


class OrderCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return self.db.query(Order).filter(Order.id == item_id).first()

    def list(self):
        return self.db.query(Order).all()
