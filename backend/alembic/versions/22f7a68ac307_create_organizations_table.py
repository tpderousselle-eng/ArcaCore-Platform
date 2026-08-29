"""create organizations table

Revision ID: 22f7a68ac307
Revises: 2bcd447c4596
Create Date: 2026-08-29 03:07:53.235411
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "22f7a68ac307"
down_revision: Union[str, Sequence[str], None] = "2bcd447c4596"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_organizations_id"),
        "organizations",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_organizations_slug"),
        "organizations",
        ["slug"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_organizations_slug"),
        table_name="organizations",
    )

    op.drop_index(
        op.f("ix_organizations_id"),
        table_name="organizations",
    )

    op.drop_table("organizations")