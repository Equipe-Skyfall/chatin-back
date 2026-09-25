import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversa import Conversa
    from app.models.modulo import Modulo


class ResumoEstudo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A student's study summary for one módulo - an addressable library item
    (RF4/RF5), unlike the short per-conversation digest cached in
    `Conversa.resumo`. At most one per (user, módulo): regenerating replaces
    it in place, so the Biblioteca stays a stable "book of summaries" rather
    than accreting duplicates.

    `materia_nome`/`tema_titulo`/`modulo_titulo` are a denormalized snapshot
    taken at generation time, so the Biblioteca can group entries and the PDF
    can render a header without walking the currículo hierarchy on every
    read. `conteudo` holds the structured template (JSON) rendered into the
    PDF on demand - no PDF bytes are stored.
    """

    __tablename__ = "resumos_estudo"
    __table_args__ = (
        UniqueConstraint("user_id", "modulo_id", name="uq_resumos_estudo_user_modulo"),
    )

    # From the external auth service's JWT `userId` claim (a Prisma cuid()
    # string) - same vocabulary as `Conversa.user_id`.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    modulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modulos.id", ondelete="CASCADE"), nullable=False
    )
    # The session that triggered the latest generation, for traceability - kept
    # nullable so a deleted conversation doesn't take the summary down with it.
    conversa_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversas.id", ondelete="SET NULL"), nullable=True
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    materia_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tema_titulo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    modulo_titulo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conteudo: Mapped[dict] = mapped_column(JSONB, nullable=False)
    modelo_ia: Mapped[str | None] = mapped_column(String(100), nullable=True)

    modulo: Mapped["Modulo"] = relationship()
    conversa: Mapped["Conversa | None"] = relationship()
