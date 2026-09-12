from uuid import UUID

from fastapi import APIRouter, status

from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import AdminUserId, CurrentUserId, MateriaRepo
from app.models.materia import Materia
from app.schemas.materia import MateriaCreate, MateriaOut, MateriaUpdate
from app.services import curriculo_service

router = APIRouter(prefix="/materias", tags=["materias"])


@router.post("", response_model=MateriaOut, status_code=status.HTTP_201_CREATED)
def criar_materia(body: MateriaCreate, _admin_id: AdminUserId, repo: MateriaRepo) -> Materia:
    return curriculo_service.criar_materia(body.nome, body.descricao, repo)


@router.get("", response_model=list[MateriaOut])
def listar_materias(_user_id: CurrentUserId, repo: MateriaRepo) -> list[Materia]:
    return repo.list_all()


@router.get("/{materia_id}", response_model=MateriaOut)
def obter_materia(materia_id: UUID, _user_id: CurrentUserId, repo: MateriaRepo) -> Materia:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    return materia


@router.put("/{materia_id}", response_model=MateriaOut)
def atualizar_materia(
    materia_id: UUID, body: MateriaUpdate, _admin_id: AdminUserId, repo: MateriaRepo
) -> Materia:
    return curriculo_service.atualizar_materia(materia_id, body.nome, body.descricao, repo)


@router.delete("/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_materia(materia_id: UUID, _admin_id: AdminUserId, repo: MateriaRepo) -> None:
    curriculo_service.deletar_materia(materia_id, repo)
