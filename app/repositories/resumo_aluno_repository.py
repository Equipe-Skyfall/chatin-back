import logging
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ProgrammingError

from app.db.session import DbSession
from app.models.resumo_aluno import ResumoAluno
from app.repositories.base import SqlAlchemyRepository

logger = logging.getLogger(__name__)

_UNDEFINED_TABLE = "42P01"  # PostgreSQL SQLSTATE for "relation does not exist"


class ResumoAlunoRepository(SqlAlchemyRepository[ResumoAluno]):
    model = ResumoAluno

    # The summary is an optimisation of the chat's context, never a reason for
    # the chat to stop: while its table is not migrated yet the reads answer
    # "no summary" and the chat carries on with the plain message window. Only
    # that one case - any other database error propagates.

    def get_by_user(self, user_id: str) -> ResumoAluno | None:
        try:
            return self.db.get(ResumoAluno, user_id)
        except ProgrammingError as exc:
            self._tabela_ausente_ou_erro(exc)
            return None

    def _tabela_ausente_ou_erro(self, exc: ProgrammingError) -> None:
        self.db.rollback()  # a failed statement poisons the session's transaction
        if getattr(exc.orig, "sqlstate", None) != _UNDEFINED_TABLE:
            raise exc
        logger.error("tabela resumos_aluno ausente (migration 0021 pendente); sem resumo")

    def salvar(self, user_id: str, resumo: str, mensagens_resumidas: dict[str, int]) -> None:
        """Insert or replace the student's summary in one statement, so two
        refreshes racing each other never conflict on the primary key."""
        stmt = insert(ResumoAluno).values(
            user_id=user_id, resumo=resumo, mensagens_resumidas=mensagens_resumidas
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ResumoAluno.user_id],
            set_={
                "resumo": stmt.excluded.resumo,
                "mensagens_resumidas": stmt.excluded.mensagens_resumidas,
                "atualizado_em": func.now(),
            },
        )
        self.db.execute(stmt)


def get_resumo_aluno_repository(db: DbSession) -> ResumoAlunoRepository:
    return ResumoAlunoRepository(db)


ResumoAlunoRepo = Annotated[ResumoAlunoRepository, Depends(get_resumo_aluno_repository)]
