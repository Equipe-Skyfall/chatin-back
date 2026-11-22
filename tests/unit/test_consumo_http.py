"""RNF7 over HTTP: whose call it is, and what the admin sees."""

from datetime import datetime

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


class _PerfilRepo:
    def nomes_por_ids(self, ids):
        return {"aluno-7": "Ana Souza"} if "aluno-7" in ids else {}


class _RepoConsumo:
    def totais(self, desde):
        return 10, 2, 1500, 800

    def por_operacao(self, desde):
        return [("conversar_com_agente", 8, 1, 1200, 600), ("gerar_questionario", 2, 1, 300, 200)]

    def por_usuario(self, desde, limite):
        return [("aluno-7", 6, 1, 900, 500)]

    def por_periodo(self, desde, granularidade):
        self.granularidade = granularidade
        return [
            (datetime(2026, 11, 10), 2, 0, 100, 50),
            (datetime(2026, 11, 11), 8, 2, 1400, 750),
        ]


def test_admin_ve_o_consumo_agregado(monkeypatch):
    get_settings = _env(monkeypatch)
    from app.deps import require_admin
    from app.main import app
    from app.repositories.ia_consumo_repository import get_ia_consumo_repository
    from app.repositories.perfil_repository import get_perfil_repository

    app.dependency_overrides[require_admin] = lambda: "admin-1"
    app.dependency_overrides[get_ia_consumo_repository] = lambda: _RepoConsumo()
    app.dependency_overrides[get_perfil_repository] = lambda: _PerfilRepo()
    try:
        resposta = TestClient(app).get("/ia/consumo?dias=7")
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_ia_consumo_repository, None)
        app.dependency_overrides.pop(get_perfil_repository, None)
        get_settings.cache_clear()

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["periodo_dias"], corpo["chamadas"], corpo["falhas"]) == (7, 10, 2)
    assert (corpo["tokens_entrada"], corpo["tokens_saida"]) == (1500, 800)
    assert corpo["por_operacao"][0]["chave"] == "conversar_com_agente"
    assert corpo["por_operacao"][0]["rotulo"] is None
    assert corpo["por_usuario"] == [
        {
            "chave": "aluno-7",
            "rotulo": "Ana Souza",
            "chamadas": 6,
            "falhas": 1,
            "tokens_entrada": 900,
            "tokens_saida": 500,
        }
    ]
    # Oldest first, so a peak shows as the bucket with the most calls.
    assert [(p["inicio"], p["chamadas"]) for p in corpo["por_periodo"]] == [
        ("2026-11-10T00:00:00", 2),
        ("2026-11-11T00:00:00", 8),
    ]


def _consultar(monkeypatch, query: str):
    get_settings = _env(monkeypatch)
    from app.deps import require_admin
    from app.main import app
    from app.repositories.ia_consumo_repository import get_ia_consumo_repository
    from app.repositories.perfil_repository import get_perfil_repository

    repo = _RepoConsumo()
    app.dependency_overrides[require_admin] = lambda: "admin-1"
    app.dependency_overrides[get_ia_consumo_repository] = lambda: repo
    app.dependency_overrides[get_perfil_repository] = lambda: _PerfilRepo()
    try:
        return TestClient(app).get(f"/ia/consumo{query}"), repo
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_ia_consumo_repository, None)
        app.dependency_overrides.pop(get_perfil_repository, None)
        get_settings.cache_clear()


def test_consumo_por_periodo_e_diario_por_padrao_e_aceita_hora(monkeypatch):
    resposta, repo = _consultar(monkeypatch, "")
    assert resposta.status_code == 200 and repo.granularidade == "dia"

    resposta, repo = _consultar(monkeypatch, "?granularidade=hora")
    assert resposta.status_code == 200 and repo.granularidade == "hora"


def test_granularidade_invalida_e_rejeitada(monkeypatch):
    resposta, _ = _consultar(monkeypatch, "?granularidade=semana")
    assert resposta.status_code == 422


def test_consumo_exige_admin(monkeypatch):
    get_settings = _env(monkeypatch)
    from app.main import app

    try:
        resposta = TestClient(app).get("/ia/consumo")
    finally:
        get_settings.cache_clear()

    assert resposta.status_code in (401, 403)
