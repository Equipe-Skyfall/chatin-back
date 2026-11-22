"""resumo_aberturas: each time a student opens a study summary (US18)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resumo_aberturas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("resumo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_resumo_aberturas_user_id", "resumo_aberturas", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_resumo_aberturas_user_id", table_name="resumo_aberturas")
    op.drop_table("resumo_aberturas")
