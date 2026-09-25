import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

MOTIVO_PRIMEIRA_TENTATIVA = "primeira_tentativa"
MOTIVO_MELHORIA_NOTA = "melhoria_de_nota"
MOTIVOS_VALIDOS = (MOTIVO_PRIMEIRA_TENTATIVA, MOTIVO_MELHORIA_NOTA)


class XpEvento(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One XP-granting event - never a running counter. Like `ProgressoUsuario`'s
    matéria/tema rollups, a user's XP total (global or per-matéria) is always
    computed by summing this table (see `XpRepository`), so it can't drift out
    of sync or double-count. Kept append-only: nothing here is ever updated,
    only inserted."""

    __tablename__ = "xp_eventos"
    __table_args__ = (CheckConstraint(f"motivo IN {MOTIVOS_VALIDOS}", name="ck_xp_eventos_motivo"),)

    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    materia_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materias.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modulo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modulos.id", ondelete="SET NULL"), nullable=True
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str] = mapped_column(String(40), nullable=False)
