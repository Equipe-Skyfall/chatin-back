"""Unit tests for the personal-trilha cap in `curriculo_service.criar_materia`
(`owner_user_id` + `limite_trilhas`) - no database, a minimal in-memory fake
repository is enough since the cap check is pure counting logic.
"""

import pytest

from app.core.exceptions import TrilhaLimiteExcedidoException
from app.models.materia import Materia
from app.services import curriculo_service

LIMITE = 3


class _FakeMateriaRepository:
    def __init__(self):
        self._materias: list[Materia] = []

    def count_by_owner(self, user_id: str) -> int:
        return sum(1 for m in self._materias if m.owner_user_id == user_id)

    def add(self, materia: Materia) -> None:
        self._materias.append(materia)

    def commit(self) -> None:
        pass

    def refresh(self, materia: Materia) -> None:
        pass


def test_admin_cria_materia_global_sem_limite():
    repo = _FakeMateriaRepository()
    for i in range(LIMITE + 2):
        materia = curriculo_service.criar_materia(f"Matéria {i}", None, repo)
        assert materia.owner_user_id is None


def test_usuario_cria_ate_o_limite_de_trilhas():
    repo = _FakeMateriaRepository()
    user_id = "user-1"

    for i in range(LIMITE):
        materia = curriculo_service.criar_materia(
            f"Trilha {i}", None, repo, owner_user_id=user_id, limite_trilhas=LIMITE
        )
        assert materia.owner_user_id == user_id

    with pytest.raises(TrilhaLimiteExcedidoException):
        curriculo_service.criar_materia(
            "Trilha extra", None, repo, owner_user_id=user_id, limite_trilhas=LIMITE
        )


def test_limite_e_por_usuario_nao_global():
    repo = _FakeMateriaRepository()
    for i in range(LIMITE):
        curriculo_service.criar_materia(
            f"Trilha de A {i}", None, repo, owner_user_id="user-a", limite_trilhas=LIMITE
        )

    # user-b's own count is still zero - A being at the cap doesn't affect B.
    materia = curriculo_service.criar_materia(
        "Trilha de B", None, repo, owner_user_id="user-b", limite_trilhas=LIMITE
    )
    assert materia.owner_user_id == "user-b"
