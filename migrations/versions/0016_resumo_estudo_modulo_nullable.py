"""resumos_estudo: allow modulo_id to be NULL (free-conversation summaries)

Module-scoped summaries keep one row per (user_id, modulo_id). A summary of a
conversation with no módulo has modulo_id NULL, and is keyed by
(user_id, conversa_id) instead - the existing unique constraint can't enforce that
(NULLs never collide), so a partial unique index does.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_resumos_estudo_user_conversa_livre"


def upgrade() -> None:
    op.alter_column(
        "resumos_estudo",
        "modulo_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX_NAME} ON resumos_estudo (user_id, conversa_id) "
        "WHERE modulo_id IS NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
    # Free-conversation summaries have no módulo to point at, so they can't survive.
    op.execute("DELETE FROM resumos_estudo WHERE modulo_id IS NULL")
    op.alter_column(
        "resumos_estudo",
        "modulo_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
