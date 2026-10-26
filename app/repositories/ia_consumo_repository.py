from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import case, func, select

from app.db.session import DbSession
from app.models.ia_consumo import IaConsumo
from app.repositories.base import SqlAlchemyRepository


class IaConsumoRepository(SqlAlchemyRepository[IaConsumo]):
    model = IaConsumo

    def _agregados(self):
        return (
            func.count(IaConsumo.id),
            func.coalesce(func.sum(case((IaConsumo.sucesso.is_(False), 1), else_=0)), 0),
            func.coalesce(func.sum(IaConsumo.tokens_entrada), 0),
            func.coalesce(func.sum(IaConsumo.tokens_saida), 0),
        )

    def totais(self, desde: datetime) -> tuple[int, int, int, int]:
        """(chamadas, falhas, tokens de entrada, tokens de saída) desde `desde`."""
        stmt = select(*self._agregados()).where(IaConsumo.created_at >= desde)
        chamadas, falhas, entrada, saida = self.db.execute(stmt).one()
        return int(chamadas), int(falhas), int(entrada), int(saida)

    def por_operacao(self, desde: datetime) -> list[tuple[str, int, int, int, int]]:
        stmt = (
            select(IaConsumo.operacao, *self._agregados())
            .where(IaConsumo.created_at >= desde)
            .group_by(IaConsumo.operacao)
            .order_by(func.count(IaConsumo.id).desc())
        )
        return [
            (op, int(c), int(f), int(e), int(s)) for op, c, f, e, s in self.db.execute(stmt).all()
        ]

    def por_usuario(self, desde: datetime, limite: int) -> list[tuple[str, int, int, int, int]]:
        """Heaviest users first; calls with no logged-in user are left out."""
        stmt = (
            select(IaConsumo.user_id, *self._agregados())
            .where(IaConsumo.created_at >= desde, IaConsumo.user_id.is_not(None))
            .group_by(IaConsumo.user_id)
            .order_by(func.count(IaConsumo.id).desc())
            .limit(limite)
        )
        return [
            (uid, int(c), int(f), int(e), int(s)) for uid, c, f, e, s in self.db.execute(stmt).all()
        ]


def get_ia_consumo_repository(db: DbSession) -> IaConsumoRepository:
    return IaConsumoRepository(db)


IaConsumoRepo = Annotated[IaConsumoRepository, Depends(get_ia_consumo_repository)]
