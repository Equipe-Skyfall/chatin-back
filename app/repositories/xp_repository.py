import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select

from app.db.session import DbSession
from app.models.xp import XpEvento
from app.repositories.base import SqlAlchemyRepository


class XpRepository(SqlAlchemyRepository[XpEvento]):
    model = XpEvento

    def total_por_usuario(self, user_id: str) -> int:
        stmt = select(func.coalesce(func.sum(XpEvento.quantidade), 0)).where(
            XpEvento.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one()

    def total_por_usuario_e_materia(self, user_id: str, materia_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.sum(XpEvento.quantidade), 0)).where(
            XpEvento.user_id == user_id, XpEvento.materia_id == materia_id
        )
        return self.db.execute(stmt).scalar_one()

    def ranking_global(self, limit: int = 20) -> list[tuple[str, int]]:
        stmt = (
            select(XpEvento.user_id, func.sum(XpEvento.quantidade).label("total"))
            .group_by(XpEvento.user_id)
            .order_by(func.sum(XpEvento.quantidade).desc())
            .limit(limit)
        )
        return [(row.user_id, row.total) for row in self.db.execute(stmt)]

    def ranking_por_materia(self, materia_id: uuid.UUID, limit: int = 20) -> list[tuple[str, int]]:
        stmt = (
            select(XpEvento.user_id, func.sum(XpEvento.quantidade).label("total"))
            .where(XpEvento.materia_id == materia_id)
            .group_by(XpEvento.user_id)
            .order_by(func.sum(XpEvento.quantidade).desc())
            .limit(limit)
        )
        return [(row.user_id, row.total) for row in self.db.execute(stmt)]


def get_xp_repository(db: DbSession) -> XpRepository:
    return XpRepository(db)


XpRepo = Annotated[XpRepository, Depends(get_xp_repository)]
