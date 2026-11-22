import logging
import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError

from app.db.session import DbSession
from app.models.resumo_abertura import ResumoAbertura
from app.repositories.base import SqlAlchemyRepository

logger = logging.getLogger(__name__)

_UNDEFINED_TABLE = "42P01"  # PostgreSQL SQLSTATE for "relation does not exist"


class ResumoAberturaRepository(SqlAlchemyRepository[ResumoAbertura]):
    model = ResumoAbertura

    # Counting is a side feature: reading a summary or the progress screen must
    # never fail because of it, so while the table is not migrated yet the count
    # is 0 and a registration is dropped. Only that case - any other error
    # propagates.

    def registrar(self, user_id: str, resumo_id: uuid.UUID) -> None:
        """Records one opening and commits it on its own."""
        try:
            self.db.add(ResumoAbertura(user_id=user_id, resumo_id=resumo_id))
            self.db.commit()
        except ProgrammingError as exc:
            self._tabela_ausente_ou_erro(exc)

    def total_por_usuario(self, user_id: str) -> int:
        try:
            stmt = select(func.count(ResumoAbertura.id)).where(ResumoAbertura.user_id == user_id)
            return int(self.db.execute(stmt).scalar_one())
        except ProgrammingError as exc:
            self._tabela_ausente_ou_erro(exc)
            return 0

    def _tabela_ausente_ou_erro(self, exc: ProgrammingError) -> None:
        self.db.rollback()  # a failed statement poisons the session's transaction
        if getattr(exc.orig, "sqlstate", None) != _UNDEFINED_TABLE:
            raise exc
        logger.error("tabela resumo_aberturas ausente (migration 0025 pendente)")


def get_resumo_abertura_repository(db: DbSession) -> ResumoAberturaRepository:
    return ResumoAberturaRepository(db)


ResumoAberturaRepo = Annotated[ResumoAberturaRepository, Depends(get_resumo_abertura_repository)]
