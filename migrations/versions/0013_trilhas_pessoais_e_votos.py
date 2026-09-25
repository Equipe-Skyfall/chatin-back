"""materias: add owner_user_id (student-owned, publicly votable trilhas) +
votos_materia table

`owner_user_id` is `NULL` for the global, admin-curated curriculum (unchanged
meaning/behavior) - a real `userId` marks a matéria as a student's own
trilha, publicly visible and votable by every student (unlike the earlier,
fully-reverted `trilhas-pessoais` feature, which made owned content visible
only to its owner - see migration 0009 in git history, deleted in this same
line of work). `nome` stops being globally unique and becomes unique only
within its own namespace: a partial unique index for the global case
(`owner_user_id IS NULL`) preserves "no two global matérias share a name",
and a composite unique constraint covers "no two of the same student's own
matérias share a name" - the two never collide with each other.

`votos_materia` is the only quality signal on fully-open, unmoderated
student-created content - one row per (user, matéria), `valor` always `+1`/
`-1`, upserted (never more than one vote per student per matéria). Voting on
global content is rejected at the service layer (`voto_service`), not here.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("materias", sa.Column("owner_user_id", sa.String(50), nullable=True))
    op.create_index("ix_materias_owner_user_id", "materias", ["owner_user_id"])
    op.drop_constraint("materias_nome_key", "materias", type_="unique")
    op.create_index(
        "uq_materias_nome_global",
        "materias",
        ["nome"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL"),
    )
    op.create_unique_constraint("uq_materias_owner_nome", "materias", ["owner_user_id", "nome"])

    op.create_table(
        "votos_materia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column(
            "materia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materias.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("valor", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("valor IN (-1, 1)", name="ck_votos_materia_valor"),
        sa.UniqueConstraint("user_id", "materia_id", name="uq_votos_materia_user_materia"),
    )
    op.create_index("ix_votos_materia_user_id", "votos_materia", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_votos_materia_user_id", table_name="votos_materia")
    op.drop_table("votos_materia")

    op.drop_constraint("uq_materias_owner_nome", "materias", type_="unique")
    op.drop_index("uq_materias_nome_global", table_name="materias")
    op.drop_index("ix_materias_owner_user_id", table_name="materias")
    op.create_unique_constraint("materias_nome_key", "materias", ["nome"])
    op.drop_column("materias", "owner_user_id")
