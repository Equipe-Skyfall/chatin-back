from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.materia import Materia
from app.models.tema import Tema
from app.repositories.base import SqlAlchemyRepository


class MateriaRepository(SqlAlchemyRepository[Materia]):
    model = Materia

    def list_all(self) -> list[Materia]:
        # Matérias have no `ordem` - they're siblings, not a sequence - so this
        # is just a stable, human-friendly default listing order.
        stmt = select(Materia).order_by(Materia.nome)
        return list(self.db.execute(stmt).scalars().all())

    def list_all_with_temas_e_modulos(self) -> list[Materia]:
        """Eager-loads temas + módulos - used by /trilha and /progresso, which
        otherwise roll up every módulo under every tema under every matéria.
        """
        stmt = (
            select(Materia)
            .options(selectinload(Materia.temas).selectinload(Tema.modulos))
            .order_by(Materia.nome)
        )
        return list(self.db.execute(stmt).scalars().unique().all())

    def get_by_nome(self, nome: str) -> Materia | None:
        stmt = select(Materia).where(Materia.nome == nome)
        return self.db.execute(stmt).scalar_one_or_none()


def get_materia_repository(db: DbSession) -> MateriaRepository:
    return MateriaRepository(db)


MateriaRepo = Annotated[MateriaRepository, Depends(get_materia_repository)]
