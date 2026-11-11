"""perfis_usuario.apelido - the name the ranking shows instead of the real one

Case-insensitive unique, so "Ana" and "ana" cannot both exist.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("perfis_usuario", sa.Column("apelido", sa.String(20), nullable=True))
    op.create_index(
        "uq_perfis_usuario_apelido_lower",
        "perfis_usuario",
        [sa.text("lower(apelido)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_perfis_usuario_apelido_lower", table_name="perfis_usuario")
    op.drop_column("perfis_usuario", "apelido")
