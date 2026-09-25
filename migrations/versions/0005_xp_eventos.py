"""add xp_eventos - append-only XP event log (totals are always summed, never stored)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "xp_eventos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column(
            "materia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materias.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modulo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modulos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "motivo IN ('modulo_concluido_primeira_vez', 'melhoria_de_nota')",
            name="ck_xp_eventos_motivo",
        ),
    )
    op.create_index("ix_xp_eventos_user_id", "xp_eventos", ["user_id"])
    op.create_index("ix_xp_eventos_materia_id", "xp_eventos", ["materia_id"])


def downgrade() -> None:
    op.drop_table("xp_eventos")
