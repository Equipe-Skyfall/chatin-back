"""Daily-access streak and the XP it earns.

A student's streak is the number of consecutive days (America/Sao_Paulo) they
used the app. Any authenticated request counts as showing up (see
`app.deps.get_current_user_id`); missing a whole day loses the streak and the
next visit starts again at 1.

XP: every day that extends the streak (the 2nd consecutive day onward) earns
XP_STREAK_DIA, and every 7th day in a row earns XP_STREAK_SEMANA on top. The
first day of a streak earns nothing, so there is nothing to farm by letting it
lapse and restarting.
"""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.models.streak import StreakUsuario
from app.models.xp import MOTIVO_STREAK_DIARIO, XpEvento
from app.repositories.streak_repository import StreakRepository
from app.repositories.xp_repository import XpRepository

logger = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")
XP_STREAK_DIA = 10
XP_STREAK_SEMANA = 50
DIAS_POR_SEMANA = 7


def hoje() -> date:
    return datetime.now(FUSO).date()


def xp_do_dia(sequencia: int) -> int:
    if sequencia < 2:
        return 0
    bonus = XP_STREAK_SEMANA if sequencia % DIAS_POR_SEMANA == 0 else 0
    return XP_STREAK_DIA + bonus


def sequencia_atual(registro: StreakUsuario | None, dia: date) -> int:
    """The streak as it stands on `dia`: still alive if the student was active
    today or yesterday, lost (0) once a whole day went by without them."""
    if registro is None or (dia - registro.ultimo_dia).days > 1:
        return 0
    return registro.sequencia


def registrar_acesso_diario(
    user_id: str,
    streak_repo: StreakRepository,
    xp_repo: XpRepository,
    dia: date | None = None,
) -> None:
    """Counts today for the student and grants the day's XP. Best effort: this
    rides on every authenticated request, so a failure (e.g. the migration not
    applied yet) is logged and swallowed - it must never take the request down."""
    dia = dia or hoje()
    try:
        sequencia = streak_repo.registrar_dia(user_id, dia)
        xp = xp_do_dia(sequencia) if sequencia is not None else 0
        if xp:
            xp_repo.add(
                XpEvento(
                    user_id=user_id, materia_id=None, quantidade=xp, motivo=MOTIVO_STREAK_DIARIO
                )
            )
        streak_repo.commit()
    except Exception:  # noqa: BLE001
        streak_repo.rollback()
        logger.exception("Falha ao registrar o streak diário do aluno %s", user_id)
