"""allow modulo_id to be NULL in resumos_estudo (free-conversation summaries)

Module-scoped summaries keep modulo_id NOT NULL; free-conversation summaries
have modulo_id=NULL and are keyed by (user_id, conversa_id) instead.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "resumos_estudo",
        "modulo_id",
        existing_type=op.f("modulos.id").type,
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM resumos_estudo WHERE modulo_id IS NULL")
    op.alter_column(
        "resumos_estudo",
        "modulo_id",
        existing_type=op.f("modulos.id").type,
        nullable=False,
    )
