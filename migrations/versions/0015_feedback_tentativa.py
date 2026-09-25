"""feedback de tentativa via IA

`tentativas`: new `feedback` column for the best-effort AI feedback text on a
módulo conclusion attempt's wrong answers (see `feedback_tentativa_service`).

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tentativas", sa.Column("feedback", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tentativas", "feedback")
