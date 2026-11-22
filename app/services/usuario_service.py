"""Removing a user's data after their account was deleted in authSys."""

from app.core.exceptions import AutoExclusaoNaoPermitidaException, UsuarioSemDadosException
from app.repositories.usuario_dados_repository import UsuarioDadosRepository


def apagar_dados_do_usuario(
    user_id: str, admin_id: str, repo: UsuarioDadosRepository
) -> tuple[dict[str, int], int]:
    """Wipes everything stored for `user_id` and returns (rows deleted per table,
    trilhas of theirs that were kept). Refuses the admin's own id - a mistyped
    request must not erase the account that is making it - and an id with
    nothing stored, so a wrong id is told apart from a successful cleanup."""
    if user_id == admin_id:
        raise AutoExclusaoNaoPermitidaException()
    materias = repo.materias_proprias(user_id)
    try:
        apagados = repo.apagar_tudo(user_id)
        if not apagados:
            raise UsuarioSemDadosException(user_id)
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return apagados, materias
