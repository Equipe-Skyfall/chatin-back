"""A student choosing which community trilhas they study (`trilhas_estudando`)."""

import uuid

from app.core.exceptions import MateriaNaoEncontradaException, NaoPodePararDeEstudarException
from app.repositories.materia_repository import MateriaRepository
from app.repositories.trilha_estudando_repository import TrilhaEstudandoRepository


def _materia_ou_404(materia_id: uuid.UUID, materia_repo: MateriaRepository):
    materia = materia_repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    return materia


def estudar(
    user_id: str,
    materia_id: uuid.UUID,
    materia_repo: MateriaRepository,
    estudando_repo: TrilhaEstudandoRepository,
) -> None:
    """Idempotent. The verified curriculum and a student's own trilhas already
    count as studied, so there is nothing to store for them."""
    materia = _materia_ou_404(materia_id, materia_repo)
    if materia.owner_user_id in (None, user_id):
        return
    estudando_repo.adicionar(user_id, materia.id)
    estudando_repo.commit()


def parar_de_estudar(
    user_id: str,
    materia_id: uuid.UUID,
    materia_repo: MateriaRepository,
    estudando_repo: TrilhaEstudandoRepository,
) -> None:
    materia = _materia_ou_404(materia_id, materia_repo)
    if materia.owner_user_id in (None, user_id):
        raise NaoPodePararDeEstudarException()
    estudando_repo.remover(user_id, materia.id)
    estudando_repo.commit()
