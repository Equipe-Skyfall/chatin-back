"""remove materias.ordem - subjects are siblings, not a sequence

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("materias", "ordem")


def downgrade() -> None:
    op.add_column("materias", sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"))
