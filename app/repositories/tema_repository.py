import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.fonte import Fonte
from app.models.tema import Tema
from app.repositories.base import SqlAlchemyRepository


class TemaRepository(SqlAlchemyRepository[Tema]):
    model = Tema

    def get_with_relations(self, tema_id: uuid.UUID) -> Tema | None:
        stmt = (
            select(Tema)
            .where(Tema.id == tema_id)
            .options(selectinload(Tema.fontes), selectinload(Tema.modulos))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_materia(self, materia_id: uuid.UUID) -> list[Tema]:
        stmt = select(Tema).where(Tema.materia_id == materia_id).order_by(Tema.ordem)
        return list(self.db.execute(stmt).scalars().all())

    def list_by_materia_with_modulos(self, materia_id: uuid.UUID) -> list[Tema]:
        stmt = (
            select(Tema)
            .where(Tema.materia_id == materia_id)
            .options(selectinload(Tema.modulos))
            .order_by(Tema.ordem)
        )
        return list(self.db.execute(stmt).scalars().unique().all())

    def adicionar_fonte(self, fonte: Fonte) -> Fonte:
        self.db.add(fonte)
        return fonte

    def atualizar_status(self, tema: Tema, status: str) -> None:
        tema.status = status
        self.db.add(tema)


def get_tema_repository(db: DbSession) -> TemaRepository:
    return TemaRepository(db)


TemaRepo = Annotated[TemaRepository, Depends(get_tema_repository)]
