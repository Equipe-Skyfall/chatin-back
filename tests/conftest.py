import pytest

from app.ai import consumo
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.in_memory_repositories import (
    InMemoryLicaoRepository,
    InMemoryProgressoRepository,
    InMemoryQuestionarioRepository,
    InMemoryTentativaRepository,
    InMemoryTrilhaEstudandoRepository,
)


@pytest.fixture
def fake_ai_provider() -> FakeAIProvider:
    return FakeAIProvider()


@pytest.fixture
def questionario_repo() -> InMemoryQuestionarioRepository:
    return InMemoryQuestionarioRepository()


@pytest.fixture
def tentativa_repo() -> InMemoryTentativaRepository:
    return InMemoryTentativaRepository()


@pytest.fixture
def progresso_repo() -> InMemoryProgressoRepository:
    return InMemoryProgressoRepository()


@pytest.fixture(autouse=True)
def _zerar_status_da_ia():
    """`status_ia` is process-wide state; keep one test's AI failures from
    leaking into the next."""
    from app.ai.disponibilidade import status_ia

    status_ia.registrar_sucesso()
    yield
    status_ia.registrar_sucesso()


@pytest.fixture(autouse=True)
def consumo_registros():
    """Usage records go to a list instead of the database, so no test depends on
    (or waits for) a connection. Tests can assert on the returned list."""
    registros: list[consumo.RegistroConsumo] = []
    consumo.definir_gravador(registros.append)
    yield registros
    consumo.definir_gravador(None)


@pytest.fixture
def licao_repo() -> InMemoryLicaoRepository:
    return InMemoryLicaoRepository()


@pytest.fixture
def trilha_estudando_repo() -> InMemoryTrilhaEstudandoRepository:
    return InMemoryTrilhaEstudandoRepository()
