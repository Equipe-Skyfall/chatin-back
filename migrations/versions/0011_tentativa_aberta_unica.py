"""tentativas: partial unique index enforcing 1 open (em_andamento)
tentativa per user

The 1-open-questionário limit (`grading_service.iniciar_tentativa_com_pool`)
was only a SELECT-then-INSERT check with no DB-level guarantee - two
concurrent requests (e.g. a double-click) could both pass the check and
each insert their own `Tentativa`, ending up with two open ones. This index
makes the invariant atomic: a second concurrent insert now fails at the DB
with a unique-violation, which `grading_service` catches and turns into
"resume the one that won the race" instead of a 500.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_tentativas_uma_aberta_por_usuario"


def upgrade() -> None:
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX_NAME} ON tentativas (user_id) "
        "WHERE status = 'em_andamento'"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
