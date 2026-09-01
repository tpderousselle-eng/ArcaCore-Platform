from backend.app.crud.comment import CommentCRUD


class CommentService:

    def __init__(self, db):
        self.crud = CommentCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()