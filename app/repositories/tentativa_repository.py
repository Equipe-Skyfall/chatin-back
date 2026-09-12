import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.db.session import DbSession
from app.models.tentativa import RespostaTentativa, Tentativa, TentativaQuestao
from app.repositories.base import SqlAlchemyRepository


class TentativaRepository(SqlAlchemyRepository[Tentativa]):
    model = Tentativa

    def add_tentativa_questoes(self, itens: list[TentativaQuestao]) -> None:
        self.db.add_all(itens)

    def get_tentativa_questao_ids(self, tentativa_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(TentativaQuestao.questao_id).where(
            TentativaQuestao.tentativa_id == tentativa_id
        )
        return set(self.db.execute(stmt).scalars().all())

    def add_respostas(self, respostas: list[RespostaTentativa]) -> None:
        self.db.add_all(respostas)

    def marcar_concluida(self, tentativa: Tentativa, pontuacao: float, total_corretas: int) -> None:
        tentativa.status = "concluida"
        tentativa.pontuacao = pontuacao
        tentativa.total_corretas = total_corretas
        self.db.add(tentativa)


def get_tentativa_repository(db: DbSession) -> TentativaRepository:
    return TentativaRepository(db)


TentativaRepo = Annotated[TentativaRepository, Depends(get_tentativa_repository)]
