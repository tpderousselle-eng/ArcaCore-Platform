from datetime import datetime, UTC

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    slug = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )

    owner_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    owner = relationship(
        "User",
        foreign_keys=[owner_id],
    )

    members = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    invitations = relationship(
        "OrganizationInvitation",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    workspaces = relationship(
        "Workspace",
        back_populates="organization",
        cascade="all, delete-orphan",
    )