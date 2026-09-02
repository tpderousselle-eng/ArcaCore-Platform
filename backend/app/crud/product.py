from sqlalchemy.orm import Session

from backend.app.models.product import Product


class ProductCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return self.db.query(Product).filter(Product.id == item_id).first()

    def list(self):
        return self.db.query(Product).all()
