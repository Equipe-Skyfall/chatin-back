"""add conversas.tipo/modulo_id/resumo - student chat + summaries

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversas", sa.Column("tipo", sa.String(20), nullable=False, server_default="admin")
    )
    op.create_check_constraint(
        "ck_conversas_tipo", "conversas", "tipo IN ('admin', 'aluno')"
    )
    op.add_column(
        "conversas",
        sa.Column(
            "modulo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modulos.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("conversas", sa.Column("resumo", sa.Text(), nullable=True))
    op.add_column(
        "conversas", sa.Column("resumo_gerado_em", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversas", "resumo_gerado_em")
    op.drop_column("conversas", "resumo")
    op.drop_column("conversas", "modulo_id")
    op.drop_constraint("ck_conversas_tipo", "conversas", type_="check")
    op.drop_column("conversas", "tipo")
