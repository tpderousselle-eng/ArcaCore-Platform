"""create organization invitations table

Revision ID: 949493a0347a
Revises: e396e077eaf8
Create Date: 2026-08-30 04:29:23.156215

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "949493a0347a"
down_revision: Union[str, Sequence[str], None] = "e396e077eaf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "organization_invitations",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
    )

    op.alter_column(
        "organization_invitations",
        "status",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "organization_invitations",
        "status",
    )