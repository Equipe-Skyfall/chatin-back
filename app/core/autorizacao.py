"""Ownership checks for the curriculum hierarchy (`Materia`/`Tema`/`Modulo`/
`Questionario`), needed since `Materia.owner_user_id` split it into two
namespaces: the global, admin-curated curriculum (`owner_user_id is None`,
visible to every authenticated user, mutable only by admins - unchanged
behavior) and a student's own personal trilha (visible/mutable only by that
student, capped at `Settings.TRILHAS_MAX_POR_USUARIO`).

Every router handler that reads or writes something reachable from a
`Materia` must call the matching function here before proceeding - there is
no query-level filtering that does this automatically, since `Tema`/`Modulo`/
`Questionario` don't carry `owner_user_id` themselves (only their ancestor
`Materia` does).
"""

from app.core.exceptions import AcessoNegadoException, MateriaNaoEncontradaException
from app.core.security import TokenPayload, require_admin_role
from app.models.materia import Materia


def verificar_acesso_leitura(materia: Materia, payload: TokenPayload) -> None:
    """Global content is visible to any authenticated user - exactly like
    before this trilha feature existed. A personal trilha is visible only to
    its own owner. Raises 404 (not 403) for someone else's trilha, so a
    request never confirms that a given id belongs to another user."""
    if materia.owner_user_id not in (None, payload.user_id):
        raise MateriaNaoEncontradaException(materia.id)


def verificar_acesso_escrita(materia: Materia, payload: TokenPayload) -> None:
    """Global content still requires the admin role (unchanged behavior) -
    admins have no special access to a student's personal trilha. A personal
    trilha can only be written to by its own owner."""
    if materia.owner_user_id is None:
        require_admin_role(payload)
    elif materia.owner_user_id != payload.user_id:
        raise MateriaNaoEncontradaException(materia.id)


def is_admin(payload: TokenPayload) -> bool:
    try:
        require_admin_role(payload)
    except AcessoNegadoException:
        return False
    return True
