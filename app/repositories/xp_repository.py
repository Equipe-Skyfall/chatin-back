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
        return self._ranking(None, limit)

    def ranking_por_materia(self, materia_id: uuid.UUID, limit: int = 20) -> list[tuple[str, int]]:
        return self._ranking(materia_id, limit)

    def posicao_global(self, user_id: str) -> tuple[int, int] | None:
        return self._posicao(user_id, None)

    def posicao_por_materia(self, user_id: str, materia_id: uuid.UUID) -> tuple[int, int] | None:
        return self._posicao(user_id, materia_id)

    def _totais(self, materia_id: uuid.UUID | None):
        stmt = select(XpEvento.user_id, func.sum(XpEvento.quantidade).label("total")).group_by(
            XpEvento.user_id
        )
        if materia_id is not None:
            stmt = stmt.where(XpEvento.materia_id == materia_id)
        return stmt

    def _ranking(self, materia_id: uuid.UUID | None, limit: int) -> list[tuple[str, int]]:
        """Highest XP first; ties break by user_id so the order (and the
        positions `_posicao` reports) never changes between two requests."""
        stmt = (
            self._totais(materia_id)
            .order_by(func.sum(XpEvento.quantidade).desc(), XpEvento.user_id)
            .limit(limit)
        )
        return [(row.user_id, row.total) for row in self.db.execute(stmt)]

    def _posicao(self, user_id: str, materia_id: uuid.UUID | None) -> tuple[int, int] | None:
        """(1-based position, XP) of one student under the same ordering as
        `_ranking`, or `None` when they have no XP there yet."""
        totais = self._totais(materia_id).subquery()
        meu_total = self.db.execute(
            select(totais.c.total).where(totais.c.user_id == user_id)
        ).scalar_one_or_none()
        if meu_total is None:
            return None
        na_frente = self.db.execute(
            select(func.count()).where(
                (totais.c.total > meu_total)
                | ((totais.c.total == meu_total) & (totais.c.user_id < user_id))
            )
        ).scalar_one()
        return na_frente + 1, int(meu_total)


def get_xp_repository(db: DbSession) -> XpRepository:
    return XpRepository(db)


XpRepo = Annotated[XpRepository, Depends(get_xp_repository)]
