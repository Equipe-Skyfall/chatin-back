"""PATCH/GET /perfil/apelido: validation and the case-insensitive uniqueness."""

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ApelidoEmUsoException


class _PerfilRepo:
    def __init__(self, em_uso=()):
        self.em_uso = {a.lower() for a in em_uso}
        self.salvos: dict[str, str] = {}

    def apelido_de(self, user_id):
        return self.salvos.get(user_id)

    def definir_apelido(self, user_id, apelido):
        if apelido.lower() in self.em_uso:
            raise ApelidoEmUsoException()
        self.salvos[user_id] = apelido


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()
    from app.deps import get_current_user_id
    from app.main import app
    from app.repositories.perfil_repository import get_perfil_repository

    repo = _PerfilRepo(em_uso=["Bruno"])
    app.dependency_overrides[get_current_user_id] = lambda: "aluno-1"
    app.dependency_overrides[get_perfil_repository] = lambda: repo
    try:
        yield TestClient(app), repo
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_define_o_apelido_normalizando_espacos(api):
    client, repo = api

    resposta = client.patch("/perfil/apelido", json={"apelido": "  Ana   Lu "})

    assert resposta.status_code == 200
    assert resposta.json() == {"apelido": "Ana Lu"}
    assert repo.salvos == {"aluno-1": "Ana Lu"}


def test_apelido_em_uso_responde_409_com_codigo(api):
    client, _ = api

    resposta = client.patch("/perfil/apelido", json={"apelido": "bruno"})

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "apelido_em_uso"


@pytest.mark.parametrize(
    "apelido", ["ab", "x" * 21, "ana@gmail.com", "   ", "a/b/c", "Aluno K3F9", "aluno 0001"]
)
def test_apelido_invalido_responde_422(api, apelido):
    client, repo = api

    assert client.patch("/perfil/apelido", json={"apelido": apelido}).status_code == 422
    assert repo.salvos == {}


def test_le_o_apelido_atual(api):
    client, repo = api
    assert client.get("/perfil/apelido").json() == {"apelido": None}

    repo.salvos["aluno-1"] = "Ana"

    assert client.get("/perfil/apelido").json() == {"apelido": "Ana"}
