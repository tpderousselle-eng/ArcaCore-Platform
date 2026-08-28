"""add_password_reset_fields

Revision ID: be837238bae6
Revises: d411d6c94172
Create Date: 2026-08-25 23:55:29.960950

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "be837238bae6"
down_revision: Union[str, Sequence[str], None] = "d411d6c94172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "users",
        sa.Column(
            "password_reset_token",
            sa.String(),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "password_reset_token_expires",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "users",
        "password_reset_token_expires",
    )

    op.drop_column(
        "users",
        "password_reset_token",
    )