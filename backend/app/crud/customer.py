from sqlalchemy.orm import Session

from backend.app.models.customer import Customer


class CustomerCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return self.db.query(Customer).filter(Customer.id == item_id).first()

    def list(self):
        return self.db.query(Customer).all()
