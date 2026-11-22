from fastapi import APIRouter

from app.deps import AdminUserId, UsuarioDadosRepo
from app.schemas.usuario import UsuarioApagadoOut
from app.services import usuario_service

router = APIRouter(prefix="/admin/usuarios", tags=["admin"])


@router.delete("/{user_id}", response_model=UsuarioApagadoOut)
def apagar_dados_do_usuario(
    user_id: str, admin_id: AdminUserId, repo: UsuarioDadosRepo
) -> UsuarioApagadoOut:
    """Removes everything this service stores about `user_id` - XP and so the
    ranking, progress, streak, chats, attempts, summaries, AI usage, profile. Meant
    for after the account was deleted in authSys, which never tells this service.
    Admin only; irreversible."""
    apagados, materias = usuario_service.apagar_dados_do_usuario(user_id, admin_id, repo)
    return UsuarioApagadoOut(
        user_id=user_id, apagados=apagados, materias_proprias_mantidas=materias
    )
