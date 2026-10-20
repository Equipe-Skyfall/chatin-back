import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import DbSession
from app.models.trilha_estudando import TrilhaEstudando
from app.repositories.base import SqlAlchemyRepository


class TrilhaEstudandoRepository(SqlAlchemyRepository[TrilhaEstudando]):
    model = TrilhaEstudando

    def existe(self, user_id: str, materia_id: uuid.UUID) -> bool:
        stmt = select(TrilhaEstudando.id).where(
            TrilhaEstudando.user_id == user_id, TrilhaEstudando.materia_id == materia_id
        )
        return self.db.execute(stmt).first() is not None

    def ids_do_usuario(self, user_id: str) -> set[uuid.UUID]:
        stmt = select(TrilhaEstudando.materia_id).where(TrilhaEstudando.user_id == user_id)
        return set(self.db.execute(stmt).scalars().all())

    def adicionar(self, user_id: str, materia_id: uuid.UUID) -> None:
        """Idempotent: studying the same trilha twice (two tabs) is not an error."""
        stmt = (
            insert(TrilhaEstudando)
            .values(user_id=user_id, materia_id=materia_id)
            .on_conflict_do_nothing(constraint="uq_trilha_estudando")
        )
        self.db.execute(stmt)

    def remover(self, user_id: str, materia_id: uuid.UUID) -> None:
        self.db.execute(
            delete(TrilhaEstudando).where(
                TrilhaEstudando.user_id == user_id, TrilhaEstudando.materia_id == materia_id
            )
        )


def get_trilha_estudando_repository(db: DbSession) -> TrilhaEstudandoRepository:
    return TrilhaEstudandoRepository(db)


TrilhaEstudandoRepo = Annotated[TrilhaEstudandoRepository, Depends(get_trilha_estudando_repository)]
