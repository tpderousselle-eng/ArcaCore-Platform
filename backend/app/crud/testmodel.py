from sqlalchemy.orm import Session

from backend.app.models.testmodel import Testmodel


class TestmodelCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return self.db.query(Testmodel).filter(Testmodel.id == item_id).first()

    def list(self):
        return self.db.query(Testmodel).all()
