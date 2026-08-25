from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from backend.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True
    )

    full_name: Mapped[str] = mapped_column(
        String(255)
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255)
    )
    role: Mapped[str] = mapped_column(
    String(50),
    default="user"
)

is_active: Mapped[bool] = mapped_column(
    Boolean,
    default=True
)

is_verified: Mapped[bool] = mapped_column(
    Boolean,
    default=False
)

created_at: Mapped[datetime] = mapped_column(
    DateTime,
    server_default=func.now()
)

updated_at: Mapped[datetime] = mapped_column(
    DateTime,
    server_default=func.now(),
    onupdate=func.now()
)