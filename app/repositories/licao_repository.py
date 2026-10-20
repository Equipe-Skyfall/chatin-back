import logging
import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import DbSession
from app.models.licao import LicaoIniciada
from app.repositories.base import SqlAlchemyRepository

logger = logging.getLogger(__name__)


class LicaoRepository(SqlAlchemyRepository[LicaoIniciada]):
    model = LicaoIniciada

    # The lesson is an extra on top of the trail, the quiz and the chat, never a
    # reason for them to stop working: if the flag cannot be read (table not
    # migrated yet, database hiccup) the reads below answer "lesson already
    # given", which keeps everything open and makes `/chat/licao` a no-op.

    def existe(self, user_id: str, modulo_id: uuid.UUID) -> bool:
        stmt = select(LicaoIniciada.id).where(
            LicaoIniciada.user_id == user_id, LicaoIniciada.modulo_id == modulo_id
        )
        try:
            return self.db.execute(stmt).first() is not None
        except SQLAlchemyError:
            self._leitura_falhou()
            return True

    def modulos_iniciados(self, user_id: str, modulo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not modulo_ids:
            return set()
        stmt = select(LicaoIniciada.modulo_id).where(
            LicaoIniciada.user_id == user_id, LicaoIniciada.modulo_id.in_(modulo_ids)
        )
        try:
            return set(self.db.execute(stmt).scalars().all())
        except SQLAlchemyError:
            self._leitura_falhou()
            return set(modulo_ids)

    def _leitura_falhou(self) -> None:
        logger.warning("não foi possível ler licoes_iniciadas; liberando o módulo", exc_info=True)
        self.db.rollback()  # a failed statement poisons the session's transaction

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
