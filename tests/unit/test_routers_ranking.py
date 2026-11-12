"""`GET /ranking` and `/xp/meu` over HTTP: ordered by XP, showing only names,
marking the authenticated student's own place (also outside the top N)."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.models.streak import StreakUsuario
from app.models.xp import MOTIVO_PRIMEIRA_TENTATIVA, XpEvento
from app.services import streak_service
from tests.fakes.in_memory_repositories import InMemoryStreakRepository, InMemoryXpRepository

NOMES = {"u1": "Ana Souza", "u2": "Bruno Lima", "u3": "Carla Dias", "u4": "Davi Rocha"}


class _PerfilRepo:
    def apelidos_por_ids(self, ids):
        return {uid: NOMES[uid] for uid in ids if uid in NOMES}


class _MateriaRepo:
    def __init__(self, materia_id):
        self.materia_id = materia_id

    def get(self, materia_id):
        return object() if materia_id == self.materia_id else None

    def list_minhas_e_globais(self, user_id):
        return []


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
    from app.repositories.perfil_repository import get_perfil_repository
    from app.repositories.streak_repository import get_streak_repository
    from app.repositories.xp_repository import get_xp_repository

    materia_id = uuid.uuid4()
    estado = SimpleNamespace(
        user="u3",
        xp=InMemoryXpRepository(),
        streak=InMemoryStreakRepository(),
        materia_id=materia_id,
    )
    overrides = {
        get_current_user_id: lambda: estado.user,
        get_xp_repository: lambda: estado.xp,
        get_perfil_repository: lambda: _PerfilRepo(),
        get_materia_repository: lambda: _MateriaRepo(materia_id),
        get_streak_repository: lambda: estado.streak,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(client=TestClient(app), estado=estado)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def _dar_xp(estado, user, quantidade, materia_id=None):
    estado.xp.add(
        XpEvento(
            user_id=user,
            materia_id=materia_id or estado.materia_id,
            quantidade=quantidade,
            motivo=MOTIVO_PRIMEIRA_TENTATIVA,
        )
    )


def test_ranking_ordena_por_xp_e_mostra_so_o_nome(api):
    for user, xp in [("u1", 100), ("u2", 300), ("u3", 200)]:
        _dar_xp(api.estado, user, xp)

    corpo = api.client.get("/ranking").json()

    assert [(e["posicao"], e["nome"], e["xp"]) for e in corpo["entradas"]] == [
        (1, "Bruno Lima", 300),
        (2, "Carla Dias", 200),
        (3, "Ana Souza", 100),
    ]
    for entrada in corpo["entradas"]:
        assert set(entrada) == {"posicao", "nome", "xp", "voce"}  # no user id, no e-mail


def test_ranking_marca_a_entrada_do_aluno_autenticado(api):
    for user, xp in [("u1", 100), ("u2", 300), ("u3", 200)]:
        _dar_xp(api.estado, user, xp)

    corpo = api.client.get("/ranking").json()

    assert [e["nome"] for e in corpo["entradas"] if e["voce"]] == ["Carla Dias"]
    assert corpo["minha_posicao"] == 2
    assert corpo["meu_xp"] == 200


def test_minha_posicao_aparece_mesmo_fora_do_top(api):
    for user, xp in [("u1", 400), ("u2", 300), ("u3", 200), ("u4", 100)]:
        _dar_xp(api.estado, user, xp)

    corpo = api.client.get("/ranking?limit=2").json()

    assert [e["nome"] for e in corpo["entradas"]] == ["Ana Souza", "Bruno Lima"]
    assert not any(e["voce"] for e in corpo["entradas"])
    assert corpo["minha_posicao"] == 3
    assert corpo["meu_xp"] == 200


def test_aluno_sem_xp_nao_tem_posicao(api):
    _dar_xp(api.estado, "u1", 100)

    corpo = api.client.get("/ranking").json()

    assert corpo["minha_posicao"] is None
    assert corpo["meu_xp"] == 0


def test_aluno_sem_apelido_aparece_com_nome_neutro(api):
    _dar_xp(api.estado, "sem-perfil", 100)

    corpo = api.client.get("/ranking").json()

    assert corpo["entradas"][0]["nome"] == "Aluno RFIL"
    assert "sem-perfil" not in api.client.get("/ranking").text


def test_empate_em_xp_tem_ordem_estavel_e_posicao_consistente(api):
    _dar_xp(api.estado, "u2", 100)
    _dar_xp(api.estado, "u3", 100)

    corpo = api.client.get("/ranking").json()  # authenticated as u3

    assert [e["nome"] for e in corpo["entradas"]] == ["Bruno Lima", "Carla Dias"]
    assert corpo["minha_posicao"] == 2


def test_ranking_por_materia_so_conta_o_xp_da_materia(api):
    _dar_xp(api.estado, "u1", 500, materia_id=uuid.uuid4())  # another matéria
    _dar_xp(api.estado, "u2", 50)
    _dar_xp(api.estado, "u3", 80)

    corpo = api.client.get(f"/ranking/materias/{api.estado.materia_id}").json()

    assert [e["nome"] for e in corpo["entradas"]] == ["Carla Dias", "Bruno Lima"]
    assert corpo["minha_posicao"] == 1


def test_ranking_de_materia_inexistente_da_404(api):
    assert api.client.get(f"/ranking/materias/{uuid.uuid4()}").status_code == 404


def test_xp_do_streak_conta_no_ranking_global(api):
    for dia in range(2):
        streak_service.registrar_acesso_diario(
            "u1", api.estado.streak, api.estado.xp, streak_service.hoje() + timedelta(days=dia)
        )

    corpo = api.client.get("/ranking").json()

    assert corpo["entradas"][0]["nome"] == "Ana Souza"
    assert corpo["entradas"][0]["xp"] == streak_service.XP_STREAK_DIA


def test_meu_xp_mostra_o_streak_atual_e_zera_quando_perdido(api):
    hoje = streak_service.hoje()
    api.estado.streak.streaks["u3"] = StreakUsuario(user_id="u3", sequencia=5, ultimo_dia=hoje)
    assert api.client.get("/xp/meu").json()["streak_atual"] == 5

    api.estado.streak.streaks["u3"] = StreakUsuario(
        user_id="u3", sequencia=5, ultimo_dia=hoje - timedelta(days=2)
    )
    assert api.client.get("/xp/meu").json()["streak_atual"] == 0
