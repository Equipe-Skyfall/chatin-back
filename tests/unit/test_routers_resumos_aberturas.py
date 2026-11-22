"""US18: each opening of a study summary counts, a PDF download does not."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.models.resumo_estudo import ResumoEstudo
from tests.fakes.in_memory_repositories import InMemoryResumoAberturaRepository

USER = "aluno-1"


class _ResumoRepo:
    def __init__(self, *resumos):
        self.resumos = {r.id: r for r in resumos}

    def get(self, resumo_id):
        return self.resumos.get(resumo_id)


def _resumo(user_id=USER):
    agora = datetime.now(UTC)
    return ResumoEstudo(
        id=uuid.uuid4(),
        user_id=user_id,
        modulo_id=None,
        conversa_id=None,
        titulo="Funções",
        conteudo={"visao_geral": "Resumo."},
        modelo_ia=None,
        created_at=agora,
        updated_at=agora,
    )


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()

    from app.deps import get_current_user_id
    from app.main import app
    from app.repositories.materia_repository import get_materia_repository
    from app.repositories.progresso_repository import get_progresso_repository
    from app.repositories.resumo_abertura_repository import get_resumo_abertura_repository
    from app.repositories.resumo_estudo_repository import get_resumo_estudo_repository
    from app.repositories.tentativa_repository import get_tentativa_repository
    from app.repositories.xp_repository import get_xp_repository
    from app.services import resumo_pdf_service
    from tests.fakes.in_memory_repositories import (
        InMemoryProgressoRepository,
        InMemoryTentativaRepository,
        InMemoryXpRepository,
    )

    meu, de_outro = _resumo(), _resumo("aluno-2")
    aberturas = InMemoryResumoAberturaRepository()

    class _Materias:
        def list_minhas_e_globais_with_temas_e_modulos(self, user_id):
            return []

    monkeypatch.setattr(resumo_pdf_service, "render_resumo_pdf", lambda resumo: b"%PDF-1.4")
    overrides = {
        get_current_user_id: lambda: USER,
        get_resumo_estudo_repository: lambda: _ResumoRepo(meu, de_outro),
        get_resumo_abertura_repository: lambda: aberturas,
        get_materia_repository: lambda: _Materias(),
        get_progresso_repository: lambda: InMemoryProgressoRepository(),
        get_tentativa_repository: lambda: InMemoryTentativaRepository(),
        get_xp_repository: lambda: InMemoryXpRepository(),
    }
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(
            client=TestClient(app), meu=meu, de_outro=de_outro, aberturas=aberturas
        )
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def _revisados(api) -> int:
    return api.client.get("/progresso").json()["resumos_revisados"]


def test_abrir_um_resumo_conta_uma_revisao(api):
    assert _revisados(api) == 0

    assert api.client.get(f"/resumos/{api.meu.id}").status_code == 200

    assert _revisados(api) == 1


def test_reabrir_o_mesmo_resumo_conta_de_novo(api):
    for _ in range(3):
        api.client.get(f"/resumos/{api.meu.id}")

    assert _revisados(api) == 3


def test_baixar_o_pdf_nao_conta(api):
    resposta = api.client.get(f"/resumos/{api.meu.id}/pdf")

    assert resposta.status_code == 200
    assert _revisados(api) == 0


def test_resumo_de_outro_aluno_da_404_e_nao_conta(api):
    assert api.client.get(f"/resumos/{api.de_outro.id}").status_code == 404
    assert api.client.get(f"/resumos/{uuid.uuid4()}").status_code == 404

    assert _revisados(api) == 0


def test_a_contagem_e_so_do_proprio_aluno(api):
    api.aberturas.registrar("aluno-2", api.de_outro.id)
    api.client.get(f"/resumos/{api.meu.id}")

    assert _revisados(api) == 1
