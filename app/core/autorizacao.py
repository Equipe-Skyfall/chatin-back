"""Write-access checks for the curriculum hierarchy (`Materia`/`Tema`/
`Modulo`/`Questionario`), needed since `Materia.owner_user_id` split it into
two namespaces: the global, admin-curated curriculum (`owner_user_id is
None`, mutable only by admins - unchanged from before this existed) and a
student's own trilha (mutable only by that student).

There is no read-access check here on purpose: every trilha, global or
student-created, is publicly readable by any authenticated user (that's the
point - other students browse and vote on them). Only writes are gated.

Every router handler that writes something reachable from a `Materia` must
call `verificar_acesso_escrita` before proceeding - there is no query-level
filtering that does this automatically, since `Tema`/`Modulo`/`Questionario`
don't carry `owner_user_id` themselves (only their ancestor `Materia` does).
"""

from app.core.exceptions import AcessoNegadoException, MateriaNaoEncontradaException
from app.core.security import TokenPayload, require_admin_role
from app.models.materia import Materia


def verificar_acesso_escrita(materia: Materia, payload: TokenPayload) -> None:
    """Global content still requires the admin role (unchanged behavior) -
    admins have no special access to a student's trilha. A student's own
    trilha can only be written to by its own owner. Raises 404 (not 403) for
    someone else's trilha, so a request never confirms that a given id
    belongs to another student."""
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
