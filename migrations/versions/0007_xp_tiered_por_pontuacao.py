"""xp_eventos: rename first-completion motivo to first-attempt (tiered rules)

The XP rule changed from "flat bonus on first *pass*" to "tiered amount on
the first *attempt*, pass or fail" - `modulo_concluido_primeira_vez` no
longer describes what's actually being recorded, so both the allowed value
and any existing rows are renamed to `primeira_tentativa`.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_xp_eventos_motivo", "xp_eventos", type_="check")
    op.execute(
        "UPDATE xp_eventos SET motivo = 'primeira_tentativa' "
        "WHERE motivo = 'modulo_concluido_primeira_vez'"
    )
    op.create_check_constraint(
        "ck_xp_eventos_motivo",
        "xp_eventos",
        "motivo IN ('primeira_tentativa', 'melhoria_de_nota')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_xp_eventos_motivo", "xp_eventos", type_="check")
    op.execute(
        "UPDATE xp_eventos SET motivo = 'modulo_concluido_primeira_vez' "
        "WHERE motivo = 'primeira_tentativa'"
    )
    op.create_check_constraint(
        "ck_xp_eventos_motivo",
        "xp_eventos",
        "motivo IN ('modulo_concluido_primeira_vez', 'melhoria_de_nota')",
    )
