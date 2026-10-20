import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import LicaoNaoIniciadaException, ModuloNaoEncontradoException
from app.routers.tentativas import _verificar_modulo_disponivel
from app.services.progresso_service import verificar_acesso_ao_modulo
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
            modulo.id,
            "user-1",
            modulo_repo,
            tema_repo,
            progresso_repo,
            licao_repo,
            _MateriaRepo(None),
        )

    assert erro.value.code == "LICAO_NAO_INICIADA"
    assert erro.value.extra == {"modulo_id": str(modulo.id)}


def test_quiz_do_modulo_libera_depois_da_licao(progresso_repo, licao_repo):
    modulo, modulo_repo, tema_repo = _cenario()
    licao_repo.marcar("user-1", modulo.id)

    liberado = _verificar_modulo_disponivel(
        modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, licao_repo, _MateriaRepo(None)
    )

    assert liberado.id == modulo.id


def test_licao_de_outro_aluno_nao_libera(progresso_repo, licao_repo):
    modulo, modulo_repo, tema_repo = _cenario()
    licao_repo.marcar("outro-aluno", modulo.id)

    with pytest.raises(LicaoNaoIniciadaException):
        _verificar_modulo_disponivel(
            modulo.id,
            "user-1",
            modulo_repo,
            tema_repo,
            progresso_repo,
            licao_repo,
            _MateriaRepo(None),
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


def test_com_a_ia_fora_do_ar_o_quiz_abre_sem_a_licao(progresso_repo, licao_repo):
    from app.ai.disponibilidade import status_ia

    modulo, modulo_repo, tema_repo = _cenario()
    status_ia.marcar_indisponivel()

    liberado = _verificar_modulo_disponivel(
        modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, licao_repo, _MateriaRepo(None)
    )

    assert liberado.id == modulo.id


class _ErroDeBanco(Exception):
    def __init__(self, sqlstate):
        self.sqlstate = sqlstate


class _DbQuebrado:
    def __init__(self, erro):
        self._erro = erro
        self.rollbacks = 0

    def execute(self, *_a, **_k):
        raise self._erro

    def rollback(self):
        self.rollbacks += 1


def test_tabela_da_licao_ausente_libera_em_vez_de_quebrar():
    """Migration 0019 ainda não aplicada: trilha, quiz e chat seguem."""
    import uuid

    from sqlalchemy.exc import ProgrammingError

    from app.repositories.licao_repository import LicaoRepository

    db = _DbQuebrado(ProgrammingError("SELECT", {}, _ErroDeBanco("42P01")))
    repo = LicaoRepository(db)
    modulo_ids = [uuid.uuid4(), uuid.uuid4()]

    assert repo.existe("user-1", modulo_ids[0]) is True
    assert repo.modulos_iniciados("user-1", modulo_ids) == set(modulo_ids)
    assert db.rollbacks == 2


@pytest.mark.parametrize(
    "erro",
    [
        pytest.param(OperationalError("SELECT", {}, _ErroDeBanco("08006")), id="banco_fora"),
        pytest.param(ProgrammingError("SELECT", {}, _ErroDeBanco("42703")), id="coluna_errada"),
    ],
)
def test_outros_erros_de_banco_nao_viram_quiz_liberado(erro):
    import uuid

    from app.repositories.licao_repository import LicaoRepository

    db = _DbQuebrado(erro)
    repo = LicaoRepository(db)

    with pytest.raises(type(erro)):
        repo.existe("user-1", uuid.uuid4())
    with pytest.raises(type(erro)):
        repo.modulos_iniciados("user-1", [uuid.uuid4()])


class _MateriaRepo:
    def __init__(self, owner_user_id):
        self._owner = owner_user_id

    def get(self, materia_id):
        from types import SimpleNamespace

        return SimpleNamespace(id=materia_id, owner_user_id=self._owner)


def test_acesso_a_licao_exige_modulo_pronto(progresso_repo):
    modulo, modulo_repo, tema_repo = _cenario()
    modulo.status = "rascunho"

    with pytest.raises(ModuloNaoEncontradoException):
        verificar_acesso_ao_modulo(
            modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, _MateriaRepo(None)
        )


def test_acesso_a_licao_nega_materia_de_outro_aluno(progresso_repo):
    modulo, modulo_repo, tema_repo = _cenario()

    with pytest.raises(ModuloNaoEncontradoException):
        verificar_acesso_ao_modulo(
            modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, _MateriaRepo("outro")
        )


def test_acesso_a_licao_vale_para_materia_global_e_propria(progresso_repo):
    modulo, modulo_repo, tema_repo = _cenario()

    for dono in (None, "user-1"):
        liberado = verificar_acesso_ao_modulo(
            modulo.id, "user-1", modulo_repo, tema_repo, progresso_repo, _MateriaRepo(dono)
        )
        assert liberado.id == modulo.id


def test_quiz_do_modulo_nega_materia_de_outro_aluno_mesmo_com_a_licao_dada(
    progresso_repo, licao_repo
):
    modulo, modulo_repo, tema_repo = _cenario()
    licao_repo.marcar("user-1", modulo.id)

    with pytest.raises(ModuloNaoEncontradoException):
        _verificar_modulo_disponivel(
            modulo.id,
            "user-1",
            modulo_repo,
            tema_repo,
            progresso_repo,
            licao_repo,
            _MateriaRepo("outro"),
        )


def test_quiz_do_modulo_vale_para_materia_propria(progresso_repo, licao_repo):
    modulo, modulo_repo, tema_repo = _cenario()
    licao_repo.marcar("user-1", modulo.id)

    liberado = _verificar_modulo_disponivel(
        modulo.id,
        "user-1",
        modulo_repo,
        tema_repo,
        progresso_repo,
        licao_repo,
        _MateriaRepo("user-1"),
    )

    assert liberado.id == modulo.id


def test_quiz_do_tema_nega_materia_de_outro_aluno(progresso_repo, licao_repo):
    from app.core.exceptions import TemaNaoEncontradoException
    from app.routers.tentativas import iniciar_tentativa_tema

    modulo, _modulo_repo, tema_repo = _cenario()
    tema = tema_repo.get(None)

    with pytest.raises(TemaNaoEncontradoException):
        iniciar_tentativa_tema(
            tema.id,
            "user-1",
            tema_repo,
            progresso_repo,
            licao_repo,
            _MateriaRepo("outro"),
            questionario_repo=None,
            tentativa_repo=None,
            settings=None,
        )
