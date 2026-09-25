import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.tema import STATUS_ERRO, STATUS_GERANDO, STATUS_PRONTO, TEMA_STATUSES

if TYPE_CHECKING:
    from app.models.questionario import Questionario
    from app.models.tema import Tema

MODULO_STATUSES = TEMA_STATUSES  # same vocabulary: 'gerando' | 'pronto' | 'erro'


class Modulo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The real content unit: owns its own teaching material (`conteudo`),
    generated from the tema's shared `fontes` plus this módulo's own
    `descricao` (its focus), followed by its own quiz. `status` reflects both
    generation steps (content, then quiz)."""

    __tablename__ = "modulos"
    __table_args__ = (
        UniqueConstraint("tema_id", "ordem", name="uq_modulos_tema_ordem"),
        CheckConstraint(f"status IN {MODULO_STATUSES}", name="ck_modulos_status"),
    )

    tema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("temas.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_GERANDO)
    conteudo: Mapped[str | None] = mapped_column(Text, nullable=True)
    conteudo_modelo_ia: Mapped[str | None] = mapped_column(String(100), nullable=True)

    tema: Mapped["Tema"] = relationship(back_populates="modulos")
    questionario: Mapped["Questionario | None"] = relationship(
        back_populates="modulo", cascade="all, delete-orphan", uselist=False
    )


__all__ = ["Modulo", "MODULO_STATUSES", "STATUS_GERANDO", "STATUS_PRONTO", "STATUS_ERRO"]
