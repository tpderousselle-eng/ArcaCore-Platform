from sqlalchemy.orm import Session


class BaseService:
    """
    Base service that provides a CRUD instance.

    Child services must define:

        crud_class = MyCRUD
    """

    crud_class = None

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

        if self.crud_class is None:
            raise NotImplementedError(
                "crud_class must be defined."
            )

        self.crud = self.crud_class(db)