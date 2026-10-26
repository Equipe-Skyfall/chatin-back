"""Monthly quota of trilhas (matérias) a student may create.

The month is the calendar month in Brazil (UTC-3, no daylight saving since
2019 - a fixed offset avoids depending on tzdata being installed). The count is
of the student's existing matérias created since the month began, so deleting
one gives the slot back. Admins are exempt: what they create is the verified,
shared curriculum.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from app.core.exceptions import LimiteTrilhasMensalExcedidoException
from app.repositories.materia_repository import MateriaRepository

FUSO_BR = timezone(timedelta(hours=-3))


@dataclass(frozen=True)
class CotaTrilhas:
    limite: int | None  # None = unlimited (admin)
    usadas: int
    restantes: int | None
    reseta_em: datetime


def inicio_do_mes(agora: datetime | None = None) -> datetime:
    local = (agora or datetime.now(UTC)).astimezone(FUSO_BR)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def proximo_reset(agora: datetime | None = None) -> datetime:
    comeco = inicio_do_mes(agora)
    ano, mes = (comeco.year + 1, 1) if comeco.month == 12 else (comeco.year, comeco.month + 1)
    return comeco.replace(year=ano, month=mes)


def calcular(
    user_id: str,
    repo: MateriaRepository,
    limite: int,
    *,
    admin: bool = False,
    agora: datetime | None = None,
) -> CotaTrilhas:
    reseta_em = proximo_reset(agora)
    if admin:
        return CotaTrilhas(limite=None, usadas=0, restantes=None, reseta_em=reseta_em)
    usadas = repo.count_criadas_desde(user_id, inicio_do_mes(agora))
    return CotaTrilhas(
        limite=limite, usadas=usadas, restantes=max(0, limite - usadas), reseta_em=reseta_em
    )


def exigir_vaga(
    user_id: str,
    repo: MateriaRepository,
    limite: int,
    *,
    admin: bool = False,
    agora: datetime | None = None,
) -> None:
    cota = calcular(user_id, repo, limite, admin=admin, agora=agora)
    if cota.restantes is not None and cota.restantes == 0:
        raise LimiteTrilhasMensalExcedidoException(limite, cota.reseta_em)
