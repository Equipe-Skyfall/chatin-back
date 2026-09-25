import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select

from app.db.session import DbSession
from app.models.voto_materia import VotoMateria
from app.repositories.base import SqlAlchemyRepository


class VotoRepository(SqlAlchemyRepository[VotoMateria]):
    model = VotoMateria

    def get_by_user_e_materia(self, user_id: str, materia_id: uuid.UUID) -> VotoMateria | None:
        stmt = select(VotoMateria).where(
            VotoMateria.user_id == user_id, VotoMateria.materia_id == materia_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def scores_por_materias(self, materia_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Net score (`sum(valor)`) per matéria, batched for a listing screen
        instead of one query per row. A matéria with zero votes is absent
        from the result - callers should default to `0`."""
        if not materia_ids:
            return {}
        stmt = (
            select(VotoMateria.materia_id, func.sum(VotoMateria.valor))
            .where(VotoMateria.materia_id.in_(materia_ids))
            .group_by(VotoMateria.materia_id)
        )
        return {materia_id: int(soma) for materia_id, soma in self.db.execute(stmt).all()}


def get_voto_repository(db: DbSession) -> VotoRepository:
    return VotoRepository(db)


VotoRepo = Annotated[VotoRepository, Depends(get_voto_repository)]
