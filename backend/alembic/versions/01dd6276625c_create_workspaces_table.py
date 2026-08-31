"""create workspaces table

Revision ID: 01dd6276625c
Revises: 949493a0347a
Create Date: 2026-08-31 04:01:10.132657

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "01dd6276625c"
down_revision: Union[str, Sequence[str], None] = "949493a0347a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_workspaces_id"),
        "workspaces",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_workspaces_slug"),
        "workspaces",
        ["slug"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_workspaces_slug"),
        table_name="workspaces",
    )

    op.drop_index(
        op.f("ix_workspaces_id"),
        table_name="workspaces",
    )

    op.drop_table("workspaces")