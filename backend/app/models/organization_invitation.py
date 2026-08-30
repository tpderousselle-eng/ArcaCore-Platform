from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String,
        default="member",
    )

    token: Mapped[str] = mapped_column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        default="pending",
    )

    invited_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    organization = relationship(
        "Organization",
        back_populates="invitations",
    )

    inviter = relationship(
        "User",
        foreign_keys=[invited_by],
    )