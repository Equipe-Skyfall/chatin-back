"""`POST /chat` end to end over HTTP: a clear, common request is answered from
the app's own data with no LLM call; anything else still reaches the agent. The
real route runs; the repositories, the logged-in user and the AI provider are
swapped."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ProvedorIAIndisponivelException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.in_memory_repositories import (
    InMemoryConversaRepository,
    InMemoryProgressoRepository,
)

USER = "aluno-1"


class _IAForaDoAr(FakeAIProvider):
    def conversar_com_agente_aluno(self, mensagens, conteudo_modulo, ctx):
        self.conversar_com_agente_aluno_calls += 1
        raise ProvedorIAIndisponivelException("provedor fora do ar")


class _Vazio:
    """Repositories the shortcut paths never touch."""

    def get(self, *_a, **_k):
        return None


class _MateriaRepo:
    def list_minhas_e_globais_with_temas_e_modulos(self, user_id):
        return []

    list_minhas_e_globais = list_minhas_e_globais_with_temas_e_modulos


class _TentativaRepo:
    def desempenho_por_tema(self, user_id):
        return {}

    def ultimo_estudo_por_modulo(self, user_id):
        return {}


class _XpRepo:
    def total_por_usuario(self, user_id):
        return 620

    def total_por_usuario_e_materia(self, user_id, materia_id):
        return 0

    def ranking_global(self, limit=20):
        return [("outro", 900), (USER, 620)]


class _PerfilRepo:
    def nomes_por_ids(self, ids):
        return {"outro": "Ana", USER: "Eu"}


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
    from app.repositories.materia_repository import get_materia_repository
    from app.repositories.modulo_repository import get_modulo_repository
    from app.repositories.perfil_repository import get_perfil_repository
    from app.repositories.progresso_repository import get_progresso_repository
    from app.repositories.questionario_repository import get_questionario_repository
    from app.repositories.tema_repository import get_tema_repository
    from app.repositories.tentativa_repository import get_tentativa_repository
    from app.repositories.voto_repository import get_voto_repository
    from app.repositories.xp_repository import get_xp_repository

    repos = SimpleNamespace(conversa=InMemoryConversaRepository(), ia=FakeAIProvider())
    overrides = {
        get_current_user_id: lambda: USER,
        get_ai_provider: lambda: repos.ia,
        get_conversa_repository: lambda: repos.conversa,
        get_materia_repository: lambda: _MateriaRepo(),
        get_modulo_repository: lambda: _Vazio(),
        get_tema_repository: lambda: _Vazio(),
        get_questionario_repository: lambda: _Vazio(),
        get_voto_repository: lambda: _Vazio(),
        get_progresso_repository: lambda: InMemoryProgressoRepository(),
        get_tentativa_repository: lambda: _TentativaRepo(),
        get_xp_repository: lambda: _XpRepo(),
        get_perfil_repository: lambda: _PerfilRepo(),
    }
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(client=TestClient(app), repos=repos, app=app)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def _mensagens(repos, conversa_id):
    return [
        (m.papel, m.conteudo)
        for m in repos.conversa.get_with_mensagens(uuid.UUID(conversa_id)).mensagens
    ]


def test_pedido_conhecido_e_respondido_sem_chamar_o_agente(api):
    resposta = api.client.post("/chat", json={"texto": "quanto xp eu tenho?"})

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["resposta"] == "Você tem 620 XP e está no nível 2. Faltam 100 XP para o nível 3."
    assert api.repos.ia.conversar_com_agente_aluno_calls == 0
    assert _mensagens(api.repos, corpo["conversa_id"]) == [
        (PAPEL_USUARIO, "quanto xp eu tenho?"),
        (PAPEL_ASSISTENTE, corpo["resposta"]),
    ]
    assert len(api.repos.ia.trocas_registradas) == 1


def test_ranking_mostra_a_posicao_do_aluno(api):
    corpo = api.client.post("/chat", json={"texto": "qual a minha posição no ranking"}).json()

    assert "1. Ana - 900 XP" in corpo["resposta"]
    assert "Sua posição: 2º, com 620 XP." in corpo["resposta"]
    assert api.repos.ia.conversar_com_agente_aluno_calls == 0


def test_pergunta_de_conteudo_continua_indo_para_o_agente(api):
    corpo = api.client.post("/chat", json={"texto": "explique a revolução francesa"}).json()

    assert api.repos.ia.conversar_com_agente_aluno_calls == 1
    assert api.repos.ia.trocas_registradas == []
    assert corpo["resposta"]


def test_pergunta_parecida_com_um_atalho_mas_de_conteudo_vai_para_o_agente(api):
    api.client.post("/chat", json={"texto": "o que é desempenho em física?"})
    api.client.post("/chat", json={"texto": "não quero ver meu desempenho"})

    assert api.repos.ia.conversar_com_agente_aluno_calls == 2
    assert api.repos.ia.trocas_registradas == []


def test_atalho_funciona_com_a_ia_fora_do_ar(api):
    api.repos.ia = _IAForaDoAr()

    atalho = api.client.post("/chat", json={"texto": "meu xp"})
    agente = api.client.post("/chat", json={"texto": "explique a revolução francesa"})

    assert atalho.status_code == 200  # no AI involved, so nothing to fail
    assert agente.status_code == 503  # the agent path still depends on it


def test_atalhos_podem_ser_desligados_pela_configuracao(api, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("ATALHOS_CHAT_ATIVOS", "false")
    get_settings.cache_clear()

    api.client.post("/chat", json={"texto": "quanto xp eu tenho?"})

    assert api.repos.ia.conversar_com_agente_aluno_calls == 1
    assert api.repos.ia.trocas_registradas == []


def test_conversa_seguinte_continua_na_mesma_conversa(api):
    primeira = api.client.post("/chat", json={"texto": "meu xp"}).json()

    segunda = api.client.post(
        "/chat",
        json={"texto": "explique a revolução francesa", "conversa_id": primeira["conversa_id"]},
    ).json()

    assert segunda["conversa_id"] == primeira["conversa_id"]
    historico = _mensagens(api.repos, primeira["conversa_id"])
    assert [papel for papel, _ in historico] == [
        PAPEL_USUARIO,
        PAPEL_ASSISTENTE,
        PAPEL_USUARIO,
        PAPEL_ASSISTENTE,
    ]
