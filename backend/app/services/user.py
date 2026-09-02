from backend.app.crud.user import UserCRUD


class UserService:

    def __init__(self, db):
        self.crud = UserCRUD(db)

    def get(self, item_id: int):
        return self.crud.get(item_id)

    def list(self):
        return self.crud.list()
