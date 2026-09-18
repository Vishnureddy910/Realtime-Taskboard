"""Add prefix index for case-insensitive username search

Revision ID: b41e8d2c7a53
Revises: 7c2b1e4a9f10
Create Date: 2026-09-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b41e8d2c7a53'
down_revision: Union[str, Sequence[str], None] = '7c2b1e4a9f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_users_username_lower_prefix",
        "users",
        [sa.text("lower(username) text_pattern_ops")],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_username_lower_prefix", table_name="users")
