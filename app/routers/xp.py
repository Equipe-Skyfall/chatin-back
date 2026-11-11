from uuid import UUID

from fastapi import APIRouter

from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import CurrentUserId, MateriaRepo, PerfilRepo, StreakRepo, XpRepo
from app.schemas.xp import MeuXpOut, RankingEntradaOut, RankingOut, XpPorMateriaOut
from app.services import streak_service, xp_service

router = APIRouter(tags=["xp"])


@router.get("/xp/meu", response_model=MeuXpOut)
def meu_xp(
    user_id: CurrentUserId, xp_repo: XpRepo, materia_repo: MateriaRepo, streak_repo: StreakRepo
) -> MeuXpOut:
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
        streak_atual=streak_service.sequencia_atual(
            streak_repo.get_by_user(user_id), streak_service.hoje()
        ),
        nivel=nivel_info.nivel,
        xp_proximo_nivel=nivel_info.xp_proximo_nivel,
        xp_faltando_proximo_nivel=nivel_info.xp_faltando_proximo_nivel,
        por_materia=por_materia,
    )


NOME_PADRAO = "Aluno"


def _montar_ranking(
    entradas: list[tuple[str, int]],
    minha: tuple[int, int] | None,
    user_id: str,
    perfil_repo: PerfilRepo,
) -> RankingOut:
    nomes = perfil_repo.nomes_por_ids([uid for uid, _ in entradas])
    return RankingOut(
        entradas=[
            RankingEntradaOut(
                posicao=i + 1, nome=nomes.get(uid) or NOME_PADRAO, xp=xp, voce=uid == user_id
            )
            for i, (uid, xp) in enumerate(entradas)
        ],
        minha_posicao=minha[0] if minha else None,
        meu_xp=minha[1] if minha else 0,
    )


@router.get("/ranking", response_model=RankingOut)
def ranking_global(
    user_id: CurrentUserId, xp_repo: XpRepo, perfil_repo: PerfilRepo, limit: int = 20
) -> RankingOut:
    return _montar_ranking(
        xp_repo.ranking_global(limit), xp_repo.posicao_global(user_id), user_id, perfil_repo
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
    return _montar_ranking(
        xp_repo.ranking_por_materia(materia_id, limit),
        xp_repo.posicao_por_materia(materia_id, user_id),
        user_id,
        perfil_repo,
    )
