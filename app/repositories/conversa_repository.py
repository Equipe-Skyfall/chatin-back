import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.db.session import DbSession
from app.models.conversa import Conversa, Mensagem
from app.repositories.base import SqlAlchemyRepository


class ConversaRepository(SqlAlchemyRepository[Conversa]):
    model = Conversa

    def get_with_mensagens(self, conversa_id: uuid.UUID) -> Conversa | None:
        stmt = (
            select(Conversa)
            .where(Conversa.id == conversa_id)
            .options(selectinload(Conversa.mensagens))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user(self, user_id: str, tipo: str) -> list[Conversa]:
        stmt = (
            select(Conversa)
            .where(Conversa.user_id == user_id, Conversa.tipo == tipo)
            .order_by(Conversa.updated_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_user_and_modulo_with_mensagens(
        self, user_id: str, modulo_id: uuid.UUID, tipo: str
    ) -> list[Conversa]:
        """Every conversation this student had scoped to this módulo -
        grounding for the on-demand personalized quiz (see
        `questionario_personalizado_service`), so it can focus on what the
        student actually asked about, not just the módulo's raw content."""
        stmt = (
            select(Conversa)
            .where(
                Conversa.user_id == user_id,
                Conversa.modulo_id == modulo_id,
                Conversa.tipo == tipo,
            )
            .options(selectinload(Conversa.mensagens))
        )
        return list(self.db.execute(stmt).scalars().all())

    def add_mensagem(self, mensagem: Mensagem) -> Mensagem:
        self.db.add(mensagem)
        return mensagem

    def proxima_ordem(self, conversa_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Mensagem).where(Mensagem.conversa_id == conversa_id)
        return self.db.execute(stmt).scalar_one()

    def tocar(self, conversa_id: uuid.UUID) -> None:
        """Bumps `updated_at` explicitly - adding child `mensagens` rows
        doesn't touch the parent row, so `onupdate` wouldn't otherwise fire.
        Keeps `list_by_user` sorted by most recently active conversation."""
        self.db.execute(
            update(Conversa).where(Conversa.id == conversa_id).values(updated_at=func.now())
        )


def get_conversa_repository(db: DbSession) -> ConversaRepository:
    return ConversaRepository(db)


ConversaRepo = Annotated[ConversaRepository, Depends(get_conversa_repository)]
