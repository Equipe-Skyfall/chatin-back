"""`GeminiProvider.resumir_conversa` sends the summarizing instruction as the
conversation's last user message (not as a system instruction), so the model
summarizes the chat instead of carrying it on - see the comment in the provider.
The Gemini call itself is stubbed."""

from types import SimpleNamespace

import pytest

from app.ai.gemini_provider import GeminiProvider
from app.ai.prompts import prompt_resumir_conversa
from app.ai.schemas import MensagemAgente
from app.config import Settings
from app.core.exceptions import ProvedorIAIndisponivelException


@pytest.fixture
def provider(monkeypatch):
    provider = GeminiProvider(
        Settings(
            SUPABASE_DB_URL="postgresql+psycopg://user:pass@localhost:5432/db",
            JWT_SECRET="test-secret",
            GEMINI_API_KEY="fake-key",
        )
    )
    provider.recebido = []

    def _gerar(**kwargs):
        provider.recebido.append(kwargs)
        return SimpleNamespace(text=provider.resposta, usage_metadata=None)

    provider.resposta = "O aluno perguntou sobre a Revolução Francesa."
    monkeypatch.setattr(provider, "_gerar_conteudo", _gerar)
    return provider


def _conversa(ultimo_papel):
    mensagens = [
        MensagemAgente(papel="user", conteudo="O que foi a Revolução Francesa?"),
        MensagemAgente(papel="assistant", conteudo="Um movimento de 1789 a 1799."),
    ]
    if ultimo_papel == "user":
        mensagens.append(MensagemAgente(papel="user", conteudo="Obrigado!"))
    return mensagens


@pytest.mark.parametrize("ultimo_papel", ["assistant", "user"])
def test_a_instrucao_vai_como_ultima_mensagem_do_usuario(provider, ultimo_papel):
    resumo = provider.resumir_conversa(_conversa(ultimo_papel))

    assert resumo == "O aluno perguntou sobre a Revolução Francesa."
    chamada = provider.recebido[0]
    ultima = chamada["contents"][-1]
    assert ultima.role == "user"
    assert ultima.parts[0].text == prompt_resumir_conversa()
    assert chamada["config"].system_instruction is None


def test_a_conversa_vai_antes_da_instrucao_na_mesma_ordem(provider):
    provider.resumir_conversa(_conversa("assistant"))

    contents = provider.recebido[0]["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[0].parts[0].text == "O que foi a Revolução Francesa?"
    assert contents[1].parts[0].text == "Um movimento de 1789 a 1799."


def test_resposta_vazia_continua_sendo_falha_do_provedor(provider):
    provider.resposta = "   "

    with pytest.raises(ProvedorIAIndisponivelException):
        provider.resumir_conversa(_conversa("assistant"))
