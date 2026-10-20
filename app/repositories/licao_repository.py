import logging
import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ProgrammingError

from app.db.session import DbSession
from app.models.licao import LicaoIniciada
from app.repositories.base import SqlAlchemyRepository

logger = logging.getLogger(__name__)

_UNDEFINED_TABLE = "42P01"  # PostgreSQL SQLSTATE for "relation does not exist"


class LicaoRepository(SqlAlchemyRepository[LicaoIniciada]):
    model = LicaoIniciada

    # The lesson is an extra on top of the trail, the quiz and the chat, never a
    # reason for them to stop working: while its table is not migrated yet the
    # reads below answer "lesson already given", which keeps everything open and
    # makes `/chat/licao` a no-op. Only that one case: any other database error
    # (outage, timeout, bad query) propagates, so a real failure is never
    # silently turned into unlocked quizzes.

    def existe(self, user_id: str, modulo_id: uuid.UUID) -> bool:
        stmt = select(LicaoIniciada.id).where(
            LicaoIniciada.user_id == user_id, LicaoIniciada.modulo_id == modulo_id
        )
        try:
            return self.db.execute(stmt).first() is not None
        except ProgrammingError as exc:
            self._tabela_ausente_ou_erro(exc)
            return True

    def modulos_iniciados(self, user_id: str, modulo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not modulo_ids:
            return set()
        stmt = select(LicaoIniciada.modulo_id).where(
            LicaoIniciada.user_id == user_id, LicaoIniciada.modulo_id.in_(modulo_ids)
        )
        try:
            return set(self.db.execute(stmt).scalars().all())
        except ProgrammingError as exc:
            self._tabela_ausente_ou_erro(exc)
            return set(modulo_ids)

    def _tabela_ausente_ou_erro(self, exc: ProgrammingError) -> None:
        self.db.rollback()  # a failed statement poisons the session's transaction
        if getattr(exc.orig, "sqlstate", None) != _UNDEFINED_TABLE:
            raise exc
        logger.error(
            "tabela licoes_iniciadas ausente (migration 0019 pendente); liberando os módulos",
            exc_info=True,
        )

    def marcar(self, user_id: str, modulo_id: uuid.UUID) -> None:
        """Idempotent: two tabs finishing the lesson at once don't conflict."""
        stmt = (
            insert(LicaoIniciada)
            .values(user_id=user_id, modulo_id=modulo_id)
            .on_conflict_do_nothing(constraint="uq_licao_iniciada_modulo")
        )
        self.db.execute(stmt)


def get_licao_repository(db: DbSession) -> LicaoRepository:
    return LicaoRepository(db)


LicaoRepo = Annotated[LicaoRepository, Depends(get_licao_repository)]
