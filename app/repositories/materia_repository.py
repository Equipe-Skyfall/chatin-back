from typing import Annotated

from fastapi import Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.materia import Materia
from app.models.tema import Tema
from app.repositories.base import SqlAlchemyRepository


class MateriaRepository(SqlAlchemyRepository[Materia]):
    model = Materia

    def list_globais(self) -> list[Materia]:
        """The shared, admin-curated curriculum only - excludes every
        student's trilha. Used wherever "the" official curriculum is meant
        (e.g. `GET /trilha`, the admin agent's `listar_materias` tool)."""
        stmt = select(Materia).where(Materia.owner_user_id.is_(None)).order_by(Materia.nome)
        return list(self.db.execute(stmt).scalars().all())

    def list_globais_with_temas_e_modulos(self) -> list[Materia]:
        """Eager-loads temas + módulos for the global curriculum only - used
        by `GET /trilha`, which renders "the" one official path, never a
        student's own trilha."""
        stmt = (
            select(Materia)
            .where(Materia.owner_user_id.is_(None))
            .options(selectinload(Materia.temas).selectinload(Tema.modulos))
            .order_by(Materia.nome)
        )
        return list(self.db.execute(stmt).scalars().unique().all())

    def list_publica(self) -> list[Materia]:
        """Global curriculum + every student's trilha, from every student -
        the public "browse the community" listing (`GET /materias`), ranked
        by votes at the router/schema level, not here."""
        stmt = select(Materia).order_by(Materia.nome)
        return list(self.db.execute(stmt).scalars().all())

    def list_minhas_e_globais(self, user_id: str) -> list[Materia]:
        """Global curriculum + only *this* user's own trilhas - never
        another student's. Used for a student's personal rollups (XP per
        matéria) where every other student's trilha would just be noise."""
        stmt = (
            select(Materia)
            .where(or_(Materia.owner_user_id.is_(None), Materia.owner_user_id == user_id))
            .order_by(Materia.nome)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_minhas_e_globais_with_temas_e_modulos(self, user_id: str) -> list[Materia]:
        """Same as `list_minhas_e_globais`, eager-loaded - used by
        `GET /progresso`, where a student's own trilha progress belongs
        alongside their progress in the shared curriculum (but not the
        thousands of other students' trilhas they've never touched)."""
        stmt = (
            select(Materia)
            .where(or_(Materia.owner_user_id.is_(None), Materia.owner_user_id == user_id))
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
