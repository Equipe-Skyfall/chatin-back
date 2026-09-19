from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tema import Tema


class Materia(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Matérias (Matemática, Física, ...) are siblings, not a sequence - there is
    no `ordem` here on purpose. Ordering only starts to matter one level down,
    where a tema like 'Álgebra Linear' can genuinely depend on 'Cálculo 1'
    coming first (see `Tema.ordem` / `Modulo.ordem`)."""

    __tablename__ = "materias"

    nome: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)

    temas: Mapped[list["Tema"]] = relationship(
        back_populates="materia", cascade="all, delete-orphan", order_by="Tema.ordem"
    )
