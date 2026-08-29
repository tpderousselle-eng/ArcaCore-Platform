"""create organization invitations table

Revision ID: e396e077eaf8
Revises: cb19cb1de584
Create Date: 2026-08-29 05:05:52.846859
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e396e077eaf8"
down_revision: Union[str, Sequence[str], None] = "cb19cb1de584"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("invited_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_organization_invitations_email"),
        "organization_invitations",
        ["email"],
        unique=False,
    )

    op.create_index(
        op.f("ix_organization_invitations_id"),
        "organization_invitations",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_organization_invitations_token"),
        "organization_invitations",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_organization_invitations_token"),
        table_name="organization_invitations",
    )

    op.drop_index(
        op.f("ix_organization_invitations_id"),
        table_name="organization_invitations",
    )

    op.drop_index(
        op.f("ix_organization_invitations_email"),
        table_name="organization_invitations",
    )

    op.drop_table("organization_invitations")