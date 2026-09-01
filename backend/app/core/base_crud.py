from typing import Generic, Type, TypeVar

from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseCRUD(Generic[ModelType]):
    def __init__(
        self,
        db: Session,
        model: Type[ModelType],
    ):
        self.db = db
        self.model = model

    def create(
        self,
        **kwargs,
    ) -> ModelType:
        obj = self.model(**kwargs)

        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

        return obj

    def get(
        self,
        obj_id: int,
    ) -> ModelType | None:
        return (
            self.db.query(self.model)
            .filter(self.model.id == obj_id)
            .first()
        )

    def list(
        self,
    ) -> list[ModelType]:
        return (
            self.db.query(self.model)
            .all()
        )

    def update(
        self,
        obj: ModelType,
        **kwargs,
    ) -> ModelType:
        for key, value in kwargs.items():
            if value is not None:
                setattr(obj, key, value)

        self.db.commit()
        self.db.refresh(obj)

        return obj

    def delete(
        self,
        obj: ModelType,
    ) -> None:
        self.db.delete(obj)
        self.db.commit()