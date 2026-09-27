import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.questionario import Questionario
from app.models.tentativa import (
    STATUS_CONCLUIDA,
    STATUS_EM_ANDAMENTO,
    RespostaTentativa,
    Tentativa,
    TentativaQuestao,
)
from app.repositories.base import SqlAlchemyRepository


class TentativaRepository(SqlAlchemyRepository[Tentativa]):
    model = Tentativa

    def get_questionario_aberto_by_user(self, user_id: str) -> Tentativa | None:
        """The student's single open (unfinished) questionário, if any -
        regardless of scope (módulo, tema-review, or personalized), and
        regardless of whether the student ever comes back to finish it.
        `grading_service` resumes it only when the quiz being started has the
        same scope (see `grading_service.mesmo_escopo`); otherwise it is
        discarded (`descartar`) to make room, since the partial unique index
        allows one open attempt per student."""
        stmt = (
            select(Tentativa)
            .where(Tentativa.user_id == user_id, Tentativa.status == STATUS_EM_ANDAMENTO)
            .options(selectinload(Tentativa.questoes_selecionadas))
            .order_by(Tentativa.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def descartar(self, tentativa: Tentativa) -> None:
        """Deletes an unfinished attempt (and its sampled questões) and flushes,
        so the partial unique index is free for the attempt that replaces it."""
        self.delete(tentativa)
        self.flush()

    def add_tentativa_questoes(self, itens: list[TentativaQuestao]) -> None:
        self.db.add_all(itens)

    def get_tentativa_questao_ids(self, tentativa_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(TentativaQuestao.questao_id).where(
            TentativaQuestao.tentativa_id == tentativa_id
        )
        return set(self.db.execute(stmt).scalars().all())

    def add_respostas(self, respostas: list[RespostaTentativa]) -> None:
        self.db.add_all(respostas)

    def marcar_concluida(self, tentativa: Tentativa, pontuacao: float, total_corretas: int) -> None:
        tentativa.status = "concluida"
        tentativa.pontuacao = pontuacao
        tentativa.total_corretas = total_corretas

    def definir_feedback(self, tentativa: Tentativa, feedback: str | None) -> None:
        """Persists the best-effort AI feedback (see `feedback_tentativa_service`)."""
        tentativa.feedback = feedback

    def media_pontuacao_concluidas(self, user_id: str) -> float | None:
        """The student's general skill signal for adaptive question selection
        (see `dificuldade_service`) - average score across every attempt
        they've ever completed, not scoped to one módulo."""
        stmt = select(func.avg(Tentativa.pontuacao)).where(
            Tentativa.user_id == user_id, Tentativa.status == STATUS_CONCLUIDA
        )
        resultado = self.db.execute(stmt).scalar_one()
        return float(resultado) if resultado is not None else None

    def list_by_user(self, user_id: str) -> list[Tentativa]:
        """The student's own quiz-attempt history, most recent first. Eager-loads
        both possible scopes (see `Tentativa`) - only one is ever populated."""
        stmt = (
            select(Tentativa)
            .where(Tentativa.user_id == user_id)
            .options(
                selectinload(Tentativa.questionario).selectinload(Questionario.modulo),
                selectinload(Tentativa.tema),
            )
            .order_by(Tentativa.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())


def get_tentativa_repository(db: DbSession) -> TentativaRepository:
    return TentativaRepository(db)


TentativaRepo = Annotated[TentativaRepository, Depends(get_tentativa_repository)]
