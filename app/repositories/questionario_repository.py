import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.db.session import DbSession
from app.models.gabarito import Gabarito
from app.models.questao import Questao
from app.models.questionario import Questionario
from app.repositories.base import SqlAlchemyRepository


class QuestionarioRepository(SqlAlchemyRepository[Questionario]):
    """Covers the questionário pool + its questões. `get_gabarito_map` and
    `atualizar_gabarito` are the only methods anywhere in the codebase that
    touch the `gabaritos` table - every other method here deliberately never
    selects or writes `resposta_correta`.
    """

    model = Questionario

    def get_by_modulo(self, modulo_id: uuid.UUID) -> Questionario | None:
        stmt = select(Questionario).where(Questionario.modulo_id == modulo_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def add_questao(self, questao: Questao) -> Questao:
        self.db.add(questao)
        return questao

    def add_gabarito(self, gabarito: Gabarito) -> Gabarito:
        self.db.add(gabarito)
        return gabarito

    def get_questao_ids_pool(self, questionario_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Questao.id).where(Questao.questionario_id == questionario_id)
        return list(self.db.execute(stmt).scalars().all())

    def get_questoes_by_ids(self, questao_ids: list[uuid.UUID]) -> list[Questao]:
        if not questao_ids:
            return []
        stmt = select(Questao).where(Questao.id.in_(questao_ids))
        return list(self.db.execute(stmt).scalars().all())

    def get_gabarito_map(self, questao_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not questao_ids:
            return {}
        stmt = select(Gabarito.questao_id, Gabarito.resposta_correta).where(
            Gabarito.questao_id.in_(questao_ids)
        )
        return {row.questao_id: row.resposta_correta for row in self.db.execute(stmt)}

    def get_questao_by_id(self, questao_id: uuid.UUID) -> Questao | None:
        return self.db.get(Questao, questao_id)

    def atualizar_questao(
        self,
        questao: Questao,
        *,
        enunciado: str | None = None,
        alternativas: list[dict] | None = None,
        explicacao: str | None = None,
    ) -> None:
        """Manual edit of an already-generated questão - distinct from
        `add_questao`, which persists a freshly AI-generated one. Only the
        provided fields change."""
        if enunciado is not None:
            questao.enunciado = enunciado
        if alternativas is not None:
            questao.alternativas = alternativas
        if explicacao is not None:
            questao.explicacao = explicacao
        self.db.add(questao)

    def atualizar_gabarito(self, questao_id: uuid.UUID, resposta_correta: str) -> None:
        gabarito = self.db.get(Gabarito, questao_id)
        if gabarito is not None:
            gabarito.resposta_correta = resposta_correta
            self.db.add(gabarito)


def get_questionario_repository(db: DbSession) -> QuestionarioRepository:
    return QuestionarioRepository(db)


QuestionarioRepo = Annotated[QuestionarioRepository, Depends(get_questionario_repository)]
