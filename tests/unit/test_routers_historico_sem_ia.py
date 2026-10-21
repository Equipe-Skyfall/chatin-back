"""US-14 over HTTP, the read side: with the AI down, the student's history -
conversations, their messages, summaries and quiz attempts - is still served.
The real routes run; only the repositories, the logged-in user and the AI
provider are swapped."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.disponibilidade import status_ia
from app.core.exceptions import ProvedorIAIndisponivelException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.models.modulo import Modulo
from app.models.questionario import Questionario
from app.models.tentativa import STATUS_CONCLUIDA, Tentativa
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.in_memory_repositories import (
    InMemoryConversaRepository,
    InMemoryTentativaRepository,
)

USER = "aluno-1"
AGORA = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class _AIForaDoAr(FakeAIProvider):
    def resumir_conversa(self, mensagens):
        self.resumir_conversa_calls += 1
        causa = httpx.ReadTimeout("sem resposta")
        raise ProvedorIAIndisponivelException("provedor fora do ar") from causa


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()

    from app.ai.adk_provider import AdkProvider  # noqa: F401 - imported by app.deps
    from app.deps import get_ai_provider, get_current_user_id
    from app.main import app
    from app.repositories.conversa_repository import get_conversa_repository
    from app.repositories.tentativa_repository import get_tentativa_repository

    repos = SimpleNamespace(
        conversa=InMemoryConversaRepository(),
        tentativa=InMemoryTentativaRepository(),
        ia=_AIForaDoAr(),
    )
    overrides = {
        get_current_user_id: lambda: USER,
        get_ai_provider: lambda: repos.ia,
        get_conversa_repository: lambda: repos.conversa,
        get_tentativa_repository: lambda: repos.tentativa,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(client=TestClient(app), repos=repos)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def _conversa(repos, titulo, resumo=None, resumo_gerado_em=None, mensagens=2):
    conversa = Conversa(
        id=uuid.uuid4(),
        user_id=USER,
        titulo=titulo,
        tipo=TIPO_ALUNO,
        resumo=resumo,
        resumo_gerado_em=resumo_gerado_em,
        created_at=AGORA,
        updated_at=AGORA,
    )
    conversa.mensagens = [
        Mensagem(
            id=uuid.uuid4(),
            conversa_id=conversa.id,
            papel=PAPEL_USUARIO if i % 2 == 0 else PAPEL_ASSISTENTE,
            conteudo=f"mensagem {i}",
            ordem=i,
            created_at=AGORA,
        )
        for i in range(mensagens)
    ]
    repos.conversa.seed(conversa)
    return conversa


def test_lista_de_conversas_e_historico_respondem_com_a_ia_fora_do_ar(api):
    conversa = _conversa(api.repos, "Revolução Francesa", mensagens=3)

    lista = api.client.get("/chat")
    historico = api.client.get(f"/chat/{conversa.id}")

    assert lista.status_code == 200
    assert [c["id"] for c in lista.json()] == [str(conversa.id)]
    assert historico.status_code == 200
    assert [m["conteudo"] for m in historico.json()] == ["mensagem 0", "mensagem 1", "mensagem 2"]


def test_resumos_guardados_continuam_vindo_com_a_ia_fora_do_ar(api):
    em_dia = _conversa(
        api.repos,
        "Em dia",
        resumo="Resumo em dia.",
        resumo_gerado_em=datetime(2999, 1, 1, tzinfo=UTC),
    )
    antigo = _conversa(
        api.repos,
        "Desatualizado",
        resumo="Resumo antigo.",
        resumo_gerado_em=datetime(2020, 1, 1, tzinfo=UTC),
    )
    _conversa(api.repos, "Sem resumo")
    status_ia.marcar_indisponivel()

    resposta = api.client.get("/chat/resumos")

    assert resposta.status_code == 200
    por_conversa = {r["conversa_id"]: r["resumo"] for r in resposta.json()}
    assert por_conversa == {str(em_dia.id): "Resumo em dia.", str(antigo.id): "Resumo antigo."}
    assert api.repos.ia.resumir_conversa_calls == 0  # nobody waited for a timeout


def test_resumos_nao_quebram_quando_a_ia_falha_antes_de_ser_marcada_como_fora(api):
    antigo = _conversa(
        api.repos,
        "Desatualizado",
        resumo="Resumo antigo.",
        resumo_gerado_em=datetime(2020, 1, 1, tzinfo=UTC),
    )
    _conversa(api.repos, "Sem resumo")

    resposta = api.client.get("/chat/resumos")

    assert resposta.status_code == 200
    assert [r["conversa_id"] for r in resposta.json()] == [str(antigo.id)]
    assert api.repos.ia.resumir_conversa_calls == 2  # it did try, and survived the failures


def test_historico_de_tentativas_responde_com_a_ia_fora_do_ar(api):
    modulo = Modulo(id=uuid.uuid4(), tema_id=uuid.uuid4(), titulo="Módulo 1", ordem=0)
    questionario = Questionario(id=uuid.uuid4(), modulo_id=modulo.id, modelo_ia="fake")
    questionario.modulo = modulo
    tentativa = Tentativa(
        id=uuid.uuid4(),
        user_id=USER,
        questionario_id=questionario.id,
        status=STATUS_CONCLUIDA,
        pontuacao=80,
        total_questoes=5,
        total_corretas=4,
        created_at=AGORA,
    )
    tentativa.questionario = questionario
    api.repos.tentativa.add(tentativa)
    api.repos.tentativa.commit()
    status_ia.marcar_indisponivel()

    resposta = api.client.get("/tentativas")

    assert resposta.status_code == 200
    [item] = resposta.json()
    assert item["modulo_titulo"] == "Módulo 1"
    assert item["pontuacao"] == 80.0
    assert item["total_corretas"] == 4
