"""Wiping a user's data after the account was deleted in authSys."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import AutoExclusaoNaoPermitidaException, UsuarioSemDadosException
from app.services import usuario_service

ADMIN = "admin-1"


class _Repo:
    def __init__(self, dados=None, materias=0, falhar=False):
        self.dados = dados or {}
        self.materias = materias
        self.falhar = falhar
        self.apagou, self.commits, self.rollbacks = [], 0, 0

    def materias_proprias(self, user_id):
        return self.materias

    def apagar_tudo(self, user_id):
        self.apagou.append(user_id)
        if self.falhar:
            raise RuntimeError("falha no banco")
        return dict(self.dados)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_apaga_e_devolve_o_que_foi_removido():
    repo = _Repo({"xp_eventos": 1, "perfis_usuario": 1}, materias=2)

    apagados, materias = usuario_service.apagar_dados_do_usuario("aluno-9", ADMIN, repo)

    assert apagados == {"xp_eventos": 1, "perfis_usuario": 1}
    assert materias == 2
    assert repo.apagou == ["aluno-9"] and repo.commits == 1


def test_admin_nao_pode_apagar_os_proprios_dados():
    repo = _Repo({"xp_eventos": 1})

    with pytest.raises(AutoExclusaoNaoPermitidaException):
        usuario_service.apagar_dados_do_usuario(ADMIN, ADMIN, repo)

    assert repo.apagou == [] and repo.commits == 0


def test_id_sem_nenhum_dado_da_404_e_nao_confirma_nada():
    repo = _Repo({})

    with pytest.raises(UsuarioSemDadosException):
        usuario_service.apagar_dados_do_usuario("nao-existe", ADMIN, repo)

    assert repo.commits == 0 and repo.rollbacks == 1


def test_falha_no_meio_desfaz_tudo():
    repo = _Repo({"xp_eventos": 1}, falhar=True)

    with pytest.raises(RuntimeError):
        usuario_service.apagar_dados_do_usuario("aluno-9", ADMIN, repo)

    assert repo.commits == 0 and repo.rollbacks == 1


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()

    from app.deps import require_admin
    from app.main import app
    from app.repositories.usuario_dados_repository import get_usuario_dados_repository

    repo = _Repo({"xp_eventos": 1, "tentativas": 2}, materias=1)
    overrides = {require_admin: lambda: ADMIN, get_usuario_dados_repository: lambda: repo}
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(client=TestClient(app), repo=repo, app=app)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def test_endpoint_apaga_os_dados_do_usuario(api):
    resposta = api.client.delete("/admin/usuarios/aluno-9")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "user_id": "aluno-9",
        "apagados": {"xp_eventos": 1, "tentativas": 2},
        "materias_proprias_mantidas": 1,
    }


def test_endpoint_recusa_apagar_o_proprio_admin(api):
    resposta = api.client.delete(f"/admin/usuarios/{ADMIN}")

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "auto_exclusao"
    assert api.repo.apagou == []


def test_endpoint_da_404_quando_nao_ha_dados(api):
    api.repo.dados = {}

    resposta = api.client.delete("/admin/usuarios/nao-existe")

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "usuario_sem_dados"


def test_endpoint_exige_admin(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()
    from app.main import app

    try:
        resposta = TestClient(app).delete("/admin/usuarios/aluno-9")
    finally:
        get_settings.cache_clear()

    assert resposta.status_code in (401, 403)
