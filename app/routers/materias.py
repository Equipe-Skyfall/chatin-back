from uuid import UUID

from fastapi import APIRouter, status

from app.core.autorizacao import is_admin, verificar_acesso_escrita
from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import CurrentUserId, MateriaRepo, TokenPayloadDep, VotoRepo
from app.models.materia import Materia
from app.schemas.materia import MateriaCreate, MateriaOut, MateriaUpdate, VotoInput, VotoOut
from app.services import curriculo_service, voto_service

router = APIRouter(prefix="/materias", tags=["materias"])


def _materia_out(materia: Materia, votos_por_id: dict[UUID, int]) -> MateriaOut:
    return MateriaOut(
        id=materia.id,
        nome=materia.nome,
        descricao=materia.descricao,
        owner_user_id=materia.owner_user_id,
        votos=votos_por_id.get(materia.id, 0),
        created_at=materia.created_at,
    )


@router.post("", response_model=MateriaOut, status_code=status.HTTP_201_CREATED)
def criar_materia(
    body: MateriaCreate, user_id: CurrentUserId, payload: TokenPayloadDep, repo: MateriaRepo
) -> MateriaOut:
    """An admin creates global, shared curriculum content (unchanged
    behavior). Any other authenticated student creates their own trilha
    instead - publicly visible/votable by everyone, no limit on how many."""
    if is_admin(payload):
        materia = curriculo_service.criar_materia(body.nome, body.descricao, repo)
    else:
        materia = curriculo_service.criar_materia(
            body.nome, body.descricao, repo, owner_user_id=user_id
        )
    return _materia_out(materia, {})


@router.get("", response_model=list[MateriaOut])
def listar_materias(
    _user_id: CurrentUserId, repo: MateriaRepo, voto_repo: VotoRepo
) -> list[MateriaOut]:
    """The official curriculum plus every student's trilha, from every
    student - public browsing. Sort by `votos` client-side (or treat
    `owner_user_id is None` as the "official" section, distinct from the
    community ones) - both fields are here specifically so the frontend can
    tell them apart without a second endpoint."""
    materias = repo.list_publica()
    votos_por_id = voto_repo.scores_por_materias([m.id for m in materias])
    return [_materia_out(m, votos_por_id) for m in materias]


@router.get("/{materia_id}", response_model=MateriaOut)
def obter_materia(
    materia_id: UUID, _user_id: CurrentUserId, repo: MateriaRepo, voto_repo: VotoRepo
) -> MateriaOut:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    votos = voto_repo.scores_por_materias([materia_id])
    return _materia_out(materia, votos)


@router.put("/{materia_id}", response_model=MateriaOut)
def atualizar_materia(
    materia_id: UUID,
    body: MateriaUpdate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    repo: MateriaRepo,
    voto_repo: VotoRepo,
) -> MateriaOut:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_escrita(materia, payload)
    atualizada = curriculo_service.atualizar_materia(materia_id, body.nome, body.descricao, repo)
    votos = voto_repo.scores_por_materias([materia_id])
    return _materia_out(atualizada, votos)


@router.delete("/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_materia(
    materia_id: UUID, _user_id: CurrentUserId, payload: TokenPayloadDep, repo: MateriaRepo
) -> None:
    materia = repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_escrita(materia, payload)
    curriculo_service.deletar_materia(materia_id, repo)


@router.post("/{materia_id}/votar", response_model=VotoOut)
def votar_materia(
    materia_id: UUID,
    body: VotoInput,
    user_id: CurrentUserId,
    repo: MateriaRepo,
    voto_repo: VotoRepo,
) -> VotoOut:
    """Upserts the caller's vote - voting again just changes it. Only valid
    on a trilha created by a student (`owner_user_id is not None`); voting
    on the official curriculum is rejected (`VotoEmConteudoGlobalException`)."""
    votos = voto_service.votar(user_id, materia_id, body.valor, repo, voto_repo)
    return VotoOut(materia_id=materia_id, votos=votos)


@router.delete("/{materia_id}/votar", response_model=VotoOut)
def remover_voto_materia(
    materia_id: UUID, user_id: CurrentUserId, repo: MateriaRepo, voto_repo: VotoRepo
) -> VotoOut:
    votos = voto_service.remover_voto(user_id, materia_id, repo, voto_repo)
    return VotoOut(materia_id=materia_id, votos=votos)
