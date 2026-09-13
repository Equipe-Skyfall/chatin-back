from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.materia import Materia
from app.models.tema import Tema
from app.repositories.base import SqlAlchemyRepository


class MateriaRepository(SqlAlchemyRepository[Materia]):
    model = Materia

    def list_globais(self) -> list[Materia]:
        """The shared, admin-curated curriculum only - excludes every
        student's personal trilha. Used wherever "the" curriculum is meant
        (e.g. the admin agent's `listar_materias` tool)."""
        stmt = select(Materia).where(Materia.owner_user_id.is_(None)).order_by(Materia.nome)
        return list(self.db.execute(stmt).scalars().all())

    def list_visiveis(self, user_id: str) -> list[Materia]:
        """The global curriculum plus this user's own personal trilhas -
        never another user's. Used by `GET /materias` and anywhere a user's
        own overview needs to include their personal trilhas alongside the
        shared curriculum."""
        stmt = (
            select(Materia)
            .where(or_(Materia.owner_user_id.is_(None), Materia.owner_user_id == user_id))
            .order_by(Materia.nome)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_globais_with_temas_e_modulos(self) -> list[Materia]:
        """Eager-loads temas + módulos for the global curriculum only - used
        by `GET /trilha`, which renders "the" one official path, not any
        student's personal trilha."""
        stmt = (
            select(Materia)
            .where(Materia.owner_user_id.is_(None))
            .options(selectinload(Materia.temas).selectinload(Tema.modulos))
            .order_by(Materia.nome)
        )
        return list(self.db.execute(stmt).scalars().unique().all())

    def list_visiveis_with_temas_e_modulos(self, user_id: str) -> list[Materia]:
        """Same as `list_visiveis`, eager-loaded - used by `GET /progresso`,
        where a student's own personal trilha progress belongs alongside
        their progress in the shared curriculum."""
        stmt = (
            select(Materia)
            .where(or_(Materia.owner_user_id.is_(None), Materia.owner_user_id == user_id))
            .options(selectinload(Materia.temas).selectinload(Tema.modulos))
            .order_by(Materia.nome)
        )
        return list(self.db.execute(stmt).scalars().unique().all())

    def count_by_owner(self, user_id: str) -> int:
        stmt = select(func.count()).select_from(Materia).where(Materia.owner_user_id == user_id)
        return self.db.execute(stmt).scalar_one()

    def get_by_nome(self, nome: str) -> Materia | None:
        stmt = select(Materia).where(Materia.nome == nome)
        return self.db.execute(stmt).scalar_one_or_none()


def get_materia_repository(db: DbSession) -> MateriaRepository:
    return MateriaRepository(db)


MateriaRepo = Annotated[MateriaRepository, Depends(get_materia_repository)]
