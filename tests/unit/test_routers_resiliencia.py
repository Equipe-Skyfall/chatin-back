"""US-14 end to end over HTTP: with the AI provider failing on every call,
what does not depend on the AI keeps working. The real routes run; only the
repositories, the logged-in user and the AI provider are swapped."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ProvedorIAIndisponivelException
from app.models.modulo import Modulo
from app.models.questionario import Questionario
from app.models.tema import Tema
from app.models.tentativa import STATUS_EM_ANDAMENTO, Tentativa, TentativaQuestao
from tests.builders.questionario_builder import QuestionarioBuilder
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.in_memory_repositories import (
    InMemoryProgressoRepository,
    InMemoryQuestionarioRepository,
    InMemoryTentativaRepository,
    InMemoryXpRepository,
)

USER = "aluno-1"


class _AIForaDoAr(FakeAIProvider):
    def gerar_feedback_erros(self, erros):
        causa = httpx.ReadTimeout("sem resposta")
        raise ProvedorIAIndisponivelException("provedor fora do ar") from causa


class _MateriaRepo:
    def list_minhas_e_globais_with_temas_e_modulos(self, user_id):
        return []


class _Get:
    def __init__(self, *entities):
        self.entities = {e.id: e for e in entities}

    def get(self, entity_id):
        return self.entities.get(entity_id)


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
    from app.repositories.materia_repository import get_materia_repository
    from app.repositories.modulo_repository import get_modulo_repository
    from app.repositories.progresso_repository import get_progresso_repository
    from app.repositories.questionario_repository import get_questionario_repository
    from app.repositories.tema_repository import get_tema_repository
    from app.repositories.tentativa_repository import get_tentativa_repository
    from app.repositories.xp_repository import get_xp_repository

    repos = SimpleNamespace(
        tentativa=InMemoryTentativaRepository(),
        questionario=InMemoryQuestionarioRepository(),
        progresso=InMemoryProgressoRepository(),
        xp=InMemoryXpRepository(),
        modulo=_Get(),
        tema=_Get(),
    )
    overrides = {
        get_current_user_id: lambda: USER,
        get_ai_provider: lambda: _AIForaDoAr(),
        get_tentativa_repository: lambda: repos.tentativa,
        get_questionario_repository: lambda: repos.questionario,
        get_progresso_repository: lambda: repos.progresso,
        get_xp_repository: lambda: repos.xp,
        get_materia_repository: lambda: _MateriaRepo(),
        get_modulo_repository: lambda: repos.modulo,
        get_tema_repository: lambda: repos.tema,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(client=TestClient(app), repos=repos)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def _abrir_tentativa_de_modulo(repos, num_questoes=4):
    """An open, graded (non-practice) attempt on a módulo, so the route tries
    to generate AI feedback. Gabarito of every question is "A"."""
    tema = Tema(id=uuid.uuid4(), materia_id=uuid.uuid4(), titulo="Funções", ordem=0)
    modulo = Modulo(id=uuid.uuid4(), tema_id=tema.id, titulo="Módulo 1", ordem=0)
    repos.modulo = _Get(modulo)
    repos.tema = _Get(tema)

    questionario_pronto, questoes, gabarito = (
        QuestionarioBuilder().com_num_questoes(num_questoes).build()
    )
    repos.questionario.seed(questionario_pronto, questoes, gabarito)
    questionario = Questionario(id=uuid.uuid4(), modulo_id=modulo.id, modelo_ia="fake")
    questionario.modulo = modulo

    tentativa = Tentativa(
        id=uuid.uuid4(),
        user_id=USER,
        questionario_id=questionario.id,
        status=STATUS_EM_ANDAMENTO,
        total_questoes=num_questoes,
        pratica=False,
    )
    tentativa.questionario = questionario
    repos.tentativa.add(tentativa)
    repos.tentativa.commit()
    repos.tentativa.add_tentativa_questoes(
        [
            TentativaQuestao(tentativa_id=tentativa.id, questao_id=q.id, ordem=i)
            for i, q in enumerate(questoes)
        ]
    )
    for q in questoes:
        repos.tentativa.tema_por_questao[q.id] = tema.id
    return tentativa, questoes


def _corpo(questoes, letras):
    return {
        "respostas": [
            {"questao_id": str(q.id), "resposta_escolhida": letra}
            for q, letra in zip(questoes, letras, strict=True)
        ]
    }


def test_quiz_e_corrigido_mesmo_com_a_ia_fora_do_ar(api):
    tentativa, questoes = _abrir_tentativa_de_modulo(api.repos)

    resposta = api.client.post(
        f"/tentativas/{tentativa.id}/responder", json=_corpo(questoes, "AABB")
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["pontuacao"] == 50.0
    assert corpo["total_corretas"] == 2
    assert corpo["desempenho_tema"]["total_respostas"] == 4
    # only the explanation of the mistakes is missing, and the frontend is told so
    assert corpo["feedback"] is None
    assert corpo["feedback_indisponivel"] is True


def test_quiz_sem_erros_nao_marca_feedback_como_indisponivel(api):
    tentativa, questoes = _abrir_tentativa_de_modulo(api.repos)

    corpo = api.client.post(
        f"/tentativas/{tentativa.id}/responder", json=_corpo(questoes, "AAAA")
    ).json()

    assert corpo["pontuacao"] == 100.0
    assert corpo["feedback"] is None
    assert corpo["feedback_indisponivel"] is False


def test_progresso_e_status_da_ia_respondem_com_a_ia_fora_do_ar(api):
    assert api.client.get("/progresso").status_code == 200
    assert api.client.get("/healthz").status_code == 200
    assert api.client.get("/ia/status").status_code == 200
