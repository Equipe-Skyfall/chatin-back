"""On-demand personalized quiz: an aluno-triggered practice quiz for one
módulo, grounded in that módulo's own content plus the student's own
conversation about it.

Checks the módulo's question pool first and only calls the AI for whatever
is missing to reach `pool_minimo` - what gets generated is appended to that
same pool (`Questionario`), reusable afterward by anyone (another student's
personalized quiz), reducing AI cost over time - but always flagged
`Questao.personalizada=True`, which structurally excludes it from any pool a
grade depends on (see `QuestionarioRepository.get_questao_ids_pool_graduavel`)
- a student's own conversation text grounds these questions, so they must
never be gradeable for anyone. Always practice-only
(`Tentativa.pratica=True`, see `grading_service.iniciar_tentativa_com_pool`)
- never counts toward progress/XP, unlike the módulo-completion quiz.
"""

import logging
import uuid

from app.ai.base import AIProvider
from app.core.exceptions import (
    AppException,
    ConteudoIndisponivelException,
    GeracaoConteudoFalhouException,
)
from app.models.conversa import TIPO_ALUNO
from app.models.gabarito import Gabarito
from app.models.modulo import Modulo
from app.models.questao import Questao
from app.models.tentativa import Tentativa
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tentativa_repository import TentativaRepository
from app.services import grading_service

logger = logging.getLogger(__name__)

# Caps how much of the student's own conversation text gets embedded in the
# generation prompt - an unbounded join of every message across every past
# conversation about this módulo has no ceiling on token cost/context size,
# and is exactly the kind of input a prompt-injection attempt would try to
# pad out. Keeps the most *recent* text (the tail), since that's the
# freshest signal of what the student actually needs help with.
_CONTEXTO_CONVERSA_MAX_CHARS = 6000


def _contexto_conversa(
    user_id: str, modulo_id: uuid.UUID, conversa_repo: ConversaRepository
) -> str | None:
    conversas = conversa_repo.list_by_user_and_modulo_with_mensagens(user_id, modulo_id, TIPO_ALUNO)
    mensagens = [m.conteudo for c in conversas for m in c.mensagens if m.conteudo]
    if not mensagens:
        return None
    texto = "\n".join(mensagens)
    return texto[-_CONTEXTO_CONVERSA_MAX_CHARS:]


def _garantir_pool_minimo(
    modulo: Modulo,
    questionario_id: uuid.UUID,
    pool_minimo: int,
    contexto_conversa: str | None,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
) -> None:
    existentes_ids = questionario_repo.get_questao_ids_pool(questionario_id)
    faltam = pool_minimo - len(existentes_ids)
    if faltam <= 0:
        return

    existentes = questionario_repo.get_questoes_by_ids(existentes_ids)
    proxima_ordem = max((q.ordem for q in existentes), default=-1) + 1

    try:
        questionario_gerado = ai_provider.gerar_questionario(
            modulo.conteudo, modulo.descricao, faltam, contexto_conversa
        )
        for offset, questao_gerada in enumerate(questionario_gerado.questoes):
            questao = Questao(
                questionario_id=questionario_id,
                ordem=proxima_ordem + offset,
                enunciado=questao_gerada.enunciado,
                alternativas=[
                    {"letra": a.letra, "texto": a.texto} for a in questao_gerada.alternativas
                ],
                explicacao=questao_gerada.explicacao,
                personalizada=True,
            )
            questionario_repo.add_questao(questao)
            questionario_repo.flush()  # assign questao.id before creating its gabarito
            questionario_repo.add_gabarito(
                Gabarito(questao_id=questao.id, resposta_correta=questao_gerada.resposta_correta)
            )
        questionario_repo.commit()
    except AppException:
        questionario_repo.db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        questionario_repo.db.rollback()
        raise GeracaoConteudoFalhouException(str(exc)) from exc

    if len(questionario_gerado.questoes) < faltam:
        logger.warning(
            "IA retornou %s questões personalizadas, pedimos %s (questionário %s) - "
            "a próxima chamada vai tentar completar a diferença.",
            len(questionario_gerado.questoes),
            faltam,
            questionario_id,
        )


def gerar_tentativa_personalizada(
    modulo_id: uuid.UUID,
    user_id: str,
    pool_minimo: int,
    num_questoes: int,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
    conversa_repo: ConversaRepository,
    tentativa_repo: TentativaRepository,
    ai_provider: AIProvider,
) -> tuple[Tentativa, list[Questao]]:
    # Checked *before* touching the AI/pool: a student with an open
    # questionário gets it back immediately, with zero AI cost - generating
    # (and paying for) new personalized questions only to discard the
    # response in favor of the open one would defeat the whole point of
    # capping cost. See `grading_service.iniciar_tentativa_com_pool`, which
    # this mirrors but can't reuse directly here, since we need to skip
    # `_garantir_pool_minimo` entirely, not just the sampling step.
    questionario_aberto = tentativa_repo.get_questionario_aberto_by_user(user_id)
    if questionario_aberto is not None:
        return grading_service.questionario_aberto_como_lista(
            questionario_aberto, questionario_repo
        )

    modulo = modulo_repo.get(modulo_id)
    if modulo is None or not modulo.conteudo:
        raise ConteudoIndisponivelException("O módulo ainda não possui conteúdo gerado.")

    questionario = questionario_repo.get_by_modulo(modulo_id)
    if questionario is None:
        raise ConteudoIndisponivelException("O módulo ainda não possui questionário gerado.")

    contexto_conversa = _contexto_conversa(user_id, modulo_id, conversa_repo)
    _garantir_pool_minimo(
        modulo, questionario.id, pool_minimo, contexto_conversa, questionario_repo, ai_provider
    )

    pool_ids = questionario_repo.get_questao_ids_pool(questionario.id)
    return grading_service.iniciar_tentativa_com_pool(
        pool_ids,
        user_id,
        num_questoes,
        questionario_repo,
        tentativa_repo,
        questionario_id=questionario.id,
        tema_id=None,
        pratica=True,
    )
