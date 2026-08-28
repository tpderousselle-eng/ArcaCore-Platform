"""add user status

Revision ID: 2bcd447c4596
Revises: be837238bae6
Create Date: 2026-08-28 13:05:48.617323

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2bcd447c4596"
down_revision: Union[str, Sequence[str], None] = "be837238bae6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="active",
        ),
    )

    op.create_index(
        "ix_users_status",
        "users",
        ["status"],
        unique=False,
    )

    op.alter_column(
        "users",
        "status",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_users_status",
        table_name="users",
    )

    op.drop_column(
        "users",
        "status",
    )