"""RNF7 over HTTP: whose call it is, and what the admin sees."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai import consumo


def _env(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()
    return get_settings


def test_chamada_de_ia_numa_rota_sincrona_e_atribuida_ao_usuario_logado(
    monkeypatch, consumo_registros
):
    get_settings = _env(monkeypatch)
    from app.deps import CurrentUserId, get_current_user_id

    app = FastAPI()

    @app.get("/x")
    def rota(user_id: CurrentUserId) -> dict:
        with consumo.medir("conversar_com_agente"):
            pass
        return {}

    app.dependency_overrides[get_current_user_id] = lambda: "aluno-7"
    try:
        assert TestClient(app).get("/x").status_code == 200
    finally:
        get_settings.cache_clear()

    assert [r.user_id for r in consumo_registros] == ["aluno-7"]


class _RepoConsumo:
    def totais(self, desde):
        return 10, 2, 1500, 800

    def por_operacao(self, desde):
        return [("conversar_com_agente", 8, 1, 1200, 600), ("gerar_questionario", 2, 1, 300, 200)]

    def por_usuario(self, desde, limite):
        return [("aluno-7", 6, 1, 900, 500)]


def test_admin_ve_o_consumo_agregado(monkeypatch):
    get_settings = _env(monkeypatch)
    from app.deps import require_admin
    from app.main import app
    from app.repositories.ia_consumo_repository import get_ia_consumo_repository

    app.dependency_overrides[require_admin] = lambda: "admin-1"
    app.dependency_overrides[get_ia_consumo_repository] = lambda: _RepoConsumo()
    try:
        resposta = TestClient(app).get("/ia/consumo?dias=7")
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_ia_consumo_repository, None)
        get_settings.cache_clear()

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["periodo_dias"], corpo["chamadas"], corpo["falhas"]) == (7, 10, 2)
    assert (corpo["tokens_entrada"], corpo["tokens_saida"]) == (1500, 800)
    assert corpo["por_operacao"][0]["chave"] == "conversar_com_agente"
    assert corpo["por_usuario"] == [
        {"chave": "aluno-7", "chamadas": 6, "falhas": 1, "tokens_entrada": 900, "tokens_saida": 500}
    ]


def test_consumo_exige_admin(monkeypatch):
    get_settings = _env(monkeypatch)
    from app.main import app

    try:
        resposta = TestClient(app).get("/ia/consumo")
    finally:
        get_settings.cache_clear()

    assert resposta.status_code in (401, 403)
