"""Feedback em texto (IA) sobre o que o aluno errou numa tentativa.

Best-effort de propósito: a falha do provedor de IA **não** pode derrubar a
correção da tentativa (RNF6) - nesse caso devolvemos `None` e a submissão
segue normal, sem feedback.
"""

import logging

from app.ai.base import AIProvider
from app.ai.schemas import ErroQuestao
from app.core.exceptions import ProvedorIAIndisponivelException
from app.schemas.tentativa import RespostaResultadoOut

logger = logging.getLogger(__name__)


def gerar_feedback(
    resultados: list[RespostaResultadoOut], ai_provider: AIProvider
) -> str | None:
    """Resumo, em linguagem natural, só das questões erradas - ou `None`
    quando o aluno acertou tudo, ou quando a IA está indisponível."""
    erros = [
        ErroQuestao(
            enunciado=resultado.enunciado,
            resposta_escolhida=resultado.resposta_escolhida,
            resposta_correta=resultado.resposta_correta,
            explicacao=resultado.explicacao,
        )
        for resultado in resultados
        if not resultado.correta
    ]
    if not erros:
        return None

    try:
        return ai_provider.gerar_feedback_erros(erros)
    except ProvedorIAIndisponivelException:
        logger.warning(
            "Falha ao gerar feedback da tentativa; seguindo sem feedback.", exc_info=True
        )
        return None
