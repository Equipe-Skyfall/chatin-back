import pytest

from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.in_memory_repositories import (
    InMemoryProgressoRepository,
    InMemoryQuestionarioRepository,
    InMemoryTentativaRepository,
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
