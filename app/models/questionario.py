import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.modulo import Modulo
    from app.models.questao import Questao


class Questionario(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The reusable question *pool* for a módulo - generated once, from that
    módulo's own `conteudo`, sampled from per attempt."""

    __tablename__ = "questionarios"

    modulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modulos.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    modelo_ia: Mapped[str] = mapped_column(String(100), nullable=False)

    modulo: Mapped["Modulo"] = relationship(back_populates="questionario")
    questoes: Mapped[list["Questao"]] = relationship(
        back_populates="questionario", cascade="all, delete-orphan", order_by="Questao.ordem"
    )
