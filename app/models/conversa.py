import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

PAPEL_USUARIO = "user"
PAPEL_ASSISTENTE = "assistant"
PAPEL_FERRAMENTA = "tool"
PAPEIS_VALIDOS = (PAPEL_USUARIO, PAPEL_ASSISTENTE, PAPEL_FERRAMENTA)


class Conversa(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An admin's chat session with the content-creation agent. Scoped to the
    admin who started it (`user_id`, from the JWT) - conversations aren't shared
    across admins."""

    __tablename__ = "conversas"

    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    titulo: Mapped[str | None] = mapped_column(String(200), nullable=True)

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
