"""streaks_usuario + streak XP: daily-access streak and the XP it earns

XP from the streak belongs to no matéria, so xp_eventos.materia_id becomes
nullable, and the allowed motivos gain 'streak_diario'.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "streaks_usuario",
        sa.Column("user_id", sa.String(50), primary_key=True),
        sa.Column("sequencia", sa.Integer(), nullable=False),
        sa.Column("ultimo_dia", sa.Date(), nullable=False),
    )
    op.alter_column("xp_eventos", "materia_id", nullable=True)
    op.drop_constraint("ck_xp_eventos_motivo", "xp_eventos", type_="check")
    op.create_check_constraint(
        "ck_xp_eventos_motivo",
        "xp_eventos",
        "motivo IN ('primeira_tentativa', 'melhoria_de_nota', 'streak_diario')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM xp_eventos WHERE motivo = 'streak_diario'")
    op.drop_constraint("ck_xp_eventos_motivo", "xp_eventos", type_="check")
    op.create_check_constraint(
        "ck_xp_eventos_motivo",
        "xp_eventos",
        "motivo IN ('primeira_tentativa', 'melhoria_de_nota')",
    )
    op.alter_column("xp_eventos", "materia_id", nullable=False)
    op.drop_table("streaks_usuario")
