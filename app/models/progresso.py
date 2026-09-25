import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.modulo import Modulo

STATUS_DISPONIVEL = "disponivel"
STATUS_CONCLUIDO = "concluido"
PROGRESSO_STATUSES = (STATUS_DISPONIVEL, STATUS_CONCLUIDO)


class ProgressoUsuario(UUIDPrimaryKeyMixin, Base):
    """Single source of truth for progress - tracked only at módulo granularity.

    Tema-level and matéria-level status/percent-complete are computed by
    rolling this table up (see `ProgressoRepository`), never stored separately,
    so the levels can't drift out of sync with each other.
    """

    __tablename__ = "progresso_usuario"
    __table_args__ = (
        UniqueConstraint("user_id", "modulo_id", name="uq_progresso_usuario_modulo"),
        CheckConstraint(f"status IN {PROGRESSO_STATUSES}", name="ck_progresso_status"),
    )

    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    modulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modulos.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_DISPONIVEL)
    melhor_pontuacao: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tentativas_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    modulo: Mapped["Modulo"] = relationship()
