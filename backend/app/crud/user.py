from sqlalchemy.orm import Session

from backend.app.models.user import User


class UserCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return self.db.query(User).filter(User.id == item_id).first()

    def list(self):
        return self.db.query(User).all()
