"""penalidade de XP por reprovação + config admin + feedback de tentativa

- `xp_eventos`: allows the new `reprovacao_final` motivo - a failing módulo
  conclusion attempt records a negative `quantidade` (penalty) instead of
  earning XP.
- `configuracoes_sistema`: new single-row table of admin-editable settings
  (today only `xp_penalidade_reprovacao`), seeded with the default.
- `tentativas`: new `feedback` column for the best-effort AI feedback text.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_xp_eventos_motivo", "xp_eventos", type_="check")
    op.create_check_constraint(
        "ck_xp_eventos_motivo",
        "xp_eventos",
        "motivo IN ('primeira_tentativa', 'melhoria_de_nota', 'reprovacao_final')",
    )

    op.create_table(
        "configuracoes_sistema",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "xp_penalidade_reprovacao", sa.Integer(), nullable=False, server_default="20"
        ),
        sa.CheckConstraint("id = 1", name="ck_configuracoes_sistema_singleton"),
    )
    op.execute(
        "INSERT INTO configuracoes_sistema (id, xp_penalidade_reprovacao) VALUES (1, 20) "
        "ON CONFLICT (id) DO NOTHING"
    )

    op.add_column("tentativas", sa.Column("feedback", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tentativas", "feedback")
    op.drop_table("configuracoes_sistema")

    # The old check constraint doesn't allow `reprovacao_final`, so any
    # penalty events recorded meanwhile have to go before it's restored.
    op.execute("DELETE FROM xp_eventos WHERE motivo = 'reprovacao_final'")
    op.drop_constraint("ck_xp_eventos_motivo", "xp_eventos", type_="check")
    op.create_check_constraint(
        "ck_xp_eventos_motivo",
        "xp_eventos",
        "motivo IN ('primeira_tentativa', 'melhoria_de_nota')",
    )
