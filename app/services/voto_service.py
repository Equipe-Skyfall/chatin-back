"""Voting on community trilhas (`Materia.owner_user_id is not None`) - the
only quality signal on fully-open, unmoderated student-created content.
Voting on the global curriculum doesn't mean anything and is rejected here,
not at the DB layer.
"""

import uuid

from app.core.exceptions import MateriaNaoEncontradaException, VotoEmConteudoGlobalException
from app.models.materia import Materia
from app.models.voto_materia import VotoMateria
from app.repositories.materia_repository import MateriaRepository
from app.repositories.voto_repository import VotoRepository


def _materia_comunidade(materia_id: uuid.UUID, materia_repo: MateriaRepository) -> Materia:
    materia = materia_repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    if materia.owner_user_id is None:
        raise VotoEmConteudoGlobalException()
    return materia


def votar(
    user_id: str,
    materia_id: uuid.UUID,
    valor: int,
    materia_repo: MateriaRepository,
    voto_repo: VotoRepository,
) -> int:
    """Upserts this user's vote (`valor` is `1` or `-1`) and returns the
    matéria's new net score. Voting again just changes the existing vote -
    a student can't stack multiple votes on the same trilha."""
    _materia_comunidade(materia_id, materia_repo)

    existente = voto_repo.get_by_user_e_materia(user_id, materia_id)
    if existente is not None:
        existente.valor = valor
        voto_repo.add(existente)
    else:
        voto_repo.add(VotoMateria(user_id=user_id, materia_id=materia_id, valor=valor))
    voto_repo.commit()

    return voto_repo.scores_por_materias([materia_id]).get(materia_id, 0)


def remover_voto(
    user_id: str,
    materia_id: uuid.UUID,
    materia_repo: MateriaRepository,
    voto_repo: VotoRepository,
) -> int:
    _materia_comunidade(materia_id, materia_repo)

    existente = voto_repo.get_by_user_e_materia(user_id, materia_id)
    if existente is not None:
        voto_repo.delete(existente)
        voto_repo.commit()

    return voto_repo.scores_por_materias([materia_id]).get(materia_id, 0)
