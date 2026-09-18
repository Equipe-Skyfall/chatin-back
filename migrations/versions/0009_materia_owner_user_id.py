"""materias: add owner_user_id - lets a student own a personal trilha

`NULL` keeps meaning "global, admin-curated curriculum" (unchanged
behavior); a real `userId` marks a matéria as that student's own personal
trilha. `nome` stops being globally unique and becomes unique only within
its own namespace - a partial unique index for the global case (`owner_user_id
IS NULL`) preserves today's "no two global matérias share a name", and a
composite unique constraint covers "no two of the same student's own
matérias share a name" - the two never collide with each other.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("materias", sa.Column("owner_user_id", sa.String(50), nullable=True))
    op.create_index("ix_materias_owner_user_id", "materias", ["owner_user_id"])

    # Postgres's default name for the inline `unique=True` from 0001's
    # `create_table` is `<table>_<column>_key`.
    op.drop_constraint("materias_nome_key", "materias", type_="unique")

    op.create_index(
        "uq_materias_nome_global",
        "materias",
        ["nome"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL"),
    )
    op.create_unique_constraint("uq_materias_owner_nome", "materias", ["owner_user_id", "nome"])


def downgrade() -> None:
    op.drop_constraint("uq_materias_owner_nome", "materias", type_="unique")
    op.drop_index("uq_materias_nome_global", table_name="materias")
    op.create_unique_constraint("materias_nome_key", "materias", ["nome"])
    op.drop_index("ix_materias_owner_user_id", table_name="materias")
    op.drop_column("materias", "owner_user_id")
