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


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
    )

    email = Column(
        String,
        nullable=False,
        index=True,
    )

    role = Column(
        String,
        nullable=False,
    )

    token = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )

    invited_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
    )

    accepted_at = Column(
        DateTime,
        nullable=True,
    )

    organization = relationship(
        "Organization",
        back_populates="invitations",
    )

    inviter = relationship(
        "User",
        foreign_keys=[invited_by],
    )