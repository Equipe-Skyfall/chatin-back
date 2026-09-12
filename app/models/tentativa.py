import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.gabarito import LETRAS_VALIDAS

if TYPE_CHECKING:
    from app.models.questao import Questao
    from app.models.questionario import Questionario

STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDA = "concluida"
TENTATIVA_STATUSES = (STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA)


class Tentativa(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "tentativas"
    __table_args__ = (
        CheckConstraint(f"status IN {TENTATIVA_STATUSES}", name="ck_tentativas_status"),
    )

    questionario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questionarios.id", ondelete="CASCADE"), nullable=False
    )
    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID, hence plain String rather than the UUID column type.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_EM_ANDAMENTO)
    pontuacao: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_questoes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_corretas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    questionario: Mapped["Questionario"] = relationship()
    questoes_selecionadas: Mapped[list["TentativaQuestao"]] = relationship(
        back_populates="tentativa", cascade="all, delete-orphan", order_by="TentativaQuestao.ordem"
    )
    respostas: Mapped[list["RespostaTentativa"]] = relationship(
        back_populates="tentativa", cascade="all, delete-orphan"
    )


class TentativaQuestao(UUIDPrimaryKeyMixin, Base):
    """Fixes, at attempt-start time, exactly which random subset of the pool
    was shown to the student. Grading and any later review reference this
    table - the sample is never re-drawn.
    """

    __tablename__ = "tentativa_questoes"
    __table_args__ = (
        UniqueConstraint("tentativa_id", "questao_id", name="uq_tentativa_questoes_questao"),
        UniqueConstraint("tentativa_id", "ordem", name="uq_tentativa_questoes_ordem"),
    )

    tentativa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tentativas.id", ondelete="CASCADE"), nullable=False
    )
    questao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questoes.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    tentativa: Mapped["Tentativa"] = relationship(back_populates="questoes_selecionadas")
    questao: Mapped["Questao"] = relationship()


class RespostaTentativa(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "respostas_tentativa"
    __table_args__ = (
        UniqueConstraint("tentativa_id", "questao_id", name="uq_respostas_tentativa_questao"),
        CheckConstraint(f"resposta_escolhida IN {LETRAS_VALIDAS}", name="ck_respostas_letra"),
    )

    tentativa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tentativas.id", ondelete="CASCADE"), nullable=False
    )
    questao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questoes.id", ondelete="CASCADE"), nullable=False
    )
    resposta_escolhida: Mapped[str] = mapped_column(String(1), nullable=False)
    correta: Mapped[bool] = mapped_column(Boolean, nullable=False)

    tentativa: Mapped["Tentativa"] = relationship(back_populates="respostas")
    questao: Mapped["Questao"] = relationship()
