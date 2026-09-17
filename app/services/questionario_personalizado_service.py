"""On-demand personalized quiz: an aluno-triggered practice quiz for one
módulo, grounded in that módulo's own content plus the student's own
conversation about it.

Checks the módulo's question pool first and only calls the AI for whatever
is missing to reach `pool_minimo` - what gets generated is appended to that
same pool (`Questionario`), reusable afterward by anyone (another student's
personalized quiz, or the módulo's own completion quiz), reducing AI cost
over time. Always practice-only (`Tentativa.pratica=True`, see
`grading_service.iniciar_tentativa_com_pool`) - never counts toward
progress/XP, unlike the módulo-completion quiz.
"""

import uuid

from app.ai.base import AIProvider
from app.core.exceptions import ConteudoIndisponivelException
from app.models.conversa import TIPO_ALUNO
from app.models.gabarito import Gabarito
from app.models.questao import Questao
from app.models.tentativa import Tentativa
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tentativa_repository import TentativaRepository
from app.services import grading_service


def _contexto_conversa(
    user_id: str, modulo_id: uuid.UUID, conversa_repo: ConversaRepository
) -> str | None:
    conversas = conversa_repo.list_by_user_and_modulo_with_mensagens(user_id, modulo_id, TIPO_ALUNO)
    mensagens = [m.conteudo for c in conversas for m in c.mensagens if m.conteudo]
    return "\n".join(mensagens) if mensagens else None


def _garantir_pool_minimo(
    modulo,
    questionario_id: uuid.UUID,
    pool_minimo: int,
    contexto_conversa: str | None,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
) -> None:
    existentes = questionario_repo.get_questao_ids_pool(questionario_id)
    faltam = pool_minimo - len(existentes)
    if faltam <= 0:
        return

    questionario_gerado = ai_provider.gerar_questionario(
        modulo.conteudo, modulo.descricao, faltam, contexto_conversa
    )
    for offset, questao_gerada in enumerate(questionario_gerado.questoes):
        questao = Questao(
            questionario_id=questionario_id,
            ordem=len(existentes) + offset,
            enunciado=questao_gerada.enunciado,
            alternativas=[
                {"letra": a.letra, "texto": a.texto} for a in questao_gerada.alternativas
            ],
            explicacao=questao_gerada.explicacao,
        )
        questionario_repo.add_questao(questao)
        questionario_repo.flush()  # assign questao.id before creating its gabarito
        questionario_repo.add_gabarito(
            Gabarito(questao_id=questao.id, resposta_correta=questao_gerada.resposta_correta)
        )
    questionario_repo.commit()


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
