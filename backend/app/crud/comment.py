from sqlalchemy.orm import Session

from backend.app.models.comment import Comment


class CommentCRUD:

    def __init__(self, db: Session):
        self.db = db

    def get(self, item_id: int):
        return (
            self.db.query(Comment)
            .filter(Comment.id == item_id)
            .first()
        )

    def list(self):
        return (
            self.db.query(Comment)
            .all()
        )