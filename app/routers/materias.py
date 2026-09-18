from uuid import UUID

from fastapi import APIRouter, status

from app.core.autorizacao import is_admin, verificar_acesso_escrita, verificar_acesso_leitura
from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import CurrentUserId, MateriaRepo, TokenPayloadDep
from app.models.materia import Materia
from app.schemas.materia import MateriaCreate, MateriaOut, MateriaUpdate
from app.services import curriculo_service

router = APIRouter(prefix="/materias", tags=["materias"])


@router.post("", response_model=MateriaOut, status_code=status.HTTP_201_CREATED)
def criar_materia(
    body: MateriaCreate, user_id: CurrentUserId, payload: TokenPayloadDep, repo: MateriaRepo
) -> Materia:
    """An admin creates global, shared curriculum content (unchanged
    behavior). Any other authenticated user creates their own personal
    trilha instead - no limit on how many."""
    if is_admin(payload):
        return curriculo_service.criar_materia(body.nome, body.descricao, repo)
    return curriculo_service.criar_materia(
        body.nome, body.descricao, repo, owner_user_id=user_id
    )


@router.get("", response_model=list[MateriaOut])
def listar_materias(user_id: CurrentUserId, repo: MateriaRepo) -> list[Materia]:
    """The global curriculum plus this user's own personal trilhas."""
    return repo.list_visiveis(user_id)


@router.get("/{materia_id}", response_model=MateriaOut)
def obter_materia(
    materia_id: UUID, _user_id: CurrentUserId, payload: TokenPayloadDep, repo: MateriaRepo
) -> Materia:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_leitura(materia, payload)
    return materia


@router.put("/{materia_id}", response_model=MateriaOut)
def atualizar_materia(
    materia_id: UUID,
    body: MateriaUpdate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    repo: MateriaRepo,
) -> Materia:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_escrita(materia, payload)
    return curriculo_service.atualizar_materia(materia_id, body.nome, body.descricao, repo)


@router.delete("/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_materia(
    materia_id: UUID, _user_id: CurrentUserId, payload: TokenPayloadDep, repo: MateriaRepo
) -> None:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_escrita(materia, payload)
    curriculo_service.deletar_materia(materia_id, repo)
