"""Long-term memory for the student chat (pgvector): a short AI extraction
of key facts per conversa (`Conversa.memoria_chave` + `memoria_embedding`),
generated lazily - the same staleness pattern as
`chat_aluno_service.obter_ou_gerar_resumo` (regenerated only when missing or
stale, never on every message) - and retrieved by semantic similarity to
ground a *different, later* conversa about the same módulo.

Unlike `resumo` (a narrative for the student's own summary list),
`memoria_chave` is a short, factual digest meant purely for the AI's own
grounding - see `app/ai/prompts.py:prompt_extrair_memoria_conversa`.
"""

import uuid
from datetime import UTC, datetime

from app.ai.base import AIProvider
from app.models.conversa import TIPO_ALUNO, Conversa
from app.repositories.conversa_repository import ConversaRepository
from app.services.historico_cache import mensagem_para_historico

_SEM_CONTEUDO_RELEVANTE = "nada relevante a registrar"


def obter_ou_gerar_memoria(
    conversa: Conversa, conversa_repo: ConversaRepository, ai_provider: AIProvider
) -> None:
    """Idempotent per stale/missing memory - a conversa that already has an
    up-to-date one costs nothing (no AI call). Persists in place; callers
    don't need the return value, they read `conversa.memoria_chave`/
    `memoria_embedding` afterward."""
    esta_atualizada = (
        conversa.memoria_chave is not None
        and conversa.memoria_gerada_em is not None
        and conversa.memoria_gerada_em >= conversa.updated_at
    )
    if esta_atualizada or not conversa.mensagens:
        return

    historico = [mensagem_para_historico(m) for m in conversa.mensagens]
    memoria_chave = ai_provider.extrair_memoria_conversa(historico)
    sem_conteudo_relevante = _SEM_CONTEUDO_RELEVANTE in memoria_chave.strip().lower()

    conversa.memoria_chave = memoria_chave
    conversa.memoria_embedding = (
        None if sem_conteudo_relevante else ai_provider.gerar_embedding(memoria_chave)
    )
    conversa.memoria_gerada_em = datetime.now(UTC)
    conversa_repo.add(conversa)
    conversa_repo.commit()


def atualizar_memorias_do_modulo(
    user_id: str,
    modulo_id: uuid.UUID,
    excluir_id: uuid.UUID,
    conversa_repo: ConversaRepository,
    ai_provider: AIProvider,
) -> None:
    """Ensures every one of the student's other, past conversas about this
    módulo has an up-to-date memory, so `ConversaRepository.buscar_memorias_similares`
    (called right after this) can actually find them. Cheap in the steady
    state: each conversa only ever regenerates once, the first time it's
    touched here (see `obter_ou_gerar_memoria`'s staleness check) - an old,
    finished conversa never goes stale again."""
    for conversa in conversa_repo.list_by_user_and_modulo(
        user_id, modulo_id, TIPO_ALUNO, excluir_id
    ):
        obter_ou_gerar_memoria(conversa, conversa_repo, ai_provider)
