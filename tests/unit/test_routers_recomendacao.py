"""`GET /recomendacao` end to end over HTTP: the real route and service run;
only the repositories and the logged-in user are swapped."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.builders.materia_builder import MateriaBuilder
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.tema_builder import TemaBuilder
from tests.fakes.in_memory_repositories import InMemoryProgressoRepository

USER = "aluno-1"


class _MateriaRepo:
    def __init__(self, materias):
        self._materias = materias

    def list_minhas_e_globais_with_temas_e_modulos(self, user_id):
        return self._materias


class _TentativaRepo:
    def __init__(self, desempenho=None, ultimo=None):
        self._desempenho = desempenho or {}
        self._ultimo = ultimo or {}

    def desempenho_por_tema(self, user_id):
        return self._desempenho

    def ultimo_estudo_por_modulo(self, user_id):
        return self._ultimo


def _trilha():
    materia_id = uuid.uuid4()
    tema1 = TemaBuilder().com_materia_id(materia_id).com_titulo("Tema 1").com_ordem(0).build()
    tema1.modulos = [ModuloBuilder().com_tema_id(tema1.id).com_titulo("M1").pronto().build()]
    tema2 = TemaBuilder().com_materia_id(materia_id).com_titulo("Tema 2").com_ordem(1).build()
    tema2.modulos = [ModuloBuilder().com_tema_id(tema2.id).com_titulo("M2").pronto().build()]
    materia = (
        MateriaBuilder().com_id(materia_id).com_nome("História").com_temas([tema1, tema2]).build()
    )
    return materia, tema1, tema2


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()

    from app.ai.adk_provider import AdkProvider  # noqa: F401 - imported by app.deps
    from app.deps import get_current_user_id
    from app.main import app
    from app.repositories.materia_repository import get_materia_repository
    from app.repositories.progresso_repository import get_progresso_repository
    from app.repositories.tentativa_repository import get_tentativa_repository
    from app.repositories.xp_repository import get_xp_repository

    def configurar(materias, tentativa_repo=None):
        app.dependency_overrides = {
            get_current_user_id: lambda: USER,
            get_materia_repository: lambda: _MateriaRepo(materias),
            get_progresso_repository: lambda: InMemoryProgressoRepository(),
            get_xp_repository: lambda: SimpleNamespace(),
            get_tentativa_repository: lambda: tentativa_repo or _TentativaRepo(),
        }
        return TestClient(app)

    yield configurar
    app.dependency_overrides = {}
    get_settings.cache_clear()


def test_aluno_novo_recebe_o_primeiro_modulo(api):
    materia, tema1, _ = _trilha()

    resposta = api([materia]).get("/recomendacao")

    assert resposta.status_code == 200
    recomendacoes = resposta.json()["recomendacoes"]
    assert [r["posicao"] for r in recomendacoes] == [1]
    corpo = recomendacoes[0]
    assert corpo["modulo_id"] == str(tema1.modulos[0].id)
    assert corpo["motivo"] == "nao_estudado"
    assert corpo["materia_nome"] == "História"
    assert corpo["tema_titulo"] == "Tema 1"


def test_sem_conteudo_a_lista_e_vazia(api):
    resposta = api([]).get("/recomendacao")

    assert resposta.status_code == 200
    assert resposta.json() == {"recomendacoes": []}


def test_tema_com_baixo_desempenho_e_data_antiga_volta_a_ser_recomendado(api):
    materia, tema1, _ = _trilha()
    modulo = tema1.modulos[0]
    tentativas = _TentativaRepo(
        desempenho={tema1.id: (2, 10)},
        ultimo={modulo.id: datetime.now(UTC) - timedelta(days=1, hours=1)},
    )
    progresso = InMemoryProgressoRepository()
    progresso.get_or_create(USER, modulo.id).tentativas_count = 1

    from app.main import app
    from app.repositories.progresso_repository import get_progresso_repository

    cliente = api([materia], tentativas)
    app.dependency_overrides[get_progresso_repository] = lambda: progresso

    corpo = cliente.get("/recomendacao").json()["recomendacoes"][0]

    assert corpo["modulo_id"] == str(modulo.id)
    assert corpo["motivo"] == "baixo_desempenho"
    assert corpo["taxa_acerto_tema"] == 20.0
    assert corpo["dias_desde_ultimo_estudo"] == 1


def test_limite_da_lista_e_validado(api):
    materia, *_ = _trilha()
    cliente = api([materia])

    assert cliente.get("/recomendacao?limite=1").status_code == 200
    assert cliente.get("/recomendacao?limite=0").status_code == 422
    assert cliente.get("/recomendacao?limite=21").status_code == 422
