from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )

    full_name = Column(
        String,
        nullable=False,
    )

    hashed_password = Column(
        String,
        nullable=False,
    )

    role = Column(
        String,
        default="user",
        nullable=False,
    )

    status = Column(
        String,
        default="active",
        nullable=False,
        index=True,
    )

    is_verified = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    verification_token = Column(
        String,
        nullable=True,
    )

    verification_token_expires = Column(
        DateTime,
        nullable=True,
    )

    password_reset_token = Column(
        String,
        nullable=True,
    )

    password_reset_token_expires = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    organization_members = relationship(
        "OrganizationMember",
        back_populates="user",
    )