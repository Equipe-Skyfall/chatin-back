"""Runs on módulo creation, right after `conteudo_modulo_pipeline`: generate
its reusable question pool - one AI call, ever, per módulo. Every subsequent
student attempt samples from what's stored here (see
`app.services.grading_service` / the tentativas router) - no new AI call is
made for that.
"""

from app.ai.base import AIProvider
from app.core.exceptions import (
    AppException,
    ConteudoIndisponivelException,
    GeracaoConteudoFalhouException,
)
from app.models.gabarito import Gabarito
from app.models.modulo import STATUS_ERRO, STATUS_PRONTO, Modulo
from app.models.questao import Questao
from app.models.questionario import Questionario
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository


def gerar_questionario_modulo(
    modulo: Modulo,
    questionario_repo: QuestionarioRepository,
    modulo_repo: ModuloRepository,
    ai_provider: AIProvider,
    pool_size: int,
) -> None:
    if not modulo.conteudo:
        raise ConteudoIndisponivelException("O módulo ainda não possui conteúdo gerado.")

    try:
        questionario_gerado = ai_provider.gerar_questionario(
            modulo.conteudo, modulo.descricao, pool_size
        )

        questionario = Questionario(modulo_id=modulo.id, modelo_ia=questionario_gerado.modelo)
        questionario_repo.add(questionario)
        questionario_repo.flush()  # assign questionario.id before creating its questões

        for ordem, questao_gerada in enumerate(questionario_gerado.questoes):
            questao = Questao(
                questionario_id=questionario.id,
                ordem=ordem,
                enunciado=questao_gerada.enunciado,
                alternativas=[
                    {"letra": alt.letra, "texto": alt.texto} for alt in questao_gerada.alternativas
                ],
                explicacao=questao_gerada.explicacao,
            )
            questionario_repo.add_questao(questao)
            questionario_repo.flush()  # assign questao.id before creating its gabarito
            questionario_repo.add_gabarito(
                Gabarito(questao_id=questao.id, resposta_correta=questao_gerada.resposta_correta)
            )

        modulo_repo.atualizar_status(modulo, STATUS_PRONTO)
        questionario_repo.commit()
    except AppException:
        questionario_repo.db.rollback()
        modulo_repo.atualizar_status(modulo, STATUS_ERRO)
        modulo_repo.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        questionario_repo.db.rollback()
        modulo_repo.atualizar_status(modulo, STATUS_ERRO)
        modulo_repo.commit()
        raise GeracaoConteudoFalhouException(str(exc)) from exc
