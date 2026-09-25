"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "materias",
        _uuid_pk(),
        sa.Column("nome", sa.String(200), nullable=False, unique=True),
        sa.Column("descricao", sa.String(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "temas",
        _uuid_pk(),
        sa.Column(
            "materia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materias.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.String(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="gerando"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("materia_id", "ordem", name="uq_temas_materia_ordem"),
        sa.CheckConstraint("status IN ('gerando', 'pronto', 'erro')", name="ck_temas_status"),
    )

    op.create_table(
        "fontes",
        _uuid_pk(),
        sa.Column(
            "tema_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("temas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("tipo", sa.String(30), nullable=False, server_default="busca_automatica"),
        sa.Column("origem", sa.String(), nullable=True),
        sa.Column("conteudo_extraido", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "modulos",
        _uuid_pk(),
        sa.Column(
            "tema_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("temas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.String(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="gerando"),
        sa.Column("conteudo", sa.Text(), nullable=True),
        sa.Column("conteudo_modelo_ia", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tema_id", "ordem", name="uq_modulos_tema_ordem"),
        sa.CheckConstraint("status IN ('gerando', 'pronto', 'erro')", name="ck_modulos_status"),
    )

    op.create_table(
        "questionarios",
        _uuid_pk(),
        sa.Column(
            "modulo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modulos.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("modelo_ia", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "questoes",
        _uuid_pk(),
        sa.Column(
            "questionario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questionarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("alternativas", postgresql.JSONB(), nullable=False),
        sa.Column("explicacao", sa.Text(), nullable=True),
        sa.UniqueConstraint("questionario_id", "ordem", name="uq_questoes_questionario_ordem"),
    )

    op.create_table(
        "gabaritos",
        sa.Column(
            "questao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questoes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("resposta_correta", sa.String(1), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("resposta_correta IN ('A', 'B', 'C', 'D', 'E')", name="ck_gabaritos_letra"),
    )

    op.create_table(
        "tentativas",
        _uuid_pk(),
        sa.Column(
            "questionario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questionarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="em_andamento"),
        sa.Column("pontuacao", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_questoes", sa.Integer(), nullable=False),
        sa.Column("total_corretas", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('em_andamento', 'concluida')", name="ck_tentativas_status"),
    )
    op.create_index("ix_tentativas_user_id", "tentativas", ["user_id"])

    op.create_table(
        "tentativa_questoes",
        _uuid_pk(),
        sa.Column(
            "tentativa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tentativas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "questao_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questoes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tentativa_id", "questao_id", name="uq_tentativa_questoes_questao"),
        sa.UniqueConstraint("tentativa_id", "ordem", name="uq_tentativa_questoes_ordem"),
    )

    op.create_table(
        "respostas_tentativa",
        _uuid_pk(),
        sa.Column(
            "tentativa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tentativas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "questao_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questoes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("resposta_escolhida", sa.String(1), nullable=False),
        sa.Column("correta", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tentativa_id", "questao_id", name="uq_respostas_tentativa_questao"),
        sa.CheckConstraint("resposta_escolhida IN ('A', 'B', 'C', 'D', 'E')", name="ck_respostas_letra"),
    )

    op.create_table(
        "progresso_usuario",
        _uuid_pk(),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column(
            "modulo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("modulos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="disponivel"),
        sa.Column("melhor_pontuacao", sa.Numeric(5, 2), nullable=True),
        sa.Column("tentativas_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "modulo_id", name="uq_progresso_usuario_modulo"),
        sa.CheckConstraint("status IN ('disponivel', 'concluido')", name="ck_progresso_status"),
    )
    op.create_index("ix_progresso_usuario_user_id", "progresso_usuario", ["user_id"])

    op.create_table(
        "conversas",
        _uuid_pk(),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_conversas_user_id", "conversas", ["user_id"])

    op.create_table(
        "mensagens",
        _uuid_pk(),
        sa.Column(
            "conversa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("papel", sa.String(20), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=True),
        sa.Column("chamadas_ferramentas", postgresql.JSONB(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conversa_id", "ordem", name="uq_mensagens_conversa_ordem"),
        sa.CheckConstraint("papel IN ('user', 'assistant', 'tool')", name="ck_mensagens_papel"),
    )


def downgrade() -> None:
    op.drop_table("mensagens")
    op.drop_table("conversas")
    op.drop_table("progresso_usuario")
    op.drop_table("respostas_tentativa")
    op.drop_table("tentativa_questoes")
    op.drop_table("tentativas")
    op.drop_table("gabaritos")
    op.drop_table("questoes")
    op.drop_table("questionarios")
    op.drop_table("modulos")
    op.drop_table("fontes")
    op.drop_table("temas")
    op.drop_table("materias")
