"""conversas: long-term memory (pgvector) - memoria_chave/memoria_embedding/
memoria_gerada_em

Enables the `vector` extension and adds the columns for the per-conversa
long-term memory (an IA extraction of key facts, not the narrative `resumo`)
used to semantically retrieve a student's own past conversations about the
same módulo - see `app/services/memoria_longo_prazo_service.py`. All three
columns are nullable and lazily populated, same pattern as
`resumo`/`resumo_gerado_em` - existing rows are unaffected.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("conversas", sa.Column("memoria_chave", sa.Text(), nullable=True))
    op.add_column(
        "conversas", sa.Column("memoria_embedding", Vector(EMBEDDING_DIM), nullable=True)
    )
    op.add_column(
        "conversas",
        sa.Column("memoria_gerada_em", sa.DateTime(timezone=True), nullable=True),
    )
    # ivfflat needs at least some rows to build meaningful lists, but is safe
    # to create empty - it'll just start as one big list until re-indexed.
    # Cosine distance (`vector_cosine_ops`) matches the `<=>` operator used
    # by `ConversaRepository.buscar_memorias_similares`.
    op.execute(
        "CREATE INDEX ix_conversas_memoria_embedding ON conversas "
        "USING ivfflat (memoria_embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_conversas_memoria_embedding")
    op.drop_column("conversas", "memoria_gerada_em")
    op.drop_column("conversas", "memoria_embedding")
    op.drop_column("conversas", "memoria_chave")
