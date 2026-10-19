"""ia_consumo: one row per AI provider call (RNF7)

No foreign keys on purpose: the usage history must outlive users and
módulos, and the writer (`app/ai/consumo.py`) is best-effort.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ia_consumo",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_id", sa.String(50), nullable=True),
        sa.Column("operacao", sa.String(80), nullable=False),
        sa.Column("modelo", sa.String(80), nullable=True),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("tipo_falha", sa.String(20), nullable=True),
        sa.Column("tokens_entrada", sa.Integer(), nullable=True),
        sa.Column("tokens_saida", sa.Integer(), nullable=True),
        sa.Column("chamadas_modelo", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
    )
    op.create_index("ix_ia_consumo_user_id", "ia_consumo", ["user_id"])
    op.create_index("ix_ia_consumo_created_at", "ia_consumo", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ia_consumo_created_at", table_name="ia_consumo")
    op.drop_index("ix_ia_consumo_user_id", table_name="ia_consumo")
    op.drop_table("ia_consumo")
