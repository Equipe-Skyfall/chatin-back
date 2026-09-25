import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.gabarito import Gabarito
    from app.models.questionario import Questionario


class Questao(UUIDPrimaryKeyMixin, Base):
    """`personalizada=True` marks a questão generated on demand by the
    student-triggered personalized quiz (grounded in that student's own
    conversation text) rather than the admin's own pool generation. It still
    lives in the same `Questionario` as the admin's questões (reused across
    students, cutting AI cost) but is structurally excluded from any pool a
    grade depends on - see `QuestionarioRepository.get_questao_ids_pool_graduavel`
    and `get_questao_ids_pool_por_tema` - so a student can never prompt-inject
    a question that ends up graded for anyone, themselves included."""

    __tablename__ = "questoes"
    __table_args__ = (
        UniqueConstraint("questionario_id", "ordem", name="uq_questoes_questionario_ordem"),
    )

    questionario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questionarios.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"letra": "A", "texto": "..."}, ...] x5 - immutable, always fetched together,
    # never queried independently: a join table would add cost with no query benefit.
    alternativas: Mapped[list] = mapped_column(JSONB, nullable=False)
    explicacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    personalizada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    questionario: Mapped["Questionario"] = relationship(back_populates="questoes")
    gabarito: Mapped["Gabarito"] = relationship(
        back_populates="questao", cascade="all, delete-orphan", uselist=False
    )
