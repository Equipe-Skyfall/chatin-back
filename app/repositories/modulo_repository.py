import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.modulo import Modulo
from app.models.tema import Tema
from app.repositories.base import SqlAlchemyRepository


class ModuloRepository(SqlAlchemyRepository[Modulo]):
    model = Modulo

    def list_by_tema(self, tema_id: uuid.UUID) -> list[Modulo]:
        stmt = select(Modulo).where(Modulo.tema_id == tema_id).order_by(Modulo.ordem)
        return list(self.db.execute(stmt).scalars().all())

    def get_with_tema_e_materia(self, modulo_id: uuid.UUID) -> Modulo | None:
        """Loads the módulo together with its tema and that tema's matéria, so
        callers (e.g. `resumo_estudo_service`) can build the study summary's
        header without triggering lazy loads."""
        stmt = (
            select(Modulo)
            .where(Modulo.id == modulo_id)
            .options(selectinload(Modulo.tema).selectinload(Tema.materia))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def atualizar_status(self, modulo: Modulo, status: str) -> None:
        modulo.status = status
        self.db.add(modulo)

    def definir_conteudo(self, modulo: Modulo, conteudo: str, modelo_ia: str) -> None:
        """Persists freshly AI-generated content - distinct from
        `atualizar_conteudo`, which is a manual edit of existing content."""
        modulo.conteudo = conteudo
        modulo.conteudo_modelo_ia = modelo_ia
        self.db.add(modulo)

    def atualizar_conteudo(self, modulo: Modulo, conteudo: str) -> None:
        modulo.conteudo = conteudo
        self.db.add(modulo)


def get_modulo_repository(db: DbSession) -> ModuloRepository:
    return ModuloRepository(db)


ModuloRepo = Annotated[ModuloRepository, Depends(get_modulo_repository)]
