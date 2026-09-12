"""tentativas: allow a tema-wide review quiz (mixes every módulo pool)

`questionario_id` becomes nullable and a new nullable `tema_id` is added -
exactly one of the two must be set (enforced by a check constraint). A
tema-scoped attempt draws questions across every módulo's pool under that
tema (see `grading_service.iniciar_tentativa_tema`); it's graded normally but
does not update per-módulo progress or XP, since it targets no single módulo.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("tentativas", "questionario_id", nullable=True)
    op.add_column(
        "tentativas",
        sa.Column(
            "tema_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("temas.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_tentativas_escopo",
        "tentativas",
        "(questionario_id IS NOT NULL)::int + (tema_id IS NOT NULL)::int = 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tentativas_escopo", "tentativas", type_="check")
    op.drop_column("tentativas", "tema_id")
    op.alter_column("tentativas", "questionario_id", nullable=False)
