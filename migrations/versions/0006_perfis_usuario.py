"""add perfis_usuario - local user_id->nome mirror for the ranking display

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "perfis_usuario",
        sa.Column("user_id", sa.String(50), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("perfis_usuario")
