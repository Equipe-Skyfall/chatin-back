"""tentativas: add pratica flag (on-demand personalized quizzes don't count
toward progress/XP)

`pratica` defaults to false, preserving today's behavior for every existing
row (a módulo-scoped attempt counts toward progress/XP unless explicitly
marked as practice - see `grading_service`/`questionario_personalizado_service`).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tentativas",
        sa.Column("pratica", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tentativas", "pratica")
