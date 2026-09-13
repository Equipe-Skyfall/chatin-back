"""The admin content-creation chat: persists the user's message, asks the
`AIProvider` for a final reply, and persists that reply. The provider owns
running its own tool-calling loop now (manually, for the legacy
`GeminiProvider`; via the ADK `Runner`'s native auto-invoke, for
`AdkProvider`) - this module no longer dispatches tool calls or tracks an
iteration cap itself; see `AIProvider.conversar_com_ferramentas`.

Per-tool-call granularity is no longer persisted here: only the user's
message and the agent's final reply become `Mensagem` rows. A provider that
keeps its own session (e.g. `AdkProvider`'s ADK `SessionService`) is the
source of truth for that finer-grained history when `AI_PROVIDER=adk`.
"""

from app.ai.base import AIProvider
from app.ai.schemas import FerramentaContexto, MensagemAgente
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Conversa, Mensagem
from app.repositories.conversa_repository import ConversaRepository


def _mensagem_para_agente(mensagem: Mensagem) -> MensagemAgente:
    return MensagemAgente(papel=mensagem.papel, conteudo=mensagem.conteudo)


def processar_mensagem(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    ctx: FerramentaContexto,
    ai_provider: AIProvider,
) -> str:
    """Persists the user's message, asks the provider for the final reply
    (running its own tool-calling loop internally), persists that reply, and
    returns it."""

    def _salvar(papel: str, conteudo: str | None) -> None:
        ordem = conversa_repo.proxima_ordem(conversa.id)
        conversa_repo.add_mensagem(
            Mensagem(conversa_id=conversa.id, papel=papel, conteudo=conteudo, ordem=ordem)
        )
        conversa_repo.commit()

    _salvar(PAPEL_USUARIO, texto_usuario)
    recarregada = conversa_repo.get_with_mensagens(conversa.id)
    historico = [_mensagem_para_agente(m) for m in recarregada.mensagens]

    resposta = ai_provider.conversar_com_ferramentas(historico, ctx)

    _salvar(PAPEL_ASSISTENTE, resposta)
    conversa_repo.tocar(conversa.id)
    conversa_repo.commit()
    return resposta
