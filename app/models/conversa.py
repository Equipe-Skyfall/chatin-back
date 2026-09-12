import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.modulo import Modulo

PAPEL_USUARIO = "user"
PAPEL_ASSISTENTE = "assistant"
PAPEL_FERRAMENTA = "tool"
PAPEIS_VALIDOS = (PAPEL_USUARIO, PAPEL_ASSISTENTE, PAPEL_FERRAMENTA)

TIPO_ADMIN = "admin"
TIPO_ALUNO = "aluno"
TIPOS_VALIDOS = (TIPO_ADMIN, TIPO_ALUNO)


class Conversa(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A chat session, either an admin's session with the content-creation
    agent (`tipo="admin"`) or a student's Q&A session with the virtual
    teacher (`tipo="aluno"`). Scoped to the user who started it - never shared
    across users, and the two types never mix in a listing.

    A student conversation may be scoped to a módulo (`modulo_id`) - the
    student opened the chat while studying it, so the teacher grounds its
    answers in that módulo's content. `resumo`/`resumo_gerado_em` cache a
    generated summary of the conversation so far - regenerated lazily
    whenever it's read and stale (see `chat_aluno_service`), not on every
    message, to avoid an AI call per turn.
    """

    __tablename__ = "conversas"
    __table_args__ = (CheckConstraint(f"tipo IN {TIPOS_VALIDOS}", name="ck_conversas_tipo"),)

    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    titulo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, server_default=TIPO_ADMIN)
    modulo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modulos.id", ondelete="SET NULL"), nullable=True
    )
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_gerado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    modulo: Mapped["Modulo | None"] = relationship()
    mensagens: Mapped[list["Mensagem"]] = relationship(
        back_populates="conversa", cascade="all, delete-orphan", order_by="Mensagem.ordem"
    )


class Mensagem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One turn in a conversation. `chamadas_ferramentas` records any tool
    calls requested/executed as part of this message (name, arguments, and
    result), so the conversation is a transparent audit trail of what the
    agent actually did - not just what it said."""

    __tablename__ = "mensagens"
    __table_args__ = (
        UniqueConstraint("conversa_id", "ordem", name="uq_mensagens_conversa_ordem"),
        CheckConstraint(f"papel IN {PAPEIS_VALIDOS}", name="ck_mensagens_papel"),
    )

    conversa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversas.id", ondelete="CASCADE"), nullable=False
    )
    papel: Mapped[str] = mapped_column(String(20), nullable=False)
    conteudo: Mapped[str | None] = mapped_column(Text, nullable=True)
    chamadas_ferramentas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    conversa: Mapped["Conversa"] = relationship(back_populates="mensagens")
