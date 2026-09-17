"""Grounded Q&A chat for regular students - deliberately simpler than the
admin agent's tool-calling loop (`agent_service`): no tools, no ability to
look up or change anything. Sees only the current módulo's content (when the
conversation is scoped to one) plus its own message history.
"""

import logging
from datetime import UTC, datetime

import redis

from app.ai.base import AIProvider
from app.ai.schemas import MensagemAgente
from app.core.exceptions import ConversaOcupadaException, ProvedorIAIndisponivelException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Conversa, Mensagem
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.services import historico_cache, memoria_longo_prazo_service
from app.services.historico_cache import mensagem_para_historico

logger = logging.getLogger(__name__)


def _memorias_relevantes(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    ai_provider: AIProvider,
    limite: int,
) -> list[str] | None:
    """Long-term context: key facts from this student's *other* past
    conversas about the same módulo, picked by semantic similarity to what
    they're asking now. Best-effort - any AI failure here (embedding or the
    lazy extraction it triggers) degrades to "no long-term context" rather
    than failing the whole turn (RNF6); the short-term window (`historico`)
    and current módulo content still ground the reply either way."""
    if conversa.modulo_id is None:
        return None
    try:
        memoria_longo_prazo_service.atualizar_memorias_do_modulo(
            conversa.user_id, conversa.modulo_id, conversa.id, conversa_repo, ai_provider
        )
        query_embedding = ai_provider.gerar_embedding(texto_usuario)
        memorias = conversa_repo.buscar_memorias_similares(
            conversa.user_id, conversa.modulo_id, query_embedding, limite, conversa.id
        )
    except ProvedorIAIndisponivelException:
        logger.warning(
            "Provedor de IA indisponível ao buscar memória de longo prazo da conversa %s",
            conversa.id,
        )
        return None
    return memorias or None


def enviar_mensagem(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    ai_provider: AIProvider,
    redis_cliente: redis.Redis | None,
    memoria_janela: int,
    memoria_longo_prazo_limite: int,
) -> str:
    def _salvar(papel: str, conteudo: str) -> None:
        ordem = conversa_repo.proxima_ordem(conversa.id)
        conversa_repo.add_mensagem(
            Mensagem(conversa_id=conversa.id, papel=papel, conteudo=conteudo, ordem=ordem)
        )
        conversa_repo.commit()

    if not historico_cache.adquirir_lock(conversa.id, redis_cliente):
        raise ConversaOcupadaException()
    try:
        # Read the window *before* saving this turn's user message, so it
        # never includes it - `texto_usuario` is passed to the provider
        # separately. See `historico_cache` for the Redis cache this reads
        # from (falling back to, and repopulating from, Postgres on a
        # miss/outage).
        historico = historico_cache.obter_historico_recente(
            conversa.id, conversa_repo, redis_cliente, memoria_janela
        )

        _salvar(PAPEL_USUARIO, texto_usuario)
        historico_cache.registrar_mensagem(
            conversa.id,
            MensagemAgente(papel=PAPEL_USUARIO, conteudo=texto_usuario),
            redis_cliente,
            memoria_janela,
        )

        conteudo_modulo = None
        if conversa.modulo_id is not None:
            modulo = modulo_repo.get(conversa.modulo_id)
            if modulo is not None:
                conteudo_modulo = modulo.conteudo

        memorias = _memorias_relevantes(
            conversa, texto_usuario, conversa_repo, ai_provider, memoria_longo_prazo_limite
        )

        resposta = ai_provider.responder_pergunta_aluno(
            historico, texto_usuario, conteudo_modulo, memorias
        )
        _salvar(PAPEL_ASSISTENTE, resposta)
        historico_cache.registrar_mensagem(
            conversa.id,
            MensagemAgente(papel=PAPEL_ASSISTENTE, conteudo=resposta),
            redis_cliente,
            memoria_janela,
        )
        conversa_repo.tocar(conversa.id)
        conversa_repo.commit()
        return resposta
    finally:
        historico_cache.liberar_lock(conversa.id, redis_cliente)


def obter_ou_gerar_resumo(
    conversa: Conversa, conversa_repo: ConversaRepository, ai_provider: AIProvider
) -> str | None:
    """Lazily (re)generates the conversation's summary - only when it's
    missing or stale (the conversation moved on since the last summary), not
    on every read and never on every message. Returns None for a conversation
    with no messages yet (nothing to summarize)."""
    esta_atualizado = (
        conversa.resumo is not None
        and conversa.resumo_gerado_em is not None
        and conversa.resumo_gerado_em >= conversa.updated_at
    )
    if esta_atualizado:
        return conversa.resumo

    completa = conversa_repo.get_with_mensagens(conversa.id)
    if not completa.mensagens:
        return None

    historico = [mensagem_para_historico(m) for m in completa.mensagens]
    resumo = ai_provider.resumir_conversa(historico)
    completa.resumo = resumo
    completa.resumo_gerado_em = datetime.now(UTC)
    conversa_repo.add(completa)
    conversa_repo.commit()
    return resumo
