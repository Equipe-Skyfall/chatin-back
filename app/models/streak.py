from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StreakUsuario(Base):
    """A student's daily-access streak: how many days in a row they showed up.
    One row per user, updated at most once a day (see `StreakRepository.
    registrar_dia`). `ultimo_dia` is the last calendar day (America/Sao_Paulo)
    they were active; once that is older than yesterday the streak is lost,
    which readers derive (`streak_service.sequencia_atual`) rather than a job
    resetting the row."""

    __tablename__ = "streaks_usuario"

    # From the external auth service's JWT `userId` claim (cuid string).
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    sequencia: Mapped[int] = mapped_column(Integer, nullable=False)
    ultimo_dia: Mapped[date] = mapped_column(Date, nullable=False)
