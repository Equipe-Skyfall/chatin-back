from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert

from app.db.session import DbSession
from app.models.streak import StreakUsuario
from app.repositories.base import SqlAlchemyRepository


class StreakRepository(SqlAlchemyRepository[StreakUsuario]):
    model = StreakUsuario

    def get_by_user(self, user_id: str) -> StreakUsuario | None:
        return self.db.get(StreakUsuario, user_id)

    def registrar_dia(self, user_id: str, hoje: date) -> int | None:
        """Counts `hoje` for the student in one statement and returns the new
        streak length - or None when today was already counted. The row only
        changes when `ultimo_dia` is older than `hoje`, so concurrent requests
        on the same day can't count it twice, and exactly one of them gets the
        return value (and with it the day's XP)."""
        stmt = insert(StreakUsuario).values(user_id=user_id, sequencia=1, ultimo_dia=hoje)
        continua = StreakUsuario.ultimo_dia == hoje - timedelta(days=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[StreakUsuario.user_id],
            set_={
                "sequencia": case((continua, StreakUsuario.sequencia + 1), else_=1),
                "ultimo_dia": hoje,
            },
            where=StreakUsuario.ultimo_dia < hoje,
        ).returning(StreakUsuario.sequencia)
        return self.db.execute(stmt).scalar_one_or_none()


def get_streak_repository(db: DbSession) -> StreakRepository:
    return StreakRepository(db)


StreakRepo = Annotated[StreakRepository, Depends(get_streak_repository)]
