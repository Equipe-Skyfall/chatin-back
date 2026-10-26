"""Who may write a quiz by hand, over HTTP. The real routes and the real
ownership check run; only the repositories and the logged-in user are fakes.

The rule under test: the global curriculum (`Materia.owner_user_id is None`)
is writable by admins only, a student's own trilha by that student only -
admins included among the "anyone else" - and someone else's trilha answers
404, never confirming it exists."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.security import TokenPayload
from tests.builders.modulo_builder import ModuloBuilder
from tests.fakes.in_memory_repositories import InMemoryQuestionarioRepository

DONO = "aluno-dono"
OUTRO_ALUNO = "aluno-outro"
ADMIN = "admin-1"


class _Get:
    def __init__(self, *entities):
        self.entities = {e.id: e for e in entities}

    def get(self, entity_id):
        return self.entities.get(entity_id)


def _questao(enunciado="Quanto é 2 + 2?", correta="B"):
    return {
        "enunciado": enunciado,
        "alternativas": [{"letra": letra, "texto": f"opção {letra}"} for letra in "ABCDE"],
        "explicacao": "Porque sim.",
        "resposta_correta": correta,
    }


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    get_settings.cache_clear()

    from app.ai.adk_provider import AdkProvider  # noqa: F401 - imported by app.deps
    from app.deps import get_current_user_id, get_token_payload
    from app.main import app
    from app.repositories.materia_repository import get_materia_repository
    from app.repositories.modulo_repository import get_modulo_repository
    from app.repositories.questionario_repository import get_questionario_repository
    from app.repositories.tema_repository import get_tema_repository

    # one módulo in a student's own trilha, one in the global curriculum
    trilha_do_dono = SimpleNamespace(id=uuid.uuid4(), owner_user_id=DONO)
    curriculo_global = SimpleNamespace(id=uuid.uuid4(), owner_user_id=None)
    tema_do_dono = SimpleNamespace(id=uuid.uuid4(), materia_id=trilha_do_dono.id)
    tema_global = SimpleNamespace(id=uuid.uuid4(), materia_id=curriculo_global.id)
    modulo_do_dono = ModuloBuilder().com_tema_id(tema_do_dono.id).build()
    modulo_global = ModuloBuilder().com_tema_id(tema_global.id).build()

    quem = SimpleNamespace(payload=TokenPayload(user_id=DONO, role="USER"))
    questionarios = InMemoryQuestionarioRepository()
    overrides = {
        get_token_payload: lambda: quem.payload,
        get_current_user_id: lambda: quem.payload.user_id,
        get_materia_repository: lambda: _Get(trilha_do_dono, curriculo_global),
        get_tema_repository: lambda: _Get(tema_do_dono, tema_global),
        get_modulo_repository: lambda: _Get(modulo_do_dono, modulo_global),
        get_questionario_repository: lambda: questionarios,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield SimpleNamespace(
            client=TestClient(app),
            quem=quem,
            questionarios=questionarios,
            modulo_do_dono=modulo_do_dono.id,
            modulo_global=modulo_global.id,
        )
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        get_settings.cache_clear()


def _entrar_como(api, user_id, role="USER"):
    api.quem.payload = TokenPayload(user_id=user_id, role=role)


def _criar_quiz(api, modulo_id, quantas=3):
    return api.client.post(
        f"/modulos/{modulo_id}/questionario",
        json={"questoes": [_questao(f"Pergunta {i}") for i in range(quantas)]},
    )


# --- the owner's whole CRUD ---


def test_dono_cria_o_quiz_da_propria_trilha_com_a_ordem_enviada(api):
    resposta = _criar_quiz(api, api.modulo_do_dono, quantas=3)

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert [q["enunciado"] for q in corpo] == ["Pergunta 0", "Pergunta 1", "Pergunta 2"]
    assert [q["ordem"] for q in corpo] == [0, 1, 2]
    assert corpo[0]["resposta_correta"] == "B"


def test_dono_le_adiciona_e_remove_questoes_do_proprio_quiz(api):
    _criar_quiz(api, api.modulo_do_dono, quantas=2)

    adicionada = api.client.post(
        f"/modulos/{api.modulo_do_dono}/questoes", json=_questao("Terceira", correta="E")
    )
    assert adicionada.status_code == 201, adicionada.text
    assert adicionada.json()["ordem"] == 2

    listadas = api.client.get(f"/modulos/{api.modulo_do_dono}/questoes").json()
    assert [q["enunciado"] for q in listadas] == ["Pergunta 0", "Pergunta 1", "Terceira"]

    removida = api.client.delete(f"/modulos/{api.modulo_do_dono}/questoes/{listadas[0]['id']}")
    assert removida.status_code == 204
    restantes = api.client.get(f"/modulos/{api.modulo_do_dono}/questoes").json()
    assert [q["enunciado"] for q in restantes] == ["Pergunta 1", "Terceira"]


def test_dono_remove_o_proprio_quiz_e_pode_criar_outro(api):
    _criar_quiz(api, api.modulo_do_dono)

    assert api.client.delete(f"/modulos/{api.modulo_do_dono}/questionario").status_code == 204
    assert api.client.get(f"/modulos/{api.modulo_do_dono}/questoes").status_code == 404
    assert _criar_quiz(api, api.modulo_do_dono, quantas=1).status_code == 201


def test_segundo_questionario_no_mesmo_modulo_e_conflito(api):
    _criar_quiz(api, api.modulo_do_dono)

    assert _criar_quiz(api, api.modulo_do_dono).status_code == 409


def test_nao_remove_a_ultima_questao(api):
    criado = _criar_quiz(api, api.modulo_do_dono, quantas=1).json()

    resposta = api.client.delete(f"/modulos/{api.modulo_do_dono}/questoes/{criado[0]['id']}")

    assert resposta.status_code == 409


# --- everyone else is refused, and nothing changes ---


@pytest.mark.parametrize("quem", [(OUTRO_ALUNO, "USER"), (ADMIN, "ADMIN")])
def test_ninguem_alem_do_dono_escreve_na_trilha_dele(api, quem):
    criado = _criar_quiz(api, api.modulo_do_dono, quantas=2).json()
    _entrar_como(api, *quem)
    modulo = api.modulo_do_dono

    respostas = [
        _criar_quiz(api, modulo),
        api.client.post(f"/modulos/{modulo}/questoes", json=_questao()),
        api.client.delete(f"/modulos/{modulo}/questoes/{criado[0]['id']}"),
        api.client.delete(f"/modulos/{modulo}/questionario"),
    ]

    # 404, not 403: someone else's trilha is never confirmed to exist
    assert [r.status_code for r in respostas] == [404, 404, 404, 404]
    _entrar_como(api, DONO)
    intacto = api.client.get(f"/modulos/{modulo}/questoes").json()
    assert [q["enunciado"] for q in intacto] == ["Pergunta 0", "Pergunta 1"]


def test_aluno_comum_nao_escreve_no_curriculo_global(api):
    _entrar_como(api, DONO, "USER")

    respostas = [
        _criar_quiz(api, api.modulo_global),
        api.client.post(f"/modulos/{api.modulo_global}/questoes", json=_questao()),
        api.client.delete(f"/modulos/{api.modulo_global}/questionario"),
    ]

    assert [r.status_code for r in respostas] == [403, 403, 403]


def test_admin_escreve_no_curriculo_global(api):
    _entrar_como(api, ADMIN, "ADMIN")

    assert _criar_quiz(api, api.modulo_global).status_code == 201
    assert (
        api.client.post(f"/modulos/{api.modulo_global}/questoes", json=_questao()).status_code
        == 201
    )
    assert api.client.delete(f"/modulos/{api.modulo_global}/questionario").status_code == 204


def test_modulo_inexistente_e_404(api):
    assert _criar_quiz(api, uuid.uuid4()).status_code == 404


# --- what is accepted as a questão ---


@pytest.mark.parametrize(
    "mudanca",
    [
        {"enunciado": ""},
        {"alternativas": [{"letra": "A", "texto": "x"}] * 4},
        {"alternativas": [{"letra": "A", "texto": "x"}] * 5},  # letters must be A-E, once each
        {"resposta_correta": "F"},
    ],
)
def test_questao_invalida_e_rejeitada(api, mudanca):
    corpo = {"questoes": [{**_questao(), **mudanca}]}

    resposta = api.client.post(f"/modulos/{api.modulo_do_dono}/questionario", json=corpo)

    assert resposta.status_code == 422
    assert api.questionarios.get_by_modulo(api.modulo_do_dono) is None


def test_questionario_sem_questoes_e_rejeitado(api):
    resposta = api.client.post(f"/modulos/{api.modulo_do_dono}/questionario", json={"questoes": []})

    assert resposta.status_code == 422
