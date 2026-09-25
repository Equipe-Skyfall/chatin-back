import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.db.session import DbSession
from app.models.progresso import STATUS_DISPONIVEL, ProgressoUsuario
from app.repositories.base import SqlAlchemyRepository


class ProgressoRepository(SqlAlchemyRepository[ProgressoUsuario]):
    model = ProgressoUsuario

    def get_by_user_and_modulo(self, user_id: str, modulo_id: uuid.UUID) -> ProgressoUsuario | None:
        stmt = select(ProgressoUsuario).where(
            ProgressoUsuario.user_id == user_id, ProgressoUsuario.modulo_id == modulo_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user_and_modulos(
        self, user_id: str, modulo_ids: list[uuid.UUID]
    ) -> list[ProgressoUsuario]:
        if not modulo_ids:
            return []
        stmt = select(ProgressoUsuario).where(
            ProgressoUsuario.user_id == user_id, ProgressoUsuario.modulo_id.in_(modulo_ids)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_user(self, user_id: str) -> list[ProgressoUsuario]:
        stmt = select(ProgressoUsuario).where(ProgressoUsuario.user_id == user_id)
        return list(self.db.execute(stmt).scalars().all())

    def get_or_create(self, user_id: str, modulo_id: uuid.UUID) -> ProgressoUsuario:
        progresso = self.get_by_user_and_modulo(user_id, modulo_id)
        if progresso is None:
            progresso = ProgressoUsuario(
                user_id=user_id, modulo_id=modulo_id, status=STATUS_DISPONIVEL, tentativas_count=0
            )
            self.db.add(progresso)
            self.flush()
        return progresso


def get_progresso_repository(db: DbSession) -> ProgressoRepository:
    return ProgressoRepository(db)


ProgressoRepo = Annotated[ProgressoRepository, Depends(get_progresso_repository)]
