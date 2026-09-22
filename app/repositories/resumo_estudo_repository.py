import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.db.session import DbSession
from app.models.modulo import Modulo
from app.models.resumo_estudo import ResumoEstudo
from app.models.tema import Tema
from app.repositories.base import SqlAlchemyRepository


class ResumoEstudoRepository(SqlAlchemyRepository[ResumoEstudo]):
    model = ResumoEstudo

    def get_by_user_and_modulo(self, user_id: str, modulo_id: uuid.UUID) -> ResumoEstudo | None:
        """Key of the upsert: at most one summary per (user, módulo)."""
        stmt = select(ResumoEstudo).where(
            ResumoEstudo.user_id == user_id, ResumoEstudo.modulo_id == modulo_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user(
        self, user_id: str, limit: int, offset: int, materia_id: uuid.UUID | None = None
    ) -> list[ResumoEstudo]:
        """The Biblioteca listing: always scoped to the caller's own `user_id`
        (never a cross-user read), paginated with limit/offset. `materia_id`
        is an optional filter that joins through módulo -> tema to narrow to
        one matéria."""
        stmt = select(ResumoEstudo).where(ResumoEstudo.user_id == user_id)
        if materia_id is not None:
            stmt = (
                stmt.join(Modulo, ResumoEstudo.modulo_id == Modulo.id)
                .join(Tema, Modulo.tema_id == Tema.id)
                .where(Tema.materia_id == materia_id)
            )
        stmt = (
            stmt.order_by(ResumoEstudo.updated_at.desc()).limit(limit).offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())


def get_resumo_estudo_repository(db: DbSession) -> ResumoEstudoRepository:
    return ResumoEstudoRepository(db)


ResumoEstudoRepo = Annotated[ResumoEstudoRepository, Depends(get_resumo_estudo_repository)]
