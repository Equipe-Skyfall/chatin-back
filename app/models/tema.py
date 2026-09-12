import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.fonte import Fonte
    from app.models.materia import Materia
    from app.models.modulo import Modulo

STATUS_GERANDO = "gerando"
STATUS_PRONTO = "pronto"
STATUS_ERRO = "erro"
TEMA_STATUSES = (STATUS_GERANDO, STATUS_PRONTO, STATUS_ERRO)


class Tema(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Pure grouping node - no content of its own. `status` reflects whether
    source search (`fontes`) has completed; the actual teaching content and
    quiz live one level down, on `Modulo`, which reuses these `fontes` rather
    than re-searching per módulo."""

    __tablename__ = "temas"
    __table_args__ = (
        UniqueConstraint("materia_id", "ordem", name="uq_temas_materia_ordem"),
        CheckConstraint(f"status IN {TEMA_STATUSES}", name="ck_temas_status"),
    )

    materia_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materias.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_GERANDO)
    # Admin-supplied free-text steering for the AI (e.g. "explique com exemplos
    # práticos", "foque em aplicações do ENEM") - fed into source search, every
    # módulo's content generation under this tema, and the auto-split planner.
    direcionamento: Mapped[str | None] = mapped_column(Text, nullable=True)

    materia: Mapped["Materia"] = relationship(back_populates="temas")
    fontes: Mapped[list["Fonte"]] = relationship(
        back_populates="tema", cascade="all, delete-orphan"
    )
    modulos: Mapped[list["Modulo"]] = relationship(
        back_populates="tema", cascade="all, delete-orphan", order_by="Modulo.ordem"
    )
