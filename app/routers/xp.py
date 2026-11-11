from uuid import UUID

from fastapi import APIRouter, Query

from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import CurrentUserId, MateriaRepo, PerfilRepo, XpRepo
from app.schemas.xp import MeuXpOut, RankingOut, XpPorMateriaOut
from app.services import ranking_service, xp_service

router = APIRouter(tags=["xp"])


@router.get("/xp/meu", response_model=MeuXpOut)
def meu_xp(user_id: CurrentUserId, xp_repo: XpRepo, materia_repo: MateriaRepo) -> MeuXpOut:
    por_materia = []
    for materia in materia_repo.list_minhas_e_globais(user_id):
        xp = xp_repo.total_por_usuario_e_materia(user_id, materia.id)
        if xp > 0:
            por_materia.append(
                XpPorMateriaOut(materia_id=materia.id, materia_nome=materia.nome, xp=xp)
            )
    xp_total = xp_repo.total_por_usuario(user_id)
    nivel_info = xp_service.calcular_nivel(xp_total)
    return MeuXpOut(
        xp_total=xp_total,
        nivel=nivel_info.nivel,
        xp_proximo_nivel=nivel_info.xp_proximo_nivel,
        xp_faltando_proximo_nivel=nivel_info.xp_faltando_proximo_nivel,
        por_materia=por_materia,
    )


@router.get("/ranking", response_model=RankingOut)
def ranking_global(
    user_id: CurrentUserId,
    xp_repo: XpRepo,
    perfil_repo: PerfilRepo,
    limit: int = Query(20, ge=1, le=100),
) -> RankingOut:
    entradas = xp_repo.ranking_global(limit)
    apelidos = perfil_repo.apelidos_por_ids([uid for uid, _ in entradas] + [user_id])
    return ranking_service.montar_ranking(
        entradas, apelidos, user_id, xp_repo.posicao_global(user_id)
    )


@router.get("/ranking/materias/{materia_id}", response_model=RankingOut)
def ranking_por_materia(
    materia_id: UUID,
    user_id: CurrentUserId,
    xp_repo: XpRepo,
    materia_repo: MateriaRepo,
    perfil_repo: PerfilRepo,
    limit: int = Query(20, ge=1, le=100),
) -> RankingOut:
    if materia_repo.get(materia_id) is None:
        raise MateriaNaoEncontradaException(materia_id)
    entradas = xp_repo.ranking_por_materia(materia_id, limit)
    apelidos = perfil_repo.apelidos_por_ids([uid for uid, _ in entradas] + [user_id])
    return ranking_service.montar_ranking(
        entradas, apelidos, user_id, xp_repo.posicao_por_materia(user_id, materia_id)
    )
