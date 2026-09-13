"""Unit tests for `agent_service.processar_mensagem` - now a thin
persist/ask-provider/persist orchestration (Fase 3 of the ADK migration moved
the tool-calling loop itself into each `AIProvider` implementation). Uses
`FakeAIProvider`, so these tests never touch the ADK or Gemini for real.
"""

import uuid

import pytest

from app.ai.schemas import FerramentaContexto
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ADMIN, Conversa, Mensagem
from app.services import agent_service


class _FakeConversaRepository:
    """In-memory stand-in for `ConversaRepository` - just enough of its
    interface (`proxima_ordem`, `add_mensagem`, `get_with_mensagens`,
    `commit`, `tocar`) for `processar_mensagem` to run against, without a
    real database."""

    def __init__(self, conversa: Conversa):
        self._conversa = conversa
        self.commits = 0
        self.tocadas = 0

    def proxima_ordem(self, conversa_id: uuid.UUID) -> int:
        return len(self._conversa.mensagens)

    def add_mensagem(self, mensagem: Mensagem) -> Mensagem:
        self._conversa.mensagens.append(mensagem)
        return mensagem

    def get_with_mensagens(self, conversa_id: uuid.UUID) -> Conversa:
        return self._conversa

    def commit(self) -> None:
        self.commits += 1

    def tocar(self, conversa_id: uuid.UUID) -> None:
        self.tocadas += 1


def _conversa() -> Conversa:
    return Conversa(id=uuid.uuid4(), user_id="admin-1", titulo="Teste", tipo=TIPO_ADMIN)


def _ctx(conversa_id: uuid.UUID) -> FerramentaContexto:
    return FerramentaContexto(
        materia_repo=None,
        tema_repo=None,
        modulo_repo=None,
        questionario_repo=None,
        ai_provider=None,
        pool_size=12,
        conversa_id=conversa_id,
    )


def test_persiste_mensagem_do_usuario_e_resposta_final(fake_ai_provider):
    conversa = _conversa()
    conversa_repo = _FakeConversaRepository(conversa)
    fake_ai_provider.resposta_agente_fixa = "Matéria criada com sucesso."

    resposta = agent_service.processar_mensagem(
        conversa, "crie uma matéria de Física", conversa_repo, _ctx(conversa.id), fake_ai_provider
    )

    assert resposta == "Matéria criada com sucesso."
    assert len(conversa.mensagens) == 2
    assert conversa.mensagens[0].papel == PAPEL_USUARIO
    assert conversa.mensagens[0].conteudo == "crie uma matéria de Física"
    assert conversa.mensagens[1].papel == PAPEL_ASSISTENTE
    assert conversa.mensagens[1].conteudo == "Matéria criada com sucesso."
    assert conversa_repo.tocadas == 1


def test_nao_persiste_granularidade_por_tool_call(fake_ai_provider):
    """Only the top-level user/assistant turns become `Mensagem` rows now -
    per-tool-call granularity lives in the ADK's own session when
    `AI_PROVIDER=adk` (see `AdkProvider.obter_historico_sessao`), not here."""
    conversa = _conversa()
    conversa_repo = _FakeConversaRepository(conversa)

    agent_service.processar_mensagem(
        conversa, "oi", conversa_repo, _ctx(conversa.id), fake_ai_provider
    )

    assert len(conversa.mensagens) == 2


def test_passa_o_ctx_correto_para_o_provider(fake_ai_provider):
    conversa = _conversa()
    conversa_repo = _FakeConversaRepository(conversa)
    ctx = _ctx(conversa.id)

    agent_service.processar_mensagem(conversa, "oi", conversa_repo, ctx, fake_ai_provider)

    assert fake_ai_provider.ctx_recebido is ctx


def test_erro_do_provider_propaga(fake_ai_provider):
    conversa = _conversa()
    conversa_repo = _FakeConversaRepository(conversa)
    fake_ai_provider.falhar_conversar_com_ferramentas = True

    with pytest.raises(RuntimeError):
        agent_service.processar_mensagem(
            conversa, "oi", conversa_repo, _ctx(conversa.id), fake_ai_provider
        )

    # The user's message was still persisted before the provider call failed.
    assert len(conversa.mensagens) == 1
    assert conversa.mensagens[0].papel == PAPEL_USUARIO
