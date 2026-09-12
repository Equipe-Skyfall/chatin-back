import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.models.questao import Questao

LETRAS_VALIDAS = ("A", "B", "C", "D", "E")


class Gabarito(CreatedAtMixin, Base):
    """Kept as its own 1:1 table, deliberately separate from `questoes`, so the
    correct-answer index is never joined/selected by any code path that serves
    questions to a student. Only `grading_service` reads this table.
    """

    __tablename__ = "gabaritos"
    __table_args__ = (
        CheckConstraint(f"resposta_correta IN {LETRAS_VALIDAS}", name="ck_gabaritos_letra"),
    )

    questao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questoes.id", ondelete="CASCADE"), primary_key=True
    )
    resposta_correta: Mapped[str] = mapped_column(String(1), nullable=False)

    questao: Mapped["Questao"] = relationship(back_populates="gabarito")
