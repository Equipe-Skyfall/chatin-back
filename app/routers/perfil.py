from fastapi import APIRouter

from app.deps import CurrentUserId, PerfilRepo
from app.schemas.perfil import ApelidoIn, ApelidoOut

router = APIRouter(tags=["perfil"])


@router.get("/perfil/apelido", response_model=ApelidoOut)
def obter_apelido(user_id: CurrentUserId, perfil_repo: PerfilRepo) -> ApelidoOut:
    return ApelidoOut(apelido=perfil_repo.apelido_de(user_id))


@router.patch("/perfil/apelido", response_model=ApelidoOut)
def definir_apelido(body: ApelidoIn, user_id: CurrentUserId, perfil_repo: PerfilRepo) -> ApelidoOut:
    perfil_repo.definir_apelido(user_id, body.apelido)
    return ApelidoOut(apelido=body.apelido)
