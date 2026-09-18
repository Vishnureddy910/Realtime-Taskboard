"""Add tasks.creator_id, cascading foreign keys, membership uniqueness and lookup indexes

Revision ID: 7c2b1e4a9f10
Revises: d9037960e8de
Create Date: 2026-09-18 12:00:00.000000

Written defensively: databases created before this revision may already have
tasks.creator_id (e.g. added by hand or by metadata.create_all), so the
current schema is inspected instead of assumed.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2b1e4a9f10'
down_revision: Union[str, Sequence[str], None] = 'd9037960e8de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, referenced table, ON DELETE behaviour)
FOREIGN_KEYS = [
    ("tasks", "list_id", "lists", "CASCADE"),
    ("tasks", "creator_id", "users", "SET NULL"),
    ("lists", "board_id", "boards", "CASCADE"),
    ("board_members", "board_id", "boards", "CASCADE"),
    ("board_members", "user_id", "users", "CASCADE"),
]


def _drop_foreign_keys_on(table: str, column: str) -> None:
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk["constrained_columns"] == [column]:
            op.drop_constraint(fk["name"], table, type_="foreignkey")


def _recreate_foreign_key(table: str, column: str, referent: str, ondelete: Union[str, None]) -> None:
    _drop_foreign_keys_on(table, column)
    op.create_foreign_key(f"{table}_{column}_fkey", table, referent, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    """Upgrade schema."""
    task_columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "creator_id" not in task_columns:
        op.add_column("tasks", sa.Column("creator_id", sa.Integer(), nullable=True))

    for table, column, referent, ondelete in FOREIGN_KEYS:
        _recreate_foreign_key(table, column, referent, ondelete)

    # Remove duplicate memberships (keeping the oldest) before enforcing uniqueness
    op.execute(
        """
        DELETE FROM board_members a
        USING board_members b
        WHERE a.board_id = b.board_id AND a.user_id = b.user_id AND a.id > b.id
        """
    )
    op.create_unique_constraint("uq_board_members_board_user", "board_members", ["board_id", "user_id"])

    op.create_index(op.f("ix_tasks_list_id"), "tasks", ["list_id"], unique=False, if_not_exists=True)
    op.create_index(op.f("ix_lists_board_id"), "lists", ["board_id"], unique=False, if_not_exists=True)
    op.create_index(op.f("ix_board_members_user_id"), "board_members", ["user_id"], unique=False, if_not_exists=True)

    # Created by metadata.create_all on older databases; nothing filters by title
    op.drop_index("ix_tasks_title", table_name="tasks", if_exists=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_board_members_user_id"), table_name="board_members")
    op.drop_index(op.f("ix_lists_board_id"), table_name="lists")
    op.drop_index(op.f("ix_tasks_list_id"), table_name="tasks")
    op.drop_constraint("uq_board_members_board_user", "board_members", type_="unique")

    for table, column, referent, _ in FOREIGN_KEYS:
        if (table, column) == ("tasks", "creator_id"):
            continue
        _recreate_foreign_key(table, column, referent, None)

    _drop_foreign_keys_on("tasks", "creator_id")
    op.drop_column("tasks", "creator_id")
