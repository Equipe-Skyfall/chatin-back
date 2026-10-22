"""trilhas_estudando: community trilhas a student chose to study

Only adoptions are stored; the global curriculum and a student's own trilhas
are implicit (see `app/models/trilha_estudando.py`).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trilhas_estudando",
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
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "materia_id", name="uq_trilha_estudando"),
    )
    op.create_index("ix_trilhas_estudando_user_id", "trilhas_estudando", ["user_id"])
    op.create_index("ix_trilhas_estudando_materia_id", "trilhas_estudando", ["materia_id"])


def downgrade() -> None:
    op.drop_index("ix_trilhas_estudando_materia_id", table_name="trilhas_estudando")
    op.drop_index("ix_trilhas_estudando_user_id", table_name="trilhas_estudando")
    op.drop_table("trilhas_estudando")
