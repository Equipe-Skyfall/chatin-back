"""`AdkProvider.registrar_troca` against a real ADK session service (in-memory
SQLite) and a stub model, so there is no Gemini call: a turn the app answered
itself must show up in the history the chat reads, and the agent must see it
on its next turn."""

import uuid

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types as genai_types

from app.ai.adk_provider import _AGENTE_ALUNO_NOME, _APP_NAME, _USER_ID, AdkProvider
from app.config import Settings
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO


class _ModeloQueAnota(BaseLlm):
    """Answers a fixed text and records every conversation it was sent."""

    model: str = "stub"
    recebidos: list = []

    async def generate_content_async(self, llm_request, stream=False):
        self.recebidos.append(
            [(c.role, "".join(p.text or "" for p in c.parts)) for c in llm_request.contents]
        )
        yield LlmResponse(
            content=genai_types.Content(
                role="model", parts=[genai_types.Part(text="resposta do agente")]
            )
        )


@pytest.fixture
def provider() -> AdkProvider:
    provider = AdkProvider(
        Settings(
            SUPABASE_DB_URL="postgresql+psycopg://user:pass@localhost:5432/db",
            JWT_SECRET="test-secret",
            GEMINI_API_KEY="fake-key",
            AI_PROVIDER="adk",
        )
    )
    provider._agente_session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///:memory:")
    return provider


def _historico(provider, conversa_id):
    return [(m.papel, m.conteudo) for m in provider.obter_historico_sessao(conversa_id) or []]


def test_troca_registrada_aparece_no_historico_da_sessao(provider):
    conversa_id = uuid.uuid4()

    provider.registrar_troca(conversa_id, "como estou indo?", "Você tem 120 XP.")

    assert _historico(provider, conversa_id) == [
        (PAPEL_USUARIO, "como estou indo?"),
        (PAPEL_ASSISTENTE, "Você tem 120 XP."),
    ]


def test_varias_trocas_mantem_a_ordem(provider):
    conversa_id = uuid.uuid4()

    provider.registrar_troca(conversa_id, "meu xp", "120 XP.")
    provider.registrar_troca(conversa_id, "meu ranking", "Você é o 3º.")

    assert [texto for _, texto in _historico(provider, conversa_id)] == [
        "meu xp",
        "120 XP.",
        "meu ranking",
        "Você é o 3º.",
    ]


def test_o_agente_enxerga_a_troca_no_turno_seguinte(provider):
    conversa_id = uuid.uuid4()
    provider.registrar_troca(conversa_id, "como estou indo?", "Você tem 120 XP.")
    modelo = _ModeloQueAnota(recebidos=[])
    agente = LlmAgent(name=_AGENTE_ALUNO_NOME, model=modelo, instruction="você é um professor")

    async def _turno():
        runner = Runner(
            app_name=_APP_NAME, agent=agente, session_service=provider._agente_session_service
        )
        async for _ in runner.run_async(
            user_id=_USER_ID,
            session_id=str(conversa_id),
            new_message=genai_types.Content(
                role="user", parts=[genai_types.Part.from_text(text="e o ranking?")]
            ),
        ):
            pass

    provider._run_no_loop_do_agente(_turno())

    assert modelo.recebidos[-1] == [
        ("user", "como estou indo?"),
        ("model", "Você tem 120 XP."),
        ("user", "e o ranking?"),
    ]


def test_falha_ao_registrar_nao_quebra_a_resposta(provider, caplog):
    class _Quebrado:
        async def get_session(self, **_kwargs):
            raise RuntimeError("banco fora do ar")

    provider._agente_session_service = _Quebrado()

    provider.registrar_troca(uuid.uuid4(), "meu xp", "120 XP.")  # must not raise

    assert "não foi possível registrar o atalho" in caplog.text
