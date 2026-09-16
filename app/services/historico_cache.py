"""Redis-backed working memory for the student chat (`chat_aluno_service`):
a cache of each conversa's most recent messages, used only to build the
context sent to the AI provider.

Postgres (`Mensagem`) stays the source of truth and the full audit trail -
this cache is a disposable, best-effort mirror of the tail of that history.
Any Redis failure (unreachable, timed out, or simply not configured - `redis`
is `None`) is treated as a cache miss and falls back to reloading from
Postgres via `conversa_repo`; it never raises, so an outage here can't break
the chat (see RNF6 in `docs/AGENTS.md`).
"""

import json
import logging
import uuid

import redis

from app.ai.schemas import MensagemAgente
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Mensagem
from app.repositories.conversa_repository import ConversaRepository

logger = logging.getLogger(__name__)


def _chave(conversa_id: uuid.UUID) -> str:
    return f"conversa:{conversa_id}:historico"


def mensagem_para_historico(mensagem: Mensagem) -> MensagemAgente:
    papel = PAPEL_ASSISTENTE if mensagem.papel == PAPEL_ASSISTENTE else PAPEL_USUARIO
    return MensagemAgente(papel=papel, conteudo=mensagem.conteudo)


def _serializar(mensagem: MensagemAgente) -> str:
    return json.dumps({"papel": mensagem.papel, "conteudo": mensagem.conteudo})


def _desserializar(bruto: str) -> MensagemAgente:
    dados = json.loads(bruto)
    return MensagemAgente(papel=dados["papel"], conteudo=dados["conteudo"])


def _do_postgres(
    conversa_id: uuid.UUID, conversa_repo: ConversaRepository, janela: int
) -> list[MensagemAgente]:
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    mensagens = conversa.mensagens[-janela:] if conversa else []
    return [mensagem_para_historico(m) for m in mensagens]


def obter_historico_recente(
    conversa_id: uuid.UUID,
    conversa_repo: ConversaRepository,
    redis_cliente: redis.Redis | None,
    janela: int,
) -> list[MensagemAgente]:
    """Returns up to `janela` most recent messages, oldest first. Tries the
    Redis cache first; falls back to (and repopulates from) Postgres on a
    miss or any Redis error."""
    if redis_cliente is None:
        return _do_postgres(conversa_id, conversa_repo, janela)

    chave = _chave(conversa_id)
    try:
        brutos = redis_cliente.lrange(chave, 0, -1)
    except redis.RedisError:
        logger.warning("Redis indisponível ao ler histórico da conversa %s", conversa_id)
        return _do_postgres(conversa_id, conversa_repo, janela)

    if brutos:
        return [_desserializar(b) for b in brutos]

    historico = _do_postgres(conversa_id, conversa_repo, janela)
    try:
        if historico:
            pipe = redis_cliente.pipeline()
            pipe.rpush(chave, *[_serializar(m) for m in historico])
            pipe.ltrim(chave, -janela, -1)
            pipe.expire(chave, 60 * 60 * 24)
            pipe.execute()
    except redis.RedisError:
        logger.warning("Redis indisponível ao repopular histórico da conversa %s", conversa_id)
    return historico


def registrar_mensagem(
    conversa_id: uuid.UUID,
    mensagem: MensagemAgente,
    redis_cliente: redis.Redis | None,
    janela: int,
) -> None:
    """Mirrors one turn onto the cache, trimmed to the last `janela` entries.
    Best-effort: never raises, since Postgres already holds the message."""
    if redis_cliente is None:
        return

    chave = _chave(conversa_id)
    try:
        pipe = redis_cliente.pipeline()
        pipe.rpush(chave, _serializar(mensagem))
        pipe.ltrim(chave, -janela, -1)
        pipe.expire(chave, 60 * 60 * 24)
        pipe.execute()
    except redis.RedisError:
        logger.warning("Redis indisponível ao registrar mensagem da conversa %s", conversa_id)
