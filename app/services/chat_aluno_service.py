"""Tool-calling chat for regular students (`agent_tools_aluno.py`): search
the public curriculum, see own performance, create own trilha. A much
smaller, non-destructive tool set than the admin agent's, but the same
loop/session mechanics under the hood (`AIProvider.conversar_com_agente_
aluno`) - see `app/ai/base.py`.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.ai.base import AIProvider
from app.ai.schemas import FerramentaContexto, MensagemAgente
from app.core.exceptions import ConversaOcupadaException, ProvedorIAIndisponivelException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Conversa, Mensagem
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository

logger = logging.getLogger(__name__)


def _mensagem_para_historico(mensagem: Mensagem) -> MensagemAgente:
    papel = PAPEL_ASSISTENTE if mensagem.papel == PAPEL_ASSISTENTE else PAPEL_USUARIO
    return MensagemAgente(papel=papel, conteudo=mensagem.conteudo)


def enviar_mensagem(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    ai_provider: AIProvider,
    ctx: FerramentaContexto,
    janela: int,
) -> str:
    """`janela` caps how many of the conversation's most recent messages are
    sent to the model (older ones stay in Postgres, just not in the prompt) -
    bounds prompt size and cost on long chats. `ctx` is this student's
    `FerramentaContexto` (see `routers/chat_aluno.py` for how it's built) -
    `ctx.conversa_id` must equal `conversa.id`."""

    def _salvar(papel: str, conteudo: str) -> None:
        ordem = conversa_repo.proxima_ordem(conversa.id)
        conversa_repo.add_mensagem(
            Mensagem(conversa_id=conversa.id, papel=papel, conteudo=conteudo, ordem=ordem)
        )
        conversa_repo.commit()

    try:
        _salvar(PAPEL_USUARIO, texto_usuario)
    except IntegrityError as exc:
        # Two simultaneous turns on the same conversa both computed the same
        # `ordem` - the unique (conversa_id, ordem) constraint let only one
        # through. This is the only concurrency guard on the student chat.
        conversa_repo.rollback()
        raise ConversaOcupadaException() from exc

    recarregada = conversa_repo.get_with_mensagens(conversa.id)
    historico = [_mensagem_para_historico(m) for m in recarregada.mensagens[-janela:]]

    conteudo_modulo = None
    if conversa.modulo_id is not None:
        modulo = modulo_repo.get(conversa.modulo_id)
        if modulo is not None:
            conteudo_modulo = modulo.conteudo

    resposta = ai_provider.conversar_com_agente_aluno(historico, conteudo_modulo, ctx)
    _salvar(PAPEL_ASSISTENTE, resposta)
    conversa_repo.tocar(conversa.id)
    conversa_repo.commit()
    return resposta


def obter_ou_gerar_resumo(
    conversa: Conversa, conversa_repo: ConversaRepository, ai_provider: AIProvider
) -> str | None:
    """Lazily (re)generates the conversation's summary - only when it's
    missing or stale (the conversation moved on since the last summary), not
    on every read and never on every message. Returns None for a conversation
    with no messages yet (nothing to summarize) or when the AI provider fails
    (RNF6) - one conversation's summary failing must not break the rest of
    the list (see `listar_resumos`), and the stale summary just gets retried
    on the next call instead of being persisted as a failure."""
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

    historico = [_mensagem_para_historico(m) for m in completa.mensagens]
    try:
        resumo = ai_provider.resumir_conversa(historico)
    except ProvedorIAIndisponivelException:
        logger.warning(
            "Falha ao gerar resumo da conversa %s; mantendo resumo anterior (se houver).",
            conversa.id,
            exc_info=True,
        )
        return conversa.resumo
    completa.resumo = resumo
    completa.resumo_gerado_em = datetime.now(UTC)
    conversa_repo.add(completa)
    conversa_repo.commit()
    return resumo
