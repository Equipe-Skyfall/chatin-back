"""Quizzes written by hand: create a módulo's questionário, add a questão,
remove one, remove the whole quiz.

The caller has already checked that the user may write to the módulo's matéria
(`core.autorizacao.verificar_acesso_escrita`): the global curriculum is the
admins', a student's own trilha is that student's. Nothing here decides who may
do what - it only keeps the quiz itself consistent.

A quiz made here is the same `Questionario` the AI would have generated for the
módulo (one per módulo), so students take it through the usual routes, with the
usual adaptive sampling and grading. `modelo_ia` says "manual" for it.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    LimiteQuestoesExcedidoException,
    ModuloNaoEncontradoException,
    OrdemDuplicadaException,
    QuestaoNaoEncontradaException,
    QuestionarioJaExisteException,
    QuestionarioNaoEncontradoException,
    QuestionarioSemQuestoesException,
)
from app.models.gabarito import Gabarito
from app.models.questao import Questao
from app.models.questionario import Questionario
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.schemas.questionario import MAX_QUESTOES_POR_QUESTIONARIO

MODELO_MANUAL = "manual"


@dataclass(frozen=True)
class NovaQuestao:
    enunciado: str
    alternativas: list[dict]
    explicacao: str | None
    resposta_correta: str


def _questionario_do_modulo(
    modulo_id: uuid.UUID, modulo_repo: ModuloRepository, questionario_repo: QuestionarioRepository
) -> Questionario:
    if modulo_repo.get(modulo_id) is None:
        raise ModuloNaoEncontradoException(modulo_id)
    questionario = questionario_repo.get_by_modulo(modulo_id)
    if questionario is None:
        raise QuestionarioNaoEncontradoException(modulo_id)
    return questionario


def _persistir_questao(
    questionario_id: uuid.UUID,
    ordem: int,
    nova: NovaQuestao,
    questionario_repo: QuestionarioRepository,
) -> Questao:
    questao = Questao(
        questionario_id=questionario_id,
        ordem=ordem,
        enunciado=nova.enunciado,
        alternativas=nova.alternativas,
        explicacao=nova.explicacao,
        personalizada=False,
    )
    questionario_repo.add_questao(questao)
    questionario_repo.flush()  # assigns questao.id, which the gabarito row needs
    questionario_repo.add_gabarito(
        Gabarito(questao_id=questao.id, resposta_correta=nova.resposta_correta)
    )
    return questao


def criar_questionario(
    modulo_id: uuid.UUID,
    questoes: list[NovaQuestao],
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
) -> list[tuple[Questao, str]]:
    """Creates the módulo's quiz with `questoes` in the order given."""
    if modulo_repo.get(modulo_id) is None:
        raise ModuloNaoEncontradoException(modulo_id)
    if questionario_repo.get_by_modulo(modulo_id) is not None:
        raise QuestionarioJaExisteException()
    if len(questoes) > MAX_QUESTOES_POR_QUESTIONARIO:
        raise LimiteQuestoesExcedidoException(MAX_QUESTOES_POR_QUESTIONARIO)

    questionario = Questionario(modulo_id=modulo_id, modelo_ia=MODELO_MANUAL)
    questionario_repo.add(questionario)
    try:
        # Where two simultaneous creations for the same módulo collide: the
        # unique index on `questionarios.modulo_id` lets only one through.
        questionario_repo.flush()
    except IntegrityError as exc:
        questionario_repo.rollback()
        raise QuestionarioJaExisteException() from exc

    criadas = [
        (_persistir_questao(questionario.id, ordem, nova, questionario_repo), nova.resposta_correta)
        for ordem, nova in enumerate(questoes)
    ]
    questionario_repo.commit()
    return criadas


def adicionar_questao(
    modulo_id: uuid.UUID,
    nova: NovaQuestao,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
) -> tuple[Questao, str]:
    """Appends a questão after the last one of the módulo's existing quiz."""
    questionario = _questionario_do_modulo(modulo_id, modulo_repo, questionario_repo)
    if (
        len(questionario_repo.get_questao_ids_pool(questionario.id))
        >= MAX_QUESTOES_POR_QUESTIONARIO
    ):
        raise LimiteQuestoesExcedidoException(MAX_QUESTOES_POR_QUESTIONARIO)

    ordem = questionario_repo.proxima_ordem(questionario.id)
    try:
        questao = _persistir_questao(questionario.id, ordem, nova, questionario_repo)
        questionario_repo.commit()
    except IntegrityError as exc:
        # Two simultaneous additions picked the same `ordem`.
        questionario_repo.rollback()
        raise OrdemDuplicadaException(ordem) from exc
    return questao, nova.resposta_correta


def remover_questao(
    modulo_id: uuid.UUID,
    questao_id: uuid.UUID,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
) -> None:
    """Removes one questão. The others keep their `ordem` (gaps are fine; what
    matters is that the relative order is kept). The last remaining questão
    cannot be removed - that would leave a quiz no student can start."""
    questionario = _questionario_do_modulo(modulo_id, modulo_repo, questionario_repo)
    questao = questionario_repo.get_questao_by_id(questao_id)
    if questao is None or questao.questionario_id != questionario.id:
        raise QuestaoNaoEncontradaException(questao_id)
    if len(questionario_repo.get_questao_ids_pool(questionario.id)) <= 1:
        raise QuestionarioSemQuestoesException()

    questionario_repo.delete(questao)
    questionario_repo.commit()


def remover_questionario(
    modulo_id: uuid.UUID,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
) -> None:
    """Removes the módulo's whole quiz, its questões and answer keys with it."""
    questionario = _questionario_do_modulo(modulo_id, modulo_repo, questionario_repo)
    questionario_repo.delete(questionario)
    questionario_repo.commit()
