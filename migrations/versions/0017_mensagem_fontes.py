"""mensagens: web sources that grounded an assistant reply (US-10)

`fontes` holds the pages the chat's web search cited for that reply;
`pergunta_id` points at the user message that prompted the search.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mensagens", sa.Column("fontes", postgresql.JSONB(), nullable=True))
    op.add_column(
        "mensagens",
        sa.Column("pergunta_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mensagens_pergunta_id",
        "mensagens",
        "mensagens",
        ["pergunta_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_mensagens_pergunta_id", "mensagens", type_="foreignkey")
    op.drop_column("mensagens", "pergunta_id")
    op.drop_column("mensagens", "fontes")
