import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import and_, func, or_, select

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

    # Ties on XP are broken by user id, so the order - and with it every
    # position - is the same on every call.

    def ranking_global(self, limit: int = 20) -> list[tuple[str, int]]:
        return self._ranking(self._totais(), limit)

    def ranking_por_materia(self, materia_id: uuid.UUID, limit: int = 20) -> list[tuple[str, int]]:
        return self._ranking(self._totais(materia_id), limit)

    def posicao_global(self, user_id: str) -> tuple[int, int] | None:
        return self._posicao(self._totais(), user_id)

    def posicao_por_materia(self, materia_id: uuid.UUID, user_id: str) -> tuple[int, int] | None:
        return self._posicao(self._totais(materia_id), user_id)

    @staticmethod
    def _totais(materia_id: uuid.UUID | None = None):
        stmt = select(XpEvento.user_id.label("uid"), func.sum(XpEvento.quantidade).label("total"))
        if materia_id is not None:
            stmt = stmt.where(XpEvento.materia_id == materia_id)
        return stmt.group_by(XpEvento.user_id).subquery()

    def _ranking(self, totais, limit: int) -> list[tuple[str, int]]:
        stmt = (
            select(totais.c.uid, totais.c.total)
            .order_by(totais.c.total.desc(), totais.c.uid)
            .limit(limit)
        )
        return [(row.uid, row.total) for row in self.db.execute(stmt)]

    def _posicao(self, totais, user_id: str) -> tuple[int, int] | None:
        """`(position, xp)` of the user, or None when they have no XP there."""
        meu = self.db.execute(
            select(totais.c.total).where(totais.c.uid == user_id)
        ).scalar_one_or_none()
        if meu is None:
            return None
        na_frente = self.db.execute(
            select(func.count())
            .select_from(totais)
            .where(
                or_(
                    totais.c.total > meu,
                    and_(totais.c.total == meu, totais.c.uid < user_id),
                )
            )
        ).scalar_one()
        return na_frente + 1, meu


def get_xp_repository(db: DbSession) -> XpRepository:
    return XpRepository(db)


XpRepo = Annotated[XpRepository, Depends(get_xp_repository)]
