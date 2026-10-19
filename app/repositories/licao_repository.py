import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import DbSession
from app.models.licao import LicaoIniciada
from app.repositories.base import SqlAlchemyRepository


class LicaoRepository(SqlAlchemyRepository[LicaoIniciada]):
    model = LicaoIniciada

    def existe(self, user_id: str, modulo_id: uuid.UUID) -> bool:
        stmt = select(LicaoIniciada.id).where(
            LicaoIniciada.user_id == user_id, LicaoIniciada.modulo_id == modulo_id
        )
        return self.db.execute(stmt).first() is not None

    def modulos_iniciados(self, user_id: str, modulo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not modulo_ids:
            return set()
        stmt = select(LicaoIniciada.modulo_id).where(
            LicaoIniciada.user_id == user_id, LicaoIniciada.modulo_id.in_(modulo_ids)
        )
        return set(self.db.execute(stmt).scalars().all())

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
