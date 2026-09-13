"""Unit tests for `curriculo_service.criar_materia`'s `owner_user_id` -
distinguishes global (admin) content from a student's own personal trilha.
No database, a minimal in-memory fake repository is enough.
"""

from app.models.materia import Materia
from app.services import curriculo_service


class _FakeMateriaRepository:
    def __init__(self):
        self._materias: list[Materia] = []

    def add(self, materia: Materia) -> None:
        self._materias.append(materia)

    def commit(self) -> None:
        pass

    def refresh(self, materia: Materia) -> None:
        pass


def test_admin_cria_materia_global():
    repo = _FakeMateriaRepository()
    materia = curriculo_service.criar_materia("Matemática", None, repo)
    assert materia.owner_user_id is None


def test_usuario_cria_trilha_pessoal():
    repo = _FakeMateriaRepository()
    materia = curriculo_service.criar_materia(
        "Extensivo ENEM", None, repo, owner_user_id="user-1"
    )
    assert materia.owner_user_id == "user-1"


def test_usuario_pode_criar_quantas_trilhas_quiser():
    """Não há mais um limite de trilhas por usuário."""
    repo = _FakeMateriaRepository()
    for i in range(10):
        materia = curriculo_service.criar_materia(
            f"Trilha {i}", None, repo, owner_user_id="user-1"
        )
        assert materia.owner_user_id == "user-1"
    assert len(repo._materias) == 10
