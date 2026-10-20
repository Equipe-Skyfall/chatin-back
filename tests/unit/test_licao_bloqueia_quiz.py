import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import LicaoNaoIniciadaException
from app.routers.tentativas import _verificar_modulo_disponivel
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.tema_builder import TemaBuilder
from tests.fakes.in_memory_repositories import InMemoryModuloRepository


class _TemaRepo:
    def __init__(self, tema):
        self._tema = tema

    def get(self, tema_id):
        return self._tema

    def list_by_materia_with_modulos(self, materia_id):
        return [self._tema]


def _cenario():
    tema = TemaBuilder().build()
    modulo = ModuloBuilder().com_tema_id(tema.id).build()
    tema.modulos = [modulo]
    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(modulo)
    return modulo, modulo_repo, _TemaRepo(tema)


def test_quiz_do_modulo_exige_a_licao(progresso_repo, licao_repo):
    modulo, modulo_repo, tema_repo = _cenario()

    with pytest.raises(LicaoNaoIniciadaException) as erro:
        _verificar_modulo_disponivel(
            modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, licao_repo
        )

    assert erro.value.code == "LICAO_NAO_INICIADA"
    assert erro.value.extra == {"modulo_id": str(modulo.id)}


def test_quiz_do_modulo_libera_depois_da_licao(progresso_repo, licao_repo):
    modulo, modulo_repo, tema_repo = _cenario()
    licao_repo.marcar("user-1", modulo.id)

    liberado = _verificar_modulo_disponivel(
        modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, licao_repo
    )

    assert liberado.id == modulo.id


def test_licao_de_outro_aluno_nao_libera(progresso_repo, licao_repo):
    modulo, modulo_repo, tema_repo = _cenario()
    licao_repo.marcar("outro-aluno", modulo.id)

    with pytest.raises(LicaoNaoIniciadaException):
        _verificar_modulo_disponivel(
            modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, licao_repo
        )


def test_handler_devolve_code_e_modulo_id():
    app = FastAPI()
    register_exception_handlers(app)
    modulo, *_ = _cenario()

    @app.get("/x")
    def _x():
        raise LicaoNaoIniciadaException(modulo.id)

    resposta = TestClient(app).get("/x")

    assert resposta.status_code == 403
    assert resposta.json()["code"] == "LICAO_NAO_INICIADA"
    assert resposta.json()["modulo_id"] == str(modulo.id)
    assert resposta.json()["detail"]
