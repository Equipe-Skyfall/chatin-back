"""add resumos_estudo - one study summary per (user, módulo)

Addressable Biblioteca item (RF4/RF5): the structured study-summary template
lives in `conteudo` (JSONB) and is rendered to PDF on demand, so no PDF bytes
are persisted. The `(user_id, modulo_id)` unique constraint is what makes it
"one summary per módulo" - regenerating updates the existing row instead of
inserting a duplicate.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resumos_estudo",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column(
            "modulo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modulos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("materia_nome", sa.String(200), nullable=True),
        sa.Column("tema_titulo", sa.String(200), nullable=True),
        sa.Column("modulo_titulo", sa.String(200), nullable=True),
        sa.Column("conteudo", postgresql.JSONB(), nullable=False),
        sa.Column("modelo_ia", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "modulo_id", name="uq_resumos_estudo_user_modulo"),
    )
    op.create_index("ix_resumos_estudo_user_id", "resumos_estudo", ["user_id"])


def downgrade() -> None:
    op.drop_table("resumos_estudo")
