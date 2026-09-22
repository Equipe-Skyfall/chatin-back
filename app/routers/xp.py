from uuid import UUID

from fastapi import APIRouter

from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import CurrentUserId, MateriaRepo, PerfilRepo, XpRepo
from app.schemas.xp import MeuXpOut, RankingEntradaOut, RankingOut, XpPorMateriaOut
from app.services import xp_service

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
    user_id: CurrentUserId, xp_repo: XpRepo, perfil_repo: PerfilRepo, limit: int = 20
) -> RankingOut:
    entradas = xp_repo.ranking_global(limit)
    nomes = perfil_repo.nomes_por_ids([uid for uid, _ in entradas])
    return RankingOut(
        entradas=[
            RankingEntradaOut(posicao=i + 1, user_id=uid, nome=nomes.get(uid), xp=xp)
            for i, (uid, xp) in enumerate(entradas)
        ]
    )


@router.get("/ranking/materias/{materia_id}", response_model=RankingOut)
def ranking_por_materia(
    materia_id: UUID,
    user_id: CurrentUserId,
    xp_repo: XpRepo,
    materia_repo: MateriaRepo,
    perfil_repo: PerfilRepo,
    limit: int = 20,
) -> RankingOut:
    if materia_repo.get(materia_id) is None:
        raise MateriaNaoEncontradaException(materia_id)
    entradas = xp_repo.ranking_por_materia(materia_id, limit)
    nomes = perfil_repo.nomes_por_ids([uid for uid, _ in entradas])
    return RankingOut(
        entradas=[
            RankingEntradaOut(posicao=i + 1, user_id=uid, nome=nomes.get(uid), xp=xp)
            for i, (uid, xp) in enumerate(entradas)
        ]
    )
