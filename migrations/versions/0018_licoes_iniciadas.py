"""licoes_iniciadas: per-student flag that the módulo's opening lesson was given

A row means `start_lesson` is true for that (user, módulo) and unlocks the
módulo's quiz. Students who already studied (progress or a módulo chat) are
backfilled so they are not locked out.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-14

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
        "licoes_iniciadas",
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
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "modulo_id", name="uq_licao_iniciada_modulo"),
    )
    op.create_index("ix_licoes_iniciadas_user_id", "licoes_iniciadas", ["user_id"])

    op.execute(
        """
        INSERT INTO licoes_iniciadas (user_id, modulo_id)
        SELECT user_id, modulo_id FROM progresso_usuario
        UNION
        SELECT user_id, modulo_id FROM conversas
        WHERE tipo = 'aluno' AND modulo_id IS NOT NULL AND user_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_licoes_iniciadas_user_id", table_name="licoes_iniciadas")
    op.drop_table("licoes_iniciadas")
