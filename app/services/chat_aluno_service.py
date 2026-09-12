"""Grounded Q&A chat for regular students - deliberately simpler than the
admin agent's tool-calling loop (`agent_service`): no tools, no ability to
look up or change anything. Sees only the current módulo's content (when the
conversation is scoped to one) plus its own message history.
"""

from datetime import UTC, datetime

from app.ai.base import AIProvider
from app.ai.schemas import MensagemAgente
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Conversa, Mensagem
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository


def _mensagem_para_historico(mensagem: Mensagem) -> MensagemAgente:
    papel = PAPEL_ASSISTENTE if mensagem.papel == PAPEL_ASSISTENTE else PAPEL_USUARIO
    return MensagemAgente(papel=papel, conteudo=mensagem.conteudo)


def enviar_mensagem(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    ai_provider: AIProvider,
) -> str:
    def _salvar(papel: str, conteudo: str) -> None:
        ordem = conversa_repo.proxima_ordem(conversa.id)
        conversa_repo.add_mensagem(
            Mensagem(conversa_id=conversa.id, papel=papel, conteudo=conteudo, ordem=ordem)
        )
        conversa_repo.commit()

    _salvar(PAPEL_USUARIO, texto_usuario)
    recarregada = conversa_repo.get_with_mensagens(conversa.id)
    # every message except the one just saved above, which is passed as `pergunta`
    historico = [_mensagem_para_historico(m) for m in recarregada.mensagens[:-1]]

    conteudo_modulo = None
    if conversa.modulo_id is not None:
        modulo = modulo_repo.get(conversa.modulo_id)
        if modulo is not None:
            conteudo_modulo = modulo.conteudo

    resposta = ai_provider.responder_pergunta_aluno(historico, texto_usuario, conteudo_modulo)
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

    historico = [_mensagem_para_historico(m) for m in completa.mensagens]
    resumo = ai_provider.resumir_conversa(historico)
    completa.resumo = resumo
    completa.resumo_gerado_em = datetime.now(UTC)
    conversa_repo.add(completa)
    conversa_repo.commit()
    return resumo
