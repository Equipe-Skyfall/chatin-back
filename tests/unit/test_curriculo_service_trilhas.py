"""Unit tests for `curriculo_service.criar_materia`'s `owner_user_id` -
global (admin) creation is unchanged; a non-`None` owner creates a
student's own trilha, no limit on how many."""

from app.models.materia import Materia
from app.services import curriculo_service


class _FakeMateriaRepository:
    def __init__(self):
        self.materias: list[Materia] = []

    def add(self, materia: Materia) -> Materia:
        self.materias.append(materia)
        return materia

    def commit(self) -> None:
        pass

    def refresh(self, materia: Materia) -> None:
        pass


def test_criar_materia_sem_owner_e_global():
    repo = _FakeMateriaRepository()

    materia = curriculo_service.criar_materia("Matemática", None, repo)

    assert materia.owner_user_id is None


def test_criar_materia_com_owner_e_pessoal():
    repo = _FakeMateriaRepository()

    materia = curriculo_service.criar_materia(
        "Extensivo ENEM", None, repo, owner_user_id="user-1"
    )

    assert materia.owner_user_id == "user-1"


def test_aluno_pode_criar_varias_trilhas_sem_limite():
    repo = _FakeMateriaRepository()

    for i in range(10):
        materia = curriculo_service.criar_materia(
            f"Trilha {i}", None, repo, owner_user_id="user-1"
        )
        assert materia.owner_user_id == "user-1"

    assert len(repo.materias) == 10
