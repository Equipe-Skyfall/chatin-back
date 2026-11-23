"""resumos_aluno: per-student running summary of the chat history

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resumos_aluno",
        sa.Column("user_id", sa.String(50), primary_key=True),
        sa.Column("resumo", sa.Text(), nullable=False),
        sa.Column(
            "mensagens_resumidas",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("resumos_aluno")
