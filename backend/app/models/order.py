from enum import Enum


from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Enum as SQLEnum,
    func,
)


from backend.app.db.base import Base


class OrderStatus(str, Enum):

    PENDING = "Pending"

    PROCESSING = "Processing"

    COMPLETED = "Completed"


class Order(Base):
    __tablename__ = "orders"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    status = Column(
        SQLEnum(OrderStatus),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
