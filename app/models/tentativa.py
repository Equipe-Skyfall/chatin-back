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
    from app.models.tema import Tema

STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDA = "concluida"
TENTATIVA_STATUSES = (STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA)


class Tentativa(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Scoped to exactly one of a módulo's `Questionario` (the normal case) OR
    a whole `Tema` (a review quiz mixing questions from every módulo pool
    under that tema - see `grading_service.iniciar_tentativa_tema`). A
    tema-scoped attempt is graded the same way (grading only ever looks at
    individual `questao_id`s, never a single owning questionário), but is
    practice only: it does NOT update `ProgressoUsuario` or grant XP, since
    it doesn't target one módulo to mark complete.
    """

    __tablename__ = "tentativas"
    __table_args__ = (
        CheckConstraint(f"status IN {TENTATIVA_STATUSES}", name="ck_tentativas_status"),
        CheckConstraint(
            "(questionario_id IS NOT NULL)::int + (tema_id IS NOT NULL)::int = 1",
            name="ck_tentativas_escopo",
        ),
    )

    questionario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questionarios.id", ondelete="CASCADE"), nullable=True
    )
    tema_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("temas.id", ondelete="CASCADE"), nullable=True
    )
    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID, hence plain String rather than the UUID column type.
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_EM_ANDAMENTO)
    pontuacao: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_questoes: Mapped[int] = mapped_column(Integer, nullable=False)
    # True for a módulo-scoped attempt that should NOT count toward
    # progress/XP - today that's only the on-demand personalized quiz (see
    # `questionario_personalizado_service`); a tema-scoped attempt already
    # skips progress/XP unconditionally (it has no single módulo to credit),
    # regardless of this flag.
    pratica: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_corretas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    questionario: Mapped["Questionario | None"] = relationship()
    tema: Mapped["Tema | None"] = relationship()
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
